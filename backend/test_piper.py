import wave
from piper import PiperVoice

# Load the local English voice
voice = PiperVoice.load("voices/en_US-lessac-medium.onnx")

# Generate English speech
text = "Hello! This is the SAIL Meeting Translator. English talkback is working successfully."

with wave.open("talkback_output.wav", "wb") as audio_file:
    voice.synthesize_wav(text, audio_file)

print("SUCCESS: English talkback audio generated!")