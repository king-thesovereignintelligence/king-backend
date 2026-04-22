from langdetect import detect, LangDetectException
import logging
import re

logger = logging.getLogger("king.language")

# Hindi Unicode range for quick detection
HINDI_UNICODE_PATTERN = re.compile(r'[\u0900-\u097F]')


def detect_language(text: str) -> str:
    """
    Detect if text is Hindi ('hi') or English ('en').
    Uses both Unicode character detection and langdetect for accuracy.
    Returns 'hi' or 'en'.
    """
    if not text or not text.strip():
        return "en"

    # Fast path: if Devanagari script detected, it's Hindi
    if HINDI_UNICODE_PATTERN.search(text):
        return "hi"

    # Langdetect for romanized Hindi or ambiguous text
    try:
        lang = detect(text)
        if lang in ("hi", "mr", "ne"):  # Hindi, Marathi, Nepali — all Indic
            return "hi"
        return "en"
    except LangDetectException:
        return "en"


def format_for_ai(text: str, detected_lang: str) -> tuple[str, str]:
    """
    Returns (processed_text, language_tag).
    The text is passed unchanged to the AI — KING handles it.
    """
    return text, detected_lang


def is_hindi(text: str) -> bool:
    return detect_language(text) == "hi"
