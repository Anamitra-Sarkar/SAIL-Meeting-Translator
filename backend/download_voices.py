#!/usr/bin/env python3
"""
Utility script to download Piper TTS voices.
Downloads the default English voice (en_US-lessac-medium) to the voices/ directory.
"""

import os
import sys
import urllib.request

VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
VOICE_NAME = "en_US-lessac-medium"

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
FILES = [
    f"{VOICE_NAME}.onnx",
    f"{VOICE_NAME}.onnx.json"
]

def download_file(url: str, dest_path: str):
    print(f"Downloading {os.path.basename(dest_path)}...")
    
    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            percent = min(100, (block_num * block_size * 100) // total_size)
            sys.stdout.write(f"\r  Progress: {percent}% ({block_num * block_size // 1024} KB / {total_size // 1024} KB)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_path, reporthook)
    sys.stdout.write("\n")
    sys.stdout.flush()

def ensure_piper_voice(target_dir: str = VOICE_DIR) -> bool:
    os.makedirs(target_dir, exist_ok=True)
    all_success = True

    for filename in FILES:
        dest_path = os.path.join(target_dir, filename)
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            print(f"✓ Found existing: {filename} ({os.path.getsize(dest_path)} bytes)")
            continue

        url = f"{BASE_URL}/{filename}"
        try:
            download_file(url, dest_path)
            print(f"✓ Successfully downloaded: {filename}")
        except Exception as e:
            print(f"✗ Failed to download {filename}: {e}", file=sys.stderr)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            all_success = False

    return all_success

if __name__ == "__main__":
    success = ensure_piper_voice()
    sys.exit(0 if success else 1)
