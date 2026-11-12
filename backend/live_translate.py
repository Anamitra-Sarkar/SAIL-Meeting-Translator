
import soundcard as sc
import numpy as np
from faster_whisper import WhisperModel
import time

SAMPLE_RATE = 16000
CHUNK_DURATION = 5

print("Loading Whisper Tiny model...", flush=True)

model = WhisperModel(
    "tiny",
    device="cpu",
    compute_type="int8",
    cpu_threads=2
)

print("Whisper model loaded successfully!", flush=True)

speaker = sc.default_speaker()

microphone = sc.get_microphone(
    id=str(speaker.name),
    include_loopback=True
)

print("\nLIVE MEETING TRANSLATOR STARTED")
print("Play speech through your computer speakers.")
print("Press Ctrl+C to stop.\n")

try:
    with microphone.recorder(samplerate=SAMPLE_RATE) as recorder:
        while True:
            audio = recorder.record(
                numframes=SAMPLE_RATE * CHUNK_DURATION
            )

            audio = audio.mean(axis=1).astype(np.float32)

            if np.max(np.abs(audio)) < 0.005:
                print("No speech detected. Waiting...")
                continue

            print("\nTranslating audio...")

            segments, info = model.transcribe(
                audio,
                task="translate",
                beam_size=1
            )

            print("Detected language:", info.language)

            for segment in segments:
                print("English:", segment.text.strip())

except KeyboardInterrupt:
    print("\nLive translation stopped.")
