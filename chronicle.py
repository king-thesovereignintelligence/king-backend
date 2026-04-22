from database import (
    save_chronicle_entry, save_mythology, get_current_arc,
    get_recent_chronicle, get_active_patterns, upsert_pattern,
    start_arc, now_iso
)
from typing import Optional, List, Dict
from datetime import datetime, timezone
import logging
import re

logger = logging.getLogger("king.chronicle")

# ── Significance Scoring ───────────────────────────────────────────────────────

VICTORY_KEYWORDS = [
    "finished", "completed", "launched", "shipped", "achieved", "won",
    "closed", "built", "released", "done", "succeeded", "passed",
    "पूरा किया", "जीत", "बनाया", "लॉन्च किया"
]
FAILURE_KEYWORDS = [
    "failed", "quit", "gave up", "lost", "rejected", "denied",
    "collapsed", "broke", "हार गया", "छोड़ दिया", "विफल"
]
MILESTONE_KEYWORDS = [
    "first time", "never done", "milestone", "level", "breakthrough",
    "crossed", "पहली बार", "उपलब्धि"
]
REVELATION_KEYWORDS = [
    "realized", "understood", "discovered", "insight", "now i see",
    "clicked", "समझ आया", "एहसास हुआ", "पता चला"
]

HIGH_SIGNIFICANCE_PHRASES = [
    "changed everything", "turning point", "never going back",
    "decided to", "committed to", "starting today", "from now on",
    "सब बदल गया", "निर्णय लिया", "आज से"
]


def score_significance(text: str) -> tuple[int, str]:
    """Score significance 1-10 and detect type."""
    text_lower = text.lower()
    score = 3
    entry_type = "PATTERN"

    for kw in VICTORY_KEYWORDS:
        if kw in text_lower:
            score = max(score, 7)
            entry_type = "VICTORY"
            break

    for kw in FAILURE_KEYWORDS:
        if kw in text_lower:
            score = max(score, 6)
            entry_type = "FAILURE"
            break

    for kw in MILESTONE_KEYWORDS:
        if kw in text_lower:
            score = max(score, 7)
            entry_type = "MILESTONE"
            break

    for kw in REVELATION_KEYWORDS:
        if kw in text_lower:
            score = max(score, 6)
            entry_type = "REVELATION"
            break

    for phrase in HIGH_SIGNIFICANCE_PHRASES:
        if phrase in text_lower:
            score = min(10, score + 2)
            break

    # Length as proxy for depth
    if len(text) > 300:
        score = min(10, score + 1)

    return score, entry_type


