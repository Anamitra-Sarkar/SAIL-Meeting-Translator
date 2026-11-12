import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_websocket_ping_pong():
    with client.websocket_connect("/ws/browser-live?sample_rate=16000") as websocket:
        init_msg = websocket.receive_json()
        assert init_msg["type"] == "status"
        assert "established" in init_msg["message"].lower()

        # Send heartbeat ping
        websocket.send_text("ping")
        reply = websocket.receive_text()
        assert reply == "pong"

def test_websocket_silence_streaming():
    with client.websocket_connect("/ws/browser-live?sample_rate=16000") as websocket:
        init_msg = websocket.receive_json()
        assert init_msg["type"] == "status"

        # Send 1 second of complete silence (zeros)
        silent_audio = np.zeros(16000, dtype=np.float32)
        websocket.send_bytes(silent_audio.tobytes())

        # Give it a fraction of a second to ensure it does not emit an error
        time.sleep(0.2)
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"
