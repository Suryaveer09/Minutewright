"""Capture system audio (and optionally the microphone) and transcribe live.

Pipeline: WASAPI loopback callback + optional mic callback -> queues ->
worker thread -> both converted to 16kHz mono -> MIXED (sum + clip) ->
written to a 16kHz mono WAV + chunked faster-whisper transcription.

Whisper isn't a streaming model, so "live" captions are faked by
transcribing short chunks as they fill up.

Notes on the mix:
- The saved WAV is the mixed 16kHz mono track, so playback contains both
  sides of a meeting. (Roadmap: dual-track native-quality recording.)
- The two streams run on independent clocks; we mix min-available-length
  each cycle, which keeps them aligned to well under a second over a
  typical meeting. Good enough for transcription and review.
- Open speakers cause the mic to re-hear remote voices (echoey doubling);
  headphones give clean separation. The UI says so.

All transcription runs with word_timestamps=True so every word knows its
position in the audio - that's what powers click-to-seek in the UI.

Also home to transcribe_file(), used for user-uploaded recordings: one
full-context pass over the whole file, which yields better transcripts
than live chunking (no chunk-boundary garbling).
"""

import queue
import threading
import time
import traceback
import wave

import numpy as np
import pyaudiowpatch as pyaudio
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

TARGET_SR = 16000       # Whisper's native sample rate
CHUNK_SECONDS = 5.0     # how often new captions appear