def detect_emotion(text: str) -> str:
    """Simple emotion tag detection."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["excited", "amazing", "great", "उत्साहित"]):
        return "DRIVE"
    if any(w in text_lower for w in ["tired", "exhausted", "drained", "थका"]):
        return "FATIGUE"
    if any(w in text_lower for w in ["angry", "frustrated", "fed up", "गुस्सा"]):
        return "TENSION"
    if any(w in text_lower for w in ["calm", "clear", "focused", "शांत"]):
        return "CLARITY"
    if any(w in text_lower for w in ["sad", "down", "low", "उदास"]):
        return "SHADOW"
    return "NEUTRAL"


def chronicle_analyze(conversation_text: str,
                       king_reply: str = "") -> Optional[Dict]:
    """
    Analyze a conversation exchange for chronicle-worthy events.
    Called after every significant exchange.
    Returns created entry dict if created, else None.
    """
    full_text = f"{conversation_text} {king_reply}"
    significance, entry_type = score_significance(conversation_text)

    if significance < 6:
        return None

    emotion = detect_emotion(conversation_text)
    arc = get_current_arc()
    arc_name = arc["name"] if arc else "The Unnamed Arc"

    # Create title from first meaningful sentence
    sentences = conversation_text.strip().split(".")
    title = sentences[0][:80].strip() if sentences else conversation_text[:80]

    entry_id = save_chronicle_entry(
        type_=entry_type,
        content=conversation_text[:500],
        title=title,
        arc_name=arc_name,
        emotion_tag=emotion,
        significance=significance,
        pattern_tag=""
    )

    result = {
        "type": entry_type,
        "significance": significance,
        "title": title,
        "entry_id": entry_id
    }

    # High significance → also create mythology entry
    if significance >= 8 and entry_id > 0:
        mythology_title = f"The Day of {title[:40]}"
        mythology_summary = (
            f"In the {arc_name} arc, RISEN {entry_type.lower()}. "
            f"Emotion: {emotion}. This moment carries weight."
        )
        save_mythology(entry_id, mythology_title, mythology_summary)
        result["mythology_created"] = True

    # Auto-start arc if none exists
    if not arc:
        start_arc("The First Arc")

    return result


def detect_pattern(history: List[Dict]) -> Optional[str]:
    """
    Detect behavioral patterns across conversation history.
    If same behavior appears 3+ times, register as pattern.
    """
    if len(history) < 6:
        return None

    # Extract user messages only
    user_msgs = [m["content"].lower() for m in history
                 if m.get("role") == "user"]

    pattern_checks = [
        ("avoidance", ["later", "not now", "maybe", "someday", "eventually",
                        "बाद में", "कभी", "शायद"]),
        ("self_doubt", ["can't", "unable", "don't know if", "not sure if",
                        "नहीं कर सकता", "पता नहीं"]),
        ("scattered_focus", ["also", "and then", "another thing", "wait",
                              "also need to", "और भी", "एक और"]),
        ("validation_seeking", ["right?", "don't you think", "what do you think",
                                 "is this good", "सही है न", "क्या लगता है"]),
    ]

    for pattern_name, triggers in pattern_checks:
        count = sum(
            1 for msg in user_msgs[-10:]
            if any(t in msg for t in triggers)
        )
        if count >= 3:
            description = {
                "avoidance": "Repeatedly deferring action with soft language.",
                "self_doubt": "Repeatedly questioning capability before attempting.",
                "scattered_focus": "Repeatedly shifting between multiple topics.",
                "validation_seeking": "Repeatedly seeking external confirmation."
            }.get(pattern_name, "Recurring behavioral signature.")

            upsert_pattern(pattern_name, description)
            return pattern_name

    return None


def build_chronicle_context() -> str:
    """Build chronicle summary for AI system prompt."""
    arc = get_current_arc()
    recent = get_recent_chronicle(5)
    patterns = get_active_patterns()

    parts = []

    if arc:
        started = arc.get("started_at", "")[:10]
        parts.append(f"Current arc: {arc['name']} (started {started})")
    else:
        parts.append("No active arc.")

    if recent:
        types = [e["type"] for e in recent]
        parts.append(f"Recent entries: {', '.join(types)}")

    if patterns:
        pnames = [p["name"] for p in patterns[:3]]
        parts.append(f"Active patterns: {', '.join(pnames)}")

    return " | ".join(parts) if parts else "Chronicle empty."


def generate_narrative() -> str:
    """Generate a full narrative summary of RISEN's journey."""
    arc = get_current_arc()
    entries = get_recent_chronicle(20)
    patterns = get_active_patterns()

    if not entries:
        return "The chronicle has not yet begun. The arc awaits its first entry."

    victories = [e for e in entries if e["type"] == "VICTORY"]
    failures = [e for e in entries if e["type"] == "FAILURE"]
    milestones = [e for e in entries if e["type"] == "MILESTONE"]
    revelations = [e for e in entries if e["type"] == "REVELATION"]

    arc_name = arc["name"] if arc else "unnamed arc"
    arc_start = arc["started_at"][:10] if arc else "unknown"

    # Calculate duration
    if arc and arc.get("started_at"):
        try:
            start_dt = datetime.fromisoformat(
                arc["started_at"].replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - start_dt).days
            duration = f"{days} days"
        except Exception:
            duration = "unknown duration"
    else:
        duration = "unknown duration"

    narrative_parts = [
        f"You are {duration} into the {arc_name} arc.",
        f"It began on {arc_start}.",
    ]

    if victories:
        v_titles = [e.get("title", "unnamed") for e in victories[:2]]
        narrative_parts.append(f"Victories recorded: {'; '.join(v_titles)}.")

    if failures:
        f_titles = [e.get("title", "unnamed") for e in failures[:1]]
        narrative_parts.append(f"Failures faced: {'; '.join(f_titles)}.")

    if revelations:
        r_titles = [e.get("title", "unnamed") for e in revelations[:1]]
        narrative_parts.append(f"Revelations: {'; '.join(r_titles)}.")

    if patterns:
        p_names = [p["name"] for p in patterns[:2]]
        narrative_parts.append(f"Pattern observed: {', '.join(p_names)}.")

    return " ".join(narrative_parts)


def proactive_opening(days_absent: int) -> Optional[str]:
    """If 3+ days absent, return an opening observation."""
    if days_absent < 3:
        return None

    arc = get_current_arc()
    patterns = get_active_patterns()

    arc_name = arc["name"] if arc else "your current arc"

    if days_absent >= 14:
        return (f"{days_absent} days of silence. "
                f"The {arc_name} waited. It still waits. What changed.")
    elif days_absent >= 7:
        return (f"A week passed. "
                f"The {arc_name} arc does not pause for absence. "
                f"What did you do with that time.")
    else:
        return (f"{days_absent} days. "
                f"The formation held. What happened.")
