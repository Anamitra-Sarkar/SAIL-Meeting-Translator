import wave
import io
import numpy as np
import pytest
from audio_utils import (
    resample_audio,
    calculate_rms_level,
    pcm_bytes_to_float32,
    create_synthetic_wav
)

def test_resample_audio():
    # 1 second of 48kHz audio = 48000 samples
    samples_48k = np.sin(np.linspace(0, 100, 48000, dtype=np.float32))
    resampled = resample_audio(samples_48k, orig_sr=48000, target_sr=16000)
    assert len(resampled) == 16000
    assert resampled.dtype == np.float32

    # Same sample rate -> returns unchanged
    same = resample_audio(samples_48k, orig_sr=48000, target_sr=48000)
    assert len(same) == 48000

    # Empty array handling
    empty = resample_audio(np.empty(0, dtype=np.float32), 44100, 16000)
    assert len(empty) == 0

def test_calculate_rms_level():
    # Silence
    silence = np.zeros(1600, dtype=np.float32)
    assert calculate_rms_level(silence) == 0.0

    # Constant signal
    const = np.ones(1600, dtype=np.float32) * 0.5
    assert pytest.approx(calculate_rms_level(const), rel=1e-3) == 0.5

    # Empty array
    assert calculate_rms_level(np.empty(0, dtype=np.float32)) == 0.0

def test_pcm_bytes_to_float32():
    # Valid 4-sample float32 array
    original = np.array([0.1, -0.2, 0.5, -0.9], dtype=np.float32)
    raw_bytes = original.tobytes()
    parsed = pcm_bytes_to_float32(raw_bytes)
    assert np.allclose(original, parsed)

    # Incomplete byte length (not divisible by 4)
    invalid_bytes = b"\x00\x00\x01"
    assert len(pcm_bytes_to_float32(invalid_bytes)) == 0

    # Empty bytes
    assert len(pcm_bytes_to_float32(b"")) == 0

def test_create_synthetic_wav():
    wav_bytes = create_synthetic_wav(duration_s=0.5, sample_rate=16000, freq=440.0)
    assert len(wav_bytes) > 44  # WAV header is 44 bytes

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 8000
