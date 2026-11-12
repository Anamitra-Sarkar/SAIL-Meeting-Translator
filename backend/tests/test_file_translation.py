import io
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient
from main import app
from audio_utils import create_synthetic_wav

client = TestClient(app)

def test_translate_audio_empty_file():
    response = client.post(
        "/translate-audio",
        files={"file": ("test.wav", b"", "audio/wav")}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

def test_translate_audio_invalid_extension():
    response = client.post(
        "/translate-audio",
        files={"file": ("malicious.exe", b"binarydata", "application/octet-stream")}
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()

def test_translate_audio_valid_wav():
    wav_content = create_synthetic_wav(duration_s=1.0, sample_rate=16000)
    response = client.post(
        "/translate-audio",
        files={"file": ("meeting_sample.wav", wav_content, "audio/wav")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "language" in data
    assert "language_name" in data
    assert "language_probability" in data
    assert "original_transcript" in data
    assert "translation" in data
    assert isinstance(data["original_transcript"], list)
    assert isinstance(data["translation"], list)
