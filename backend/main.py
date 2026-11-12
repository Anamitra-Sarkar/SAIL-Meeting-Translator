import os
import time
import asyncio
import tempfile
import threading

import numpy as np
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel


# =====================================================
# SETTINGS (safe to change)
# =====================================================

# "base" is fast. "small" is more accurate but slower.
MODEL_SIZE = "base"

# CPU threads used by Whisper
CPU_THREADS = max(2, (os.cpu_count() or 4) - 1)

# Browser sends audio at 16000 Hz
SAMPLE_RATE = 16000

# Chunks quieter than this are treated as silence and skipped
SILENCE_LEVEL = 0.003

# Audio is NEVER skipped while the model is busy: chunks wait in line.
# 120 chunks of 10 seconds = 20 minutes of waiting audio (about 75 MB).
# Only if the line gets longer than this is the oldest chunk dropped,
# to protect the computer's memory.
MAX_WAITING_CHUNKS = 120

# False = FAST mode: one Whisper pass per chunk (English text only).
# True  = also write the original-language text (needs a second pass,
#         so it takes roughly twice as long).
# Start with False. Change to True only if the terminal shows that
# "Processed ... in ..." is clearly shorter than the audio length.
SHOW_ORIGINAL_TEXT = True

# True  = if Whisper hears Urdu, show it as Hindi (Devanagari)
# False = keep Urdu as Urdu
TREAT_URDU_AS_HINDI = True

# True = do not show anything when English is detected
IGNORE_ENGLISH = False

HINDI_PROMPT = (
    "यह हिंदी भाषा में बोला गया है। "
    "कृपया हिंदी को देवनागरी लिपि में लिखें। "
    "उर्दू लिपि का उपयोग न करें।"
)

VAD_SETTINGS = {"min_silence_duration_ms": 500}


# =====================================================
# APP SETUP
# =====================================================

app = FastAPI(title="SAIL Meeting Translator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

print("Loading Whisper model...")

model = WhisperModel(
    MODEL_SIZE,
    device="cpu",
    compute_type="int8",
    cpu_threads=CPU_THREADS
)

# Only one transcription may use the model at a time
model_lock = threading.Lock()

print("Whisper model loaded successfully.")


LANGUAGE_NAMES = {
    "hi": "Hindi",
    "bn": "Bengali",
    "ko": "Korean",
    "en": "English",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "ja": "Japanese",
    "zh": "Chinese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ar": "Arabic",
    "ru": "Russian",
    "pt": "Portuguese"
}


def language_label(code):
    return LANGUAGE_NAMES.get(code, code.upper())


# =====================================================
# BASIC ENDPOINTS
# =====================================================

@app.get("/")
def home():
    return {"message": "SAIL Meeting Translator backend is running!"}


@app.get("/health")
def health():
    return {"status": "healthy"}


# =====================================================
# AUDIO PROCESSING
# =====================================================

def collect_segments(segments):
    result = []

    for segment in segments:
        text = segment.text.strip()

        if text:
            result.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": text
            })

    return result


def process_audio(audio):
    """
    Pass 1: translate to English and detect the language.
    Pass 2: write the original speech (only if not English).
    Returns: original, translated, language, probability
    """

    with model_lock:

        # ---- Pass 1: English translation + language detection ----
        translated_segments, info = model.transcribe(
            audio,
            task="translate",
            beam_size=1,
            vad_filter=True,
            vad_parameters=VAD_SETTINGS,
            condition_on_previous_text=False
        )

        translated = collect_segments(translated_segments)

        language = info.language
        probability = info.language_probability

        # No speech found in this chunk
        if not translated:
            return [], [], language, probability

        # English speech: original and translation are the same
        if language == "en":
            return translated, translated, language, probability

        transcribe_language = language
        extra = {}

        if language == "ur" and TREAT_URDU_AS_HINDI:
            transcribe_language = "hi"
            language = "hi"

        # FAST mode: stop here, no second pass
        if not SHOW_ORIGINAL_TEXT:
            return [], translated, language, probability

        # ---- Pass 2: original text in the original language ----

        if transcribe_language == "hi":
            extra["initial_prompt"] = HINDI_PROMPT

        original_segments, _ = model.transcribe(
            audio,
            task="transcribe",
            language=transcribe_language,
            beam_size=1,
            vad_filter=True,
            vad_parameters=VAD_SETTINGS,
            condition_on_previous_text=False,
            **extra
        )

        original = collect_segments(original_segments)

    return original, translated, language, probability


# =====================================================
# UPLOADED FILE TRANSLATION
# =====================================================

