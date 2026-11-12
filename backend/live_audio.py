
import soundcard as sc
import numpy as np
import time

def capture_audio(duration=5):
    speaker = sc.default_speaker()

    microphone = sc.get_microphone(
        id=str(speaker.name),
        include_loopback=True
    )

    print("Capturing meeting audio...")

    with microphone.recorder(samplerate=16000) as recorder:
        audio = recorder.record(
            numframes=16000 * duration
        )

    audio = audio.mean(axis=1).astype(np.float32)

    print("Audio captured successfully!")
    print("Audio duration:", len(audio) / 16000, "seconds")
    print("Audio level:", np.max(np.abs(audio)))

    return audio


if __name__ == "__main__":
    print("Live Audio Capture Test")
    print("Play speech through your computer speakers.")

    time.sleep(2)

    audio = capture_audio(duration=5)

    print("Capture test completed.")
