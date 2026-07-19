"""Spike: record what the PC is playing via WASAPI loopback.

Windows hides a 'loopback' twin of every output device. PyAudioWPatch
exposes it, so we can open the default speakers *as an input* and capture
exactly what the user hears - no Teams API, no virtual audio cables.
Run with music or a video playing; produces test.wav (gitignored).
"""

import wave
import pyaudiowpatch as pyaudio

SECONDS = 5

p = pyaudio.PyAudio()
wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
if not speakers.get("isLoopbackDevice"):
    for lb in p.get_loopback_device_info_generator():
        if speakers["name"] in lb["name"]:
            speakers = lb
            break

rate = int(speakers["defaultSampleRate"])
channels = speakers["maxInputChannels"]
print(f"Recording {SECONDS}s from: {speakers['name']}")

stream = p.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                input=True, input_device_index=speakers["index"])
frames = [stream.read(1024) for _ in range(int(rate / 1024 * SECONDS))]
stream.close()
p.terminate()

with wave.open("test.wav", "wb") as wf:
    wf.setnchannels(channels)
    wf.setsampwidth(2)
    wf.setframerate(rate)
    wf.writeframes(b"".join(frames))
print("Saved test.wav")