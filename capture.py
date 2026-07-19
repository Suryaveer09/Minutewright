"""Capture system audio and transcribe it live.

Pipeline: WASAPI loopback callback -> queue -> worker thread -> resample to
16kHz mono -> chunked faster-whisper transcription every few seconds.

Whisper isn't a streaming model, so "live" captions are faked by transcribing
short chunks as they fill up. This is the same trick every live-Whisper app
uses (whisper.cpp's stream demo, RealtimeSTT, etc).

If a wav_path is given, the raw captured audio is also written to disk
incrementally, so even an hours-long meeting never has to fit in memory.
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
        # Trim any leftover partial frame, then average L+R into one channel.
        usable = (len(audio) // channels) * channels
        audio = audio[:usable].reshape(-1, channels).mean(axis=1)

    if rate != TARGET_SR:
        from math import gcd
        g = gcd(TARGET_SR, rate)
        audio = resample_poly(audio, TARGET_SR // g, rate // g).astype(np.float32)

    return audio


class LiveCapture:
    """Records system audio and transcribes it in near-real-time chunks."""

    def __init__(self, model: WhisperModel, wav_path=None):
        self.model = model
        self.wav_path = wav_path      # if set, raw audio is saved here
        self.q: queue.Queue[bytes] = queue.Queue()
        self.lines = []               # [{"t": seconds, "text": "..."}]
        self.rate = None
        self.channels = None
        self._stop = threading.Event()

    def start(self):
        p = pyaudio.PyAudio()
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not speakers.get("isLoopbackDevice"):
            for lb in p.get_loopback_device_info_generator():
                if speakers["name"] in lb["name"]:
                    speakers = lb
                    break

        self.rate = int(speakers["defaultSampleRate"])
        self.channels = speakers["maxInputChannels"]

        def callback(in_data, frame_count, time_info, status):
            self.q.put(in_data)
            return (None, pyaudio.paContinue)

        self._pa = p
        self._stream = p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=speakers["index"],
            stream_callback=callback,
        )
        self._stream.start_stream()

        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        print(f"Listening to: {speakers['name']}")

    def stop(self):
        self._stop.set()
        self._worker_thread.join(timeout=30)
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()

    def _worker(self):
        wav = None
        if self.wav_path:
            wav = wave.open(str(self.wav_path), "wb")
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)   # int16
            wav.setframerate(self.rate)

        buf = np.zeros(0, dtype=np.float32)
        chunk_n = int(CHUNK_SECONDS * TARGET_SR)
        consumed = 0  # 16kHz samples already transcribed, for timestamps

        try:
            while not self._stop.is_set():
                drained = []
                try:
                    while True:
                        drained.append(self.q.get_nowait())
                except queue.Empty:
                    pass

                if drained:
                    raw = b"".join(drained)
                    if wav:
                        wav.writeframes(raw)
                    buf = np.concatenate([buf, to_mono_16k(raw, self.rate, self.channels)])

                while len(buf) >= chunk_n:
                    piece = buf[:chunk_n]
                    buf = buf[chunk_n:]
                    start_s = consumed / TARGET_SR
                    consumed += len(piece)
                    self._transcribe(piece, start_s)

                time.sleep(0.4)

            # Flush: grab anything still sitting in the queue, then transcribe
            # whatever's left in buf even if it's short of a full chunk.
            drained = []
            try:
                while True:
                    drained.append(self.q.get_nowait())
            except queue.Empty:
                pass
            if drained:
                raw = b"".join(drained)
                if wav:
                    wav.writeframes(raw)
                buf = np.concatenate([buf, to_mono_16k(raw, self.rate, self.channels)])
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
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception:
            # One bad chunk must not kill the whole meeting (learned the hard
            # way from the cuBLAS crash): log it and keep recording.
            print("Transcription error on one chunk:\n" + traceback.format_exc(limit=2))
            return
        if text:
            line = {"t": start_s, "text": text}
            self.lines.append(line)
            mm, ss = divmod(int(start_s), 60)
            print(f"[{mm:02d}:{ss:02d}] {text}")