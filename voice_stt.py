import httpx
from config import settings
import logging
import base64

logger = logging.getLogger("king.voice_stt")

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(audio_bytes: bytes,
                            filename: str = "audio.webm",
                            hint_language: str = "auto") -> dict:
    """
    Transcribe audio using Groq Whisper.
    Supports Hindi and English automatically.

    Returns:
        {"text": str, "language": "en"|"hi", "confidence": float}
    """
    if not audio_bytes:
        return {"text": "", "language": "en", "confidence": 0.0}

    # Groq Whisper language hints
    lang_param = None
    if hint_language == "hi":
        lang_param = "hi"
    elif hint_language == "en":
        lang_param = "en"
    # If auto, let Whisper detect

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (filename, audio_bytes, _get_mime(filename))}
            data = {
                "model": "whisper-large-v3",
                "response_format": "verbose_json",
            }
            if lang_param:
                data["language"] = lang_param

            response = await client.post(
                GROQ_STT_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files=files,
                data=data
            )

            if response.status_code != 200:
                logger.error(f"Groq STT error {response.status_code}: {response.text}")
                return {"text": "", "language": "en", "confidence": 0.0}

            result = response.json()
            text = result.get("text", "").strip()
            detected_lang = result.get("language", "english")

            # Normalize language code
            lang_code = "hi" if detected_lang in ("hindi", "hi") else "en"

            return {
                "text": text,
                "language": lang_code,
                "confidence": 0.9 if text else 0.0
            }

    except httpx.TimeoutException:
        logger.error("Groq STT timeout")
        return {"text": "", "language": "en", "confidence": 0.0}
    except Exception as e:
        logger.error(f"Groq STT error: {e}")
        return {"text": "", "language": "en", "confidence": 0.0}


def _get_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {
        "webm": "audio/webm",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/m4a",
        "mp4": "audio/mp4",
    }
    return mime_map.get(ext, "audio/webm")
