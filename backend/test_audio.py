import soundcard as sc
import numpy as np
import time

print("Available audio devices:")

for device in sc.all_microphones(include_loopback=True):
    print(device.name)

print("\nStarting audio capture for 5 seconds...")

speaker = sc.default_speaker()
microphone = sc.get_microphone(
    id=str(speaker.name),
    include_loopback=True
)

with microphone.recorder(samplerate=16000) as recorder:
    audio = recorder.record(numframes=16000 * 5)

print("\nAudio captured successfully!")
print("Audio shape:", audio.shape)
print("Audio level:", np.max(np.abs(audio)))