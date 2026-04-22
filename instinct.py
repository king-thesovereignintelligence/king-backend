from database import (
    save_state_history, save_danger_flag, upsert_instinct_pattern,
    get_instinct_patterns, get_recent_chronicle, get_active_patterns,
    get_db, now_iso
)
from typing import Optional, List, Dict
import re
import logging

logger = logging.getLogger("king.instinct")


# ── Master State Detection ─────────────────────────────────────────────────────

def detect_state(message: str, session_history: List[Dict]) -> str:
    """
    Analyze message characteristics to detect RISEN's current state.
    Returns: SHARP | TIRED | STRESSED | DISTRACTED | LOCKED_IN
    """
    if not message:
        return "SHARP"

    word_count = len(message.split())
    char_count = len(message)
    has_punctuation = bool(re.search(r'[?!.]', message))
    question_count = message.count("?")
    sentence_count = max(1, len(re.split(r'[.!?]', message)))
    avg_sentence_len = word_count / sentence_count

    # Count session messages to gauge session depth
    session_length = len(session_history)

    signals = {
        "word_count": word_count,
        "avg_sentence_len": avg_sentence_len,
        "question_count": question_count,
        "session_length": session_length
    }

    # SHARP: longer messages, deep questions, complex vocabulary
    complex_words = len([w for w in message.split()
                          if len(w) > 7])
    if (word_count > 30 and complex_words > 3
            and question_count <= 2):
        save_state_history("SHARP", signals)
        return "SHARP"

    # TIRED: very short, simple words, low energy markers
    tired_markers = ["tired", "sleepy", "exhausted", "can't", "ugh",
                     "idk", "whatever", "थका", "नींद", "उफ्फ"]
    if (word_count < 15
            or any(m in message.lower() for m in tired_markers)):
        save_state_history("TIRED", signals)
        return "TIRED"

    # STRESSED: urgency markers, fragmented, exclamations
    stressed_markers = ["asap", "urgent", "quickly", "need this now",
                         "help", "stuck", "not working", "जल्दी", "अटक"]
    if (any(m in message.lower() for m in stressed_markers)
            or message.count("!") >= 2):
        save_state_history("STRESSED", signals)
        return "STRESSED"

    # DISTRACTED: topic jumping, very short, incomplete thoughts
    distracted_markers = ["also", "wait", "actually", "nevermind",
                           "forget it", "oh and", "रुको", "छोड़ो"]
    if (word_count < 10
            or sum(1 for m in distracted_markers
                   if m in message.lower()) >= 2):
        save_state_history("DISTRACTED", signals)
        return "DISTRACTED"

    # LOCKED_IN: sustained long messages, technical depth, flow
    if (session_length >= 5 and word_count > 40
            and question_count == 0 and complex_words > 5):
        save_state_history("LOCKED_IN", signals)
        return "LOCKED_IN"

    # Default
    save_state_history("SHARP", signals)
    return "SHARP"


def detect_self_deception(message: str) -> Optional[str]:
    """
    Detect self-deception patterns in the message.
    Returns a direct observation string if detected, else None.
    """
    msg_lower = message.lower()

    # Excess justification — explains too much unprompted
    justification_count = sum(1 for phrase in [
        "because", "the reason is", "i mean", "what i'm saying is",
        "basically", "technically", "the thing is", "it's just that",
        "क्योंकि", "मेरा मतलब"
    ] if phrase in msg_lower)

    if justification_count >= 3:
        upsert_instinct_pattern(
            "excess_justification",
            "Over-explains decisions unprompted — signal of self-doubt."
        )
        return ("You are explaining this more than the question requires. "
                "What are you defending against.")

    # Self-answering questions — asks then immediately answers
    self_answer_pattern = re.compile(
        r'\?.*?(i think|i guess|probably|maybe|i suppose|शायद|लगता है)',
        re.IGNORECASE
    )
    if self_answer_pattern.search(message):
        upsert_instinct_pattern(
            "self_answering_questions",
            "Asks questions and immediately answers them — avoiding confronting uncertainty."
        )
        return "You are asking and answering your own question. What is the real question underneath."

    # Circular rephrasing — same thought multiple times
    sentences = [s.strip() for s in re.split(r'[.!?]', message)
                 if len(s.strip()) > 15]
    if len(sentences) >= 3:
        # Simple similarity check: shared word ratio
        words_per_sentence = [set(s.lower().split()) for s in sentences]
        for i in range(len(words_per_sentence)):
            for j in range(i + 1, len(words_per_sentence)):
                a, b = words_per_sentence[i], words_per_sentence[j]
                if len(a) > 0 and len(b) > 0:
                    overlap = len(a & b) / min(len(a), len(b))
                    if overlap > 0.65:
                        upsert_instinct_pattern(
                            "circular_rephrasing",
                            "Rephrases the same thought — processing resistance."
                        )
                        return ("You have said this twice in different words. "
                                "Name what you are actually avoiding.")

    # Heavy hedging
    hedge_count = sum(1 for hedge in [
        "maybe", "perhaps", "might", "possibly", "kind of", "sort of",
        "i think", "i'm not sure", "शायद", "लगता है", "हो सकता है"
    ] if hedge in msg_lower)

    if hedge_count >= 4:
        upsert_instinct_pattern(
            "heavy_hedging",
            "Excessive qualifiers — avoiding commitment to clear positions."
        )
        return "Remove all the hedges from that statement. What are you actually saying."

    return None