@app.post("/translate-audio")
async def translate_audio(file: UploadFile = File(...)):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No audio file selected."
        )

    suffix = os.path.splitext(file.filename)[1] or ".wav"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(await file.read())

        original, translated, language, probability = (
            await asyncio.to_thread(process_audio, temp_path)
        )

        return {
            "language": language,
            "language_name": language_label(language),
            "language_probability": round(probability, 3),
            "original_transcript": original,
            "translation": translated
        }

    except Exception as error:
        print("File translation error:", error)
        raise HTTPException(status_code=500, detail=str(error))

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# =====================================================
# LIVE BROWSER AUDIO
# =====================================================

@app.websocket("/ws/browser-live")
async def browser_live_translation(websocket: WebSocket):

    await websocket.accept()
    print("Live connection opened.")

    # Audio chunks wait here while the model is busy
    queue = asyncio.Queue(maxsize=MAX_WAITING_CHUNKS)

    async def worker():
        # Takes chunks from the queue, one at a time.
        # An error in one chunk never closes the connection.
        try:
            while True:
                audio, offset = await queue.get()

                try:
                    started = time.perf_counter()

                    original, translated, language, probability = (
                        await asyncio.to_thread(process_audio, audio)
                    )

                    print(
                        "Processed",
                        round(len(audio) / SAMPLE_RATE, 1),
                        "s of audio in",
                        round(time.perf_counter() - started, 1),
                        "s"
                    )
                except Exception as error:
                    print("Chunk processing error:", error)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Processing error: {error}"
                    })
                    continue

                if not original and not translated:
                    continue

                if language == "en" and IGNORE_ENGLISH:
                    continue

                name = language_label(language)

                print(
                    "Detected:", name,
                    "| Confidence:", round(probability, 2),
                    "| Original segments:", len(original),
                    "| English segments:", len(translated)
                )

                for segment in original:
                    await websocket.send_json({
                        "type": "original_transcript",
                        "language": language,
                        "language_name": name,
                        "start": round(offset + segment["start"], 2),
                        "end": round(offset + segment["end"], 2),
                        "text": segment["text"]
                    })

                for segment in translated:
                    await websocket.send_json({
                        "type": "translation",
                        "language": "en",
                        "language_name": "English",
                        "source_language_name": name,
                        "start": round(offset + segment["start"], 2),
                        "end": round(offset + segment["end"], 2),
                        "text": segment["text"]
                    })

                waiting = queue.qsize()

                await websocket.send_json({
                    "type": "status",
                    "message": (
                        "Listening to system audio..."
                        if waiting == 0
                        else f"Catching up: {waiting} audio chunk(s) "
                             "waiting. Nothing is skipped."
                    )
                })

        except asyncio.CancelledError:
            raise
        except Exception as error:
            print("Worker stopped:", error)

    worker_task = asyncio.create_task(worker())
    audio_offset = 0.0

    try:
        await websocket.send_json({
            "type": "status",
            "message": "Browser audio connection established."
        })

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                print("Browser closed the connection.")
                break

            audio_bytes = message.get("bytes")

            # Float32 audio needs complete 4-byte samples
            if not audio_bytes or len(audio_bytes) % 4 != 0:
                continue

            audio = np.frombuffer(
                audio_bytes,
                dtype=np.float32
            ).copy()

            if len(audio) == 0:
                continue

            duration = len(audio) / SAMPLE_RATE
            offset = audio_offset
            audio_offset += duration

            level = float(np.sqrt(np.mean(audio ** 2)))

            print(
                "Audio received:",
                round(duration, 2), "seconds",
                "| Level:", round(level, 4)
            )

            # Skip silence to save processing time
            if level < SILENCE_LEVEL:
                continue

            # Only if the line is extremely long (memory protection)
            if queue.full():
                try:
                    queue.get_nowait()
                    print("Line too long: dropped one old audio chunk.")
                    await websocket.send_json({
                        "type": "status",
                        "message": (
                            "Translation is far behind. "
                            "The oldest audio was skipped."
                        )
                    })
                except asyncio.QueueEmpty:
                    pass

            queue.put_nowait((audio, offset))

            if queue.qsize() >= 2:
                await websocket.send_json({
                    "type": "status",
                    "message": (
                        f"Catching up: {queue.qsize()} audio chunk(s) "
                        "waiting. Nothing is skipped."
                    )
                })

    except WebSocketDisconnect:
        print("Browser audio connection disconnected.")

    except Exception as error:
        print("Live connection error:", error)

    finally:
        worker_task.cancel()
        print("Live connection closed.")