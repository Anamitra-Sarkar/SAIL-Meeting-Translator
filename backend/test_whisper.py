import soundcard as sc
import numpy as np
from faster_whisper import WhisperModel

# Step 1: Select speaker audio
speaker = sc.default_speaker()

microphone = sc.get_microphone(
    id=str(speaker.name),
    include_loopback=True
)

# Step 2: Capture 10 seconds of meeting audio
print("Recording audio for 10 seconds...")
print("Play a video or meeting with speech.")

with microphone.recorder(samplerate=16000) as recorder:
    audio = recorder.record(numframes=16000 * 10)

print("Audio captured!")

# Step 3: Convert stereo audio into mono
audio = audio.mean(axis=1).astype(np.float32)

# Step 4: Load Whisper model
print("Loading Whisper model...")

try:
    print("Loading Whisper model...", flush=True)

    model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
    cpu_threads=2
)

    print("Whisper model loaded successfully!", flush=True)

except Exception as e:
    print("WHISPER ERROR:", repr(e), flush=True)
    raise

# Step 5: Translate speech into English
print("Translating speech into English...")

segments, info = model.transcribe(
    audio,
    task="translate",
    beam_size=5
)

print("\nDetected language:", info.language)
print("\nEnglish Translation:")

for segment in segments:
    print(segment.text)