def detect_danger(chronicle_data: Optional[Dict] = None) -> Optional[str]:
    """
    Detect danger signals from patterns and history.
    Returns warning string if danger detected, else None.
    """
    try:
        # Check for active unresolved danger flags
        res = get_db().table("danger_flags") \
            .select("*") \
            .eq("resolved", False) \
            .order("detected_at", desc=True) \
            .limit(1) \
            .execute()
        if res.data:
            flag = res.data[0]
            if flag["flag_type"] == "habit_gap":
                return f"Habit gap detected {flag['detected_at'][:10]}. The gap is widening."

        # Check patterns for compounding avoidance
        patterns = get_active_patterns()
        avoidance_patterns = [p for p in patterns
                               if "avoidance" in p.get("name", "")
                               or "procrastinat" in p.get("name", "")]
        if len(avoidance_patterns) >= 2:
            save_danger_flag(
                "compound_avoidance",
                "Multiple avoidance patterns active simultaneously."
            )
            return "Multiple avoidance patterns are compounding. This is not a coincidence."

        return None

    except Exception as e:
        logger.error(f"detect_danger error: {e}")
        return None


def detect_opportunity(recent_messages: List[Dict]) -> Optional[str]:
    """
    Find unconnected insights in recent messages that form a larger pattern.
    Returns the connection they haven't made yet.
    """
    if len(recent_messages) < 4:
        return None

    user_messages = [m["content"].lower() for m in recent_messages
                     if m.get("role") == "user"]

    # Look for adjacent concepts that connect
    theme_clusters = {
        "system_building": ["system", "process", "routine", "structure",
                             "automate", "workflow", "सिस्टम", "प्रक्रिया"],
        "identity_work": ["who i am", "becoming", "identity", "character",
                          "discipline", "standard", "पहचान", "अनुशासन"],
        "leverage": ["scale", "leverage", "multiply", "team", "delegate",
                     "resources", "लाभ उठाना"],
    }

    active_themes = []
    for theme, keywords in theme_clusters.items():
        hit_count = sum(
            1 for msg in user_messages[-8:]
            if any(kw in msg for kw in keywords)
        )
        if hit_count >= 2:
            active_themes.append(theme)

    if len(active_themes) >= 2:
        connection_map = {
            ("system_building", "identity_work"):
                "You are building systems and working on identity simultaneously. "
                "They are the same project. Your systems reflect your standards.",
            ("system_building", "leverage"):
                "The systems you are building are leverage. "
                "What you automate now compounds exponentially.",
            ("identity_work", "leverage"):
                "Identity work is the highest leverage investment. "
                "Character is the system that runs all other systems.",
        }
        key = tuple(sorted(active_themes[:2]))
        return connection_map.get(key)

    return None


def format_instinct(obs: str) -> str:
    """Format an instinct observation with proper prefix."""
    # Ensure it's 3 sentences max
    sentences = re.split(r'(?<=[.!?]) +', obs.strip())
    truncated = " ".join(sentences[:3])
    return f"[INSTINCT] {truncated}"


def build_instinct_context() -> str:
    """Build instinct summary for AI system prompt."""
    patterns = get_instinct_patterns()
    if not patterns:
        return "No patterns detected yet."

    high_conf = [p for p in patterns if p.get("confidence", 0) > 0.6]
    if not high_conf:
        return "Patterns forming — confidence building."

    names = [p["pattern_name"] for p in high_conf[:3]]
    return f"Active high-confidence patterns: {', '.join(names)}"
