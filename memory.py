from database import (
    get_all_memory, get_recent_messages, set_memory, save_message
)
from typing import List, Dict
import json
import logging

logger = logging.getLogger("king.memory")

# Keys that are always included in context
PRIORITY_KEYS = [
    "user_goal", "current_project", "current_phase",
    "known_weakness", "known_strength", "last_major_decision",
    "training_status", "health_note", "mood_baseline"
]


def build_memory_context(limit: int = 8) -> str:
    """
    Build a compressed memory string for the AI system prompt.
    Prioritizes goal/project keys, then most recently updated.
    """
    all_mem = get_all_memory()
    if not all_mem:
        return "No persistent memory yet."

    parts = []

    # Priority keys first
    for key in PRIORITY_KEYS:
        if key in all_mem:
            parts.append(f"{key}: {all_mem[key]}")

    # Fill remaining slots with other keys
    other_keys = [k for k in all_mem if k not in PRIORITY_KEYS
                  and k != "last_seen"]
    for key in other_keys[:max(0, limit - len(parts))]:
        parts.append(f"{key}: {all_mem[key]}")

    return " | ".join(parts) if parts else "Memory initialized."


def build_conversation_context(limit: int = 12) -> List[Dict]:
    """Return recent messages formatted for AI API."""
    messages = get_recent_messages(limit)
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Map to standard roles
        if role == "king":
            role = "assistant"
        result.append({"role": role, "content": content})
    return result


def extract_and_save_facts(user_message: str,
                            king_reply: str) -> None:
    """
    Scan the exchange for extractable facts about RISEN.
    Simple keyword-based extraction — KING learns from every exchange.
    """
    msg_lower = user_message.lower()

    # Goal detection
    goal_triggers = ["my goal is", "i want to", "i'm working on",
                     "i'm building", "my mission is", "i plan to",
                     "मेरा लक्ष्य", "मैं बना रहा हूँ", "मैं चाहता हूँ"]
    for trigger in goal_triggers:
        if trigger in msg_lower:
            idx = msg_lower.find(trigger) + len(trigger)
            goal_text = user_message[idx:idx+150].strip()
            if goal_text:
                set_memory("user_goal", goal_text[:200])
            break

    # Project detection
    project_triggers = ["working on", "building", "creating",
                        "developing", "काम कर रहा हूँ", "बना रहा हूँ"]
    for trigger in project_triggers:
        if trigger in msg_lower:
            idx = msg_lower.find(trigger) + len(trigger)
            proj_text = user_message[idx:idx+100].strip()
            if proj_text:
                set_memory("current_project", proj_text[:150])
            break

    # Training/discipline note
    training_triggers = ["trained", "workout", "exercised", "gym",
                         "ran", "व्यायाम", "जिम"]
    for trigger in training_triggers:
        if trigger in msg_lower:
            set_memory("training_status", f"Active — last mention: {user_message[:100]}")
            break
