from database import get_mission, save_mission, now_iso
from typing import Optional, List, Dict
import json
import re
import logging

logger = logging.getLogger("king.purpose")

# ── Goal Extraction ────────────────────────────────────────────────────────────

GOAL_TRIGGERS = [
    ("goal", r"(?:my goal is|i want to achieve|i aim to)\s+(.+?)(?:\.|$)"),
    ("standard", r"(?:my standard is|i hold myself to|i commit to)\s+(.+?)(?:\.|$)"),
    ("non_negotiable", r"(?:non.negotiable|no matter what|always will|never will)\s+(.+?)(?:\.|$)"),
    ("phase", r"(?:this phase|right now i'm|currently focused on)\s+(.+?)(?:\.|$)"),
]

HINDI_GOAL_TRIGGERS = [
    r"(?:मेरा लक्ष्य है|मैं हासिल करना चाहता हूँ)\s+(.+?)(?:\।|$)",
    r"(?:मेरा मानक है|मैं खुद को)\s+(.+?)(?:\।|$)",
]


def extract_goal(message: str) -> Optional[Dict]:
    """
    Detect and extract goal/standard/intention from a message.
    Returns dict with type and extracted text, or None.
    """
    msg_lower = message.lower()

    for goal_type, pattern in GOAL_TRIGGERS:
        match = re.search(pattern, msg_lower)
        if match:
            extracted = match.group(1).strip()[:200]
            if len(extracted) > 10:
                return {"type": goal_type, "text": extracted,
                        "raw": message[:300]}

    for pattern in HINDI_GOAL_TRIGGERS:
        match = re.search(pattern, message)
        if match:
            extracted = match.group(1).strip()[:200]
            if len(extracted) > 5:
                return {"type": "goal", "text": extracted,
                        "raw": message[:300]}

    return None


def build_mission(all_goals: List[Dict]) -> str:
    """
    Synthesize extracted goals into a living mission statement.
    """
    if not all_goals:
        return "Mission undefined. RISEN has not yet declared his direction."

    goal_texts = [g["text"] for g in all_goals
                  if g.get("type") == "goal"]
    standard_texts = [g["text"] for g in all_goals
                      if g.get("type") == "standard"]
    phase_texts = [g["text"] for g in all_goals
                   if g.get("type") == "phase"]

    parts = []
    if goal_texts:
        parts.append(f"To {goal_texts[-1]}")
    if standard_texts:
        parts.append(f"holding to the standard: {standard_texts[-1]}")
    if phase_texts:
        parts.append(f"current phase: {phase_texts[-1]}")

    return ". ".join(parts) + "." if parts else "Mission in formation."


def check_violation(behavior: str,
                    standards: List[str]) -> Optional[str]:
    """
    Compare current behavior against stated standards.
    Returns confrontation string if violation detected.
    """
    if not standards:
        return None

    behavior_lower = behavior.lower()

    violation_pairs = [
        (["sleep early", "early to bed", "10pm"], ["stayed up", "late night", "2am", "3am"]),
        (["no junk food", "clean diet", "healthy"], ["ate junk", "pizza", "chips", "fast food"]),
        (["train every day", "workout daily"], ["skipped", "didn't train", "no workout"]),
        (["no social media", "limit phone"], ["scrolled", "instagram", "youtube hours"]),
        (["read daily", "one hour reading"], ["didn't read", "no reading", "skipped reading"]),
    ]

    for standard_triggers, violation_triggers in violation_pairs:
        standard_matches = any(t in s.lower() for t in standard_triggers
                                for s in standards)
        behavior_violation = any(t in behavior_lower
                                  for t in violation_triggers)

        if standard_matches and behavior_violation:
            relevant_standard = next(
                (s for s in standards
                 if any(t in s.lower() for t in standard_triggers)),
                standards[0]
            )
            return (f"You said: '{relevant_standard}'. "
                    f"You just did the opposite. What changed.")

    return None


def intervene(context: str) -> str:
    """
    Self-sabotage detected. Return intervention message.
    """
    context_lower = context.lower()

    if any(w in context_lower for w in ["giving up", "quit", "can't do this",
                                         "छोड़ना", "हार"]):
        return ("You are at the exact point where most people stop. "
                "That is not a coincidence. "
                "The resistance you feel right now is the signal that you are close.")

    if any(w in context_lower for w in ["distracted", "procrastinat",
                                         "wasting time", "ध्यान नहीं"]):
        return ("Name one thing. Do it. "
                "Clarity comes from action, not from planning the action.")

    if any(w in context_lower for w in ["doubt", "not sure", "maybe i",
                                         "संदेह", "शायद मैं"]):
        return ("Doubt is data. It tells you where the next growth point is. "
                "Act anyway.")

    return ("The pattern is clear. "
            "You already know what needs to happen. "
            "The question is whether you will do it.")


def no_coasting(achievement: str) -> str:
    """After an achievement, one sentence then redirect to next stage."""
    return "Noted. The next stage begins now."


def update_mission_from_goals(extracted_goals: List[Dict]) -> None:
    """Update the stored mission based on newly extracted goals."""
    if not extracted_goals:
        return

    existing = get_mission()
    existing_standards = []
    existing_non_neg = []
    existing_phase = ""

    if existing:
        try:
            existing_standards = json.loads(
                existing.get("standards", "[]"))
        except Exception:
            existing_standards = []
        try:
            existing_non_neg = json.loads(
                existing.get("non_negotiables", "[]"))
        except Exception:
            existing_non_neg = []
        existing_phase = existing.get("current_phase", "")

    # Merge new goals
    for g in extracted_goals:
        if g["type"] == "standard" and g["text"] not in existing_standards:
            existing_standards.append(g["text"])
        elif g["type"] == "non_negotiable" and g["text"] not in existing_non_neg:
            existing_non_neg.append(g["text"])
        elif g["type"] == "phase":
            existing_phase = g["text"]

    mission_text = build_mission(extracted_goals)
    save_mission(
        mission_statement=mission_text,
        standards=existing_standards[-10:],   # keep last 10
        non_negotiables=existing_non_neg[-5:],
        current_phase=existing_phase
    )


def build_purpose_context() -> str:
    """Build purpose summary for AI system prompt."""
    mission = get_mission()
    if not mission:
        return "Mission not yet declared."

    parts = [f"Mission: {mission.get('mission_statement', 'Undefined')}"]

    try:
        standards = json.loads(mission.get("standards", "[]"))
        if standards:
            parts.append(f"Standards: {'; '.join(standards[:3])}")
    except Exception:
        pass

    phase = mission.get("current_phase", "")
    if phase:
        parts.append(f"Phase: {phase}")

    return " | ".join(parts)