def to_mono_16k(raw: bytes, rate: int, channels: int) -> np.ndarray:
    """int16 interleaved bytes at native rate -> float32 mono 16kHz."""
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    if channels > 1:
        # Trim any leftover partial frame, then average channels to mono.
        usable = (len(audio) // channels) * channels
        audio = audio[:usable].reshape(-1, channels).mean(axis=1)

    if rate != TARGET_SR:
        from math import gcd
        g = gcd(TARGET_SR, rate)
        audio = resample_poly(audio, TARGET_SR // g, rate // g).astype(np.float32)

    return audio


def _words_of(segment, offset: float = 0.0) -> list:
    """Per-word timestamps from a segment -> [{"w": word, "s": seconds}]."""
    out = []
    for w in (segment.words or []):
        word = w.word.strip()
        if word:
            out.append({"w": word, "s": round(offset + w.start, 2)})
    return out


def list_devices() -> dict:
    """Enumerate WASAPI capture sources for the settings UI.

    speakers: loopback devices (system-audio sources), shown without the
    "[Loopback]" suffix; mics: real input devices. Restricted to the
    WASAPI host API so each physical device appears once (not duplicated
    by MME/DirectSound).
    """
    p = pyaudio.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers, mics = [], []
        for lb in p.get_loopback_device_info_generator():
            speakers.append({
                "index": lb["index"],
                "name": lb["name"].replace(" [Loopback]", ""),
            })
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if (d.get("hostApi") == wasapi["index"]
                    and d.get("maxInputChannels", 0) > 0
                    and not d.get("isLoopbackDevice")):
                mics.append({"index": d["index"], "name": d["name"]})
        return {"speakers": speakers, "mics": mics}
    finally:
        p.terminate()


class LiveCapture:
    """Records system audio (+ optional mic) and transcribes it live."""

    def __init__(self, model: WhisperModel, wav_path=None,
                 loopback_index=None, mic_index=None, capture_mic=True):
        self.model = model
        self.wav_path = wav_path
        self.loopback_index = loopback_index   # None = default speakers
        self.mic_index = mic_index             # None = default microphone
        self.capture_mic = capture_mic
        self.mic_active = False
        self.mic_error = None

        self.q_spk: queue.Queue[bytes] = queue.Queue()
        self.q_mic: queue.Queue[bytes] = queue.Queue()
        self.lines = []               # [{"t": s, "text": "...", "words": [...]}]
        self._stop = threading.Event()
        self._streams = []

    # ------------------------------------------------------------- start
    def start(self) -> dict:
        p = pyaudio.PyAudio()
        self._pa = p

        # --- system audio (loopback) -------------------------------------
        if self.loopback_index is not None:
            try:
                speakers = p.get_device_info_by_index(self.loopback_index)
            except Exception:
                speakers = None
        else:
            speakers = None
        if speakers is None or not speakers.get("isLoopbackDevice"):
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not speakers.get("isLoopbackDevice"):
                for lb in p.get_loopback_device_info_generator():
                    if speakers["name"] in lb["name"]:
                        speakers = lb
                        break

        self.spk_rate = int(speakers["defaultSampleRate"])
        self.spk_channels = max(1, speakers["maxInputChannels"])

        def spk_cb(in_data, frame_count, time_info, status):
            self.q_spk.put(in_data)
            return (None, pyaudio.paContinue)

        self._streams.append(p.open(
            format=pyaudio.paInt16,
            channels=self.spk_channels,
            rate=self.spk_rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=speakers["index"],
            stream_callback=spk_cb,
        ))
        print(f"Listening to: {speakers['name']}")

        # --- microphone (optional; failure never blocks recording) -------
        if self.capture_mic:
            try:
                if self.mic_index is not None:
                    mic = p.get_device_info_by_index(self.mic_index)
                else:
                    mic = p.get_default_input_device_info()
                if mic.get("maxInputChannels", 0) < 1 or mic.get("isLoopbackDevice"):
                    raise RuntimeError("Selected device can't record audio")

                self.mic_rate = int(mic["defaultSampleRate"])
                self.mic_channels = min(2, max(1, mic["maxInputChannels"]))

                def mic_cb(in_data, frame_count, time_info, status):
                    self.q_mic.put(in_data)
                    return (None, pyaudio.paContinue)

                self._streams.append(p.open(
                    format=pyaudio.paInt16,
                    channels=self.mic_channels,
                    rate=self.mic_rate,
                    frames_per_buffer=1024,
                    input=True,
                    input_device_index=mic["index"],
                    stream_callback=mic_cb,
                ))
                self.mic_active = True
                print(f"Also recording mic: {mic['name']}")
            except Exception as exc:
                self.mic_error = ("Couldn't open the microphone - recording "
                                  "system audio only. " + str(exc))
                print(self.mic_error)

        for s in self._streams:
            s.start_stream()

        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        return {"mic_requested": self.capture_mic,
                "mic_active": self.mic_active,
                "mic_error": self.mic_error}

    def stop(self):
        self._stop.set()
        self._worker_thread.join(timeout=30)
        for s in self._streams:
            try:
                s.stop_stream()
                s.close()
            except Exception:
                pass
        self._pa.terminate()

    # ------------------------------------------------------------ worker
    @staticmethod
    def _drain(q: queue.Queue) -> bytes:
        out = []
        try:
            while True:
                out.append(q.get_nowait())
        except queue.Empty:
            pass
        return b"".join(out)

    def _worker(self):
        wav = None
        if self.wav_path:
            wav = wave.open(str(self.wav_path), "wb")
            wav.setnchannels(1)          # the mixed track is 16kHz mono
            wav.setsampwidth(2)
            wav.setframerate(TARGET_SR)

        spk16 = np.zeros(0, dtype=np.float32)   # converted, waiting to be mixed
        mic16 = np.zeros(0, dtype=np.float32)
        buf = np.zeros(0, dtype=np.float32)     # mixed, waiting to be transcribed
        chunk_n = int(CHUNK_SECONDS * TARGET_SR)
        consumed = 0

        def emit(mixed: np.ndarray):
            nonlocal buf
            if not len(mixed):
                return
            if wav:
                wav.writeframes((mixed * 32767).astype(np.int16).tobytes())
            buf = np.concatenate([buf, mixed])

        try:
            while not self._stop.is_set():
                raw = self._drain(self.q_spk)
                if raw:
                    spk16 = np.concatenate(
                        [spk16, to_mono_16k(raw, self.spk_rate, self.spk_channels)])

                if self.mic_active:
                    raw_m = self._drain(self.q_mic)
                    if raw_m:
                        mic16 = np.concatenate(
                            [mic16, to_mono_16k(raw_m, self.mic_rate, self.mic_channels)])
                    # Mix only what both sides have; carry remainders forward.
                    n = min(len(spk16), len(mic16))
                    if n:
                        mixed = np.clip(spk16[:n] + mic16[:n], -1.0, 1.0)
                        spk16, mic16 = spk16[n:], mic16[n:]
                        emit(mixed)
                else:
                    emit(spk16)
                    spk16 = np.zeros(0, dtype=np.float32)

                while len(buf) >= chunk_n:
                    piece = buf[:chunk_n]
                    buf = buf[chunk_n:]
                    start_s = consumed / TARGET_SR
                    consumed += len(piece)
                    self._transcribe(piece, start_s)

                time.sleep(0.4)

            # Flush: drain everything, pad the shorter side with silence so
            # no audio is dropped, mix, and transcribe the remainder.
            raw = self._drain(self.q_spk)
            if raw:
                spk16 = np.concatenate(
                    [spk16, to_mono_16k(raw, self.spk_rate, self.spk_channels)])
            if self.mic_active:
                raw_m = self._drain(self.q_mic)
                if raw_m:
                    mic16 = np.concatenate(
                        [mic16, to_mono_16k(raw_m, self.mic_rate, self.mic_channels)])
                n = max(len(spk16), len(mic16))
                spk16 = np.pad(spk16, (0, n - len(spk16)))
                mic16 = np.pad(mic16, (0, n - len(mic16)))
                emit(np.clip(spk16 + mic16, -1.0, 1.0))
            else:
                emit(spk16)
            if len(buf) >= TARGET_SR // 2:   # only bother if at least ~0.5s remains
                self._transcribe(buf, consumed / TARGET_SR)
        finally:
            # Always close: wave only writes correct header sizes on close(),
            # so skipping this - even during a crash - corrupts the file.
            if wav:
                wav.close()

    def _transcribe(self, piece: np.ndarray, start_s: float):
        try:
            segments, _ = self.model.transcribe(
                piece, language="en", beam_size=1,
                vad_filter=True, condition_on_previous_text=False,
                word_timestamps=True,
            )
            texts, words = [], []
            for seg in segments:  # iterating IS the transcription
                t = seg.text.strip()
                if t:
                    texts.append(t)
                words.extend(_words_of(seg, offset=start_s))
            text = " ".join(texts).strip()
        except Exception:
            # One bad chunk must not kill the whole meeting (learned the hard
            # way from the cuBLAS crash): log it and keep recording.
            print("Transcription error on one chunk:\n" + traceback.format_exc(limit=2))
            return
        if text:
            line = {"t": start_s, "text": text, "words": words}
            self.lines.append(line)
            mm, ss = divmod(int(start_s), 60)
            print(f"[{mm:02d}:{ss:02d}] {text}")


def transcribe_file(model: WhisperModel, path, on_progress=None):
    """Transcribe an uploaded audio/video file in ONE full-context pass.

    faster-whisper decodes mp3/m4a/mp4/wav/ogg/flac/webm itself (bundled
    FFmpeg via PyAV) - no external tools needed. Full-file transcription
    uses default beam search and cross-segment context, so quality is
    *better* than the live chunked path.

    on_progress: optional callback taking percent (0-100), driven by each
    segment's end time against the file's total duration.

    Returns (lines, duration_sec) where lines is the same shape LiveCapture
    produces: [{"t": seconds, "text": "...", "words": [{"w","s"}, ...]}].
    """
    segments, info = model.transcribe(str(path), vad_filter=True, word_timestamps=True)
    duration = float(info.duration or 0.0)
    lines = []
    for s in segments:  # generator: iterating IS the transcription
        text = s.text.strip()
        if text:
            lines.append({"t": float(s.start), "text": text, "words": _words_of(s)})
        if on_progress and duration:
            on_progress(min(100.0, s.end / duration * 100.0))
    return lines, duration