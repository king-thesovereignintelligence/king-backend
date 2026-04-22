import google.generativeai as genai
from groq import AsyncGroq
from config import settings
from personality import build_system_prompt, process_ego_cycle
from language import detect_language
from memory import (build_memory_context, build_conversation_context,
                     extract_and_save_facts)
from chronicle import (chronicle_analyze, detect_pattern,
                        build_chronicle_context, proactive_opening)
from instinct import (detect_state, detect_self_deception,
                       detect_danger, detect_opportunity,
                       format_instinct, build_instinct_context)
from purpose import (extract_goal, update_mission_from_goals,
                      check_violation, build_purpose_context)
from database import (save_message, get_recent_messages, update_last_seen,
                       get_days_since_last_seen, get_mission)
import json
import re
import logging
from typing import Optional

logger = logging.getLogger("king.brain")

# Configure Gemini
genai.configure(api_key=settings.gemini_api_key)

# Groq async client
_groq_client = AsyncGroq(api_key=settings.groq_api_key)

# ── Markdown stripper for voice ────────────────────────────────────────────────

def strip_markdown(text: str) -> str:
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Voice state detection from reply ──────────────────────────────────────────

def determine_voice_state(master_state: str, reply: str) -> str:
    """Map master state and reply content to TTS voice state."""
    state_map = {
        "SHARP":      "sharp",
        "TIRED":      "tired",
        "STRESSED":   "stressed",
        "DISTRACTED": "tired",
        "LOCKED_IN":  "locked_in",
    }
    base = state_map.get(master_state, "sharp")

    # Override for important truths
    important_signals = [
        "you said", "you are currently", "what changed",
        "pattern", "self-sabotage", "danger", "[instinct]", "[ego]"
    ]
    if any(s in reply.lower() for s in important_signals):
        return "important"

    return base


# ── Formation state detection ──────────────────────────────────────────────────

def determine_formation_state(master_state: str) -> str:
    """Map master state to phone formation seal visual state."""
    mapping = {
        "SHARP":      "online",
        "TIRED":      "online",
        "STRESSED":   "restless",
        "DISTRACTED": "online",
        "LOCKED_IN":  "aligned",
    }
    return mapping.get(master_state, "online")


# ── Core AI call ───────────────────────────────────────────────────────────────

async def _call_gemini(system_prompt: str,
                        messages: list) -> Optional[str]:
    """Attempt Gemini 2.0 Flash."""
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=system_prompt
        )
        # Build conversation history for Gemini
        gemini_history = []
        for msg in messages[:-1]:  # all but last
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        chat = model.start_chat(history=gemini_history)
        last_msg = messages[-1]["content"] if messages else ""

        response = chat.send_message(
            last_msg,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.72,
            ),
            request_options={"timeout": 10}
        )
        return response.text
    except Exception as e:
        logger.warning(f"Gemini failed: {e}")
        return None


async def _call_groq(system_prompt: str,
                      messages: list) -> Optional[str]:
    """Attempt Groq llama-3.3-70b-versatile."""
    try:
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)

        response = await _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=api_messages,
            max_tokens=1024,
            temperature=0.72,
            timeout=10
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq failed: {e}")
        return None


# ── Main process function ──────────────────────────────────────────────────────

async def process(user_input: str,
                   source: str = "phone",
                   hint_language: Optional[str] = None) -> dict:
    """
    Full processing pipeline for a user message.
    Returns complete response dict.
    """
    # 1. Detect language
    lang = hint_language if hint_language in ("en", "hi") \
        else detect_language(user_input)

    # 2. Save user message
    save_message("user", user_input, lang)

    # 3. Get conversation context
    history = get_recent_messages(20)
    conversation = build_conversation_context(16)

    # 4. Detect master state
    master_state = detect_state(user_input, history)

    # 5. Process ego cycle
    ego_state, ego_interjection = process_ego_cycle(user_input, history, lang)

    # 6. Check self-deception
    self_deception = detect_self_deception(user_input)

    # 7. Extract and store goals
    extracted_goal = extract_goal(user_input)
    if extracted_goal:
        update_mission_from_goals([extracted_goal])

    # 8. Check purpose violations
    mission = get_mission()
    standards = []
    if mission:
        import json as json_mod
        try:
            standards = json_mod.loads(mission.get("standards", "[]"))
        except Exception:
            standards = []
    purpose_violation = check_violation(user_input, standards)

    # 9. Detect danger
    danger = detect_danger()

    # 10. Detect opportunity in recent messages
    opportunity = detect_opportunity(history[-10:] if history else [])

    # 11. Build all context strings
    memory_ctx = build_memory_context()
    chronicle_ctx = build_chronicle_context()
    purpose_ctx = build_purpose_context()
    instinct_ctx = build_instinct_context()

    # 12. Check days absent
    days_absent = get_days_since_last_seen()
    update_last_seen()

    # 13. Check for proactive opening
    proactive = proactive_opening(days_absent)

    # 14. Build instinct flag for response
    instinct_flag = None
    if self_deception:
        instinct_flag = format_instinct(self_deception)
    elif danger:
        instinct_flag = format_instinct(danger)
    elif opportunity:
        instinct_flag = format_instinct(opportunity)
    elif purpose_violation:
        instinct_flag = format_instinct(purpose_violation)

    # 15. Build system prompt
    system_prompt = build_system_prompt(
        ego_state=ego_state,
        master_state=master_state,
        lang=lang,
        memory_context=memory_ctx,
        chronicle_context=chronicle_ctx,
        purpose_context=purpose_ctx,
        instinct_context=instinct_ctx,
        days_since_last=days_absent
    )

    # 16. Prepare conversation messages
    # Inject proactive opening into system if applicable
    if proactive and days_absent >= 3:
        system_prompt += f"\n\n[OPENING NOTE: {proactive}]"

    # Add current user message to conversation
    if not conversation or conversation[-1].get("content") != user_input:
        conversation.append({"role": "user", "content": user_input})

    # 17. Call AI chain
    raw_reply = await _call_gemini(system_prompt, conversation)
    if not raw_reply:
        raw_reply = await _call_groq(system_prompt, conversation)
    if not raw_reply:
        fallback = ("All AI paths are closed. Standing by."
                    if lang == "en"
                    else "सभी AI मार्ग बंद हैं। प्रतीक्षारत।")
        raw_reply = fallback

    # 18. Post-process reply
    reply = raw_reply.strip()
    voice_reply = strip_markdown(reply)

    # 19. Save KING's response
    save_message("king", reply, lang)

    # 20. Extract and save facts from exchange
    extract_and_save_facts(user_input, reply)

    # 21. Chronicle analysis (background — non-blocking)
    try:
        chronicle_analyze(user_input, reply)
        detect_pattern(history)
    except Exception as e:
        logger.error(f"Chronicle analysis error: {e}")

    # 22. Detect action from reply
    action, action_params = _detect_action(reply, user_input)

    # 23. Determine output states
    voice_state = determine_voice_state(master_state, reply)
    formation_state = determine_formation_state(master_state)

    return {
        "reply": reply,
        "voice_reply": voice_reply,
        "language": lang,
        "action": action,
        "action_params": action_params,
        "ego_interjection": ego_interjection,
        "instinct_flag": instinct_flag,
        "voice_state": voice_state,
        "formation_state": formation_state,
        "master_state": master_state,
    }


def _detect_action(reply: str, user_input: str) -> tuple:
    """
    Detect if reply implies a system action.
    Returns (action_name, params) or (None, {})
    """
    user_lower = user_input.lower()

    app_keywords = {
        "open chrome": ("open_app", {"name": "chrome"}),
        "open spotify": ("open_app", {"name": "spotify"}),
        "open discord": ("open_app", {"name": "discord"}),
        "open vscode": ("open_app", {"name": "vscode"}),
        "open terminal": ("open_app", {"name": "terminal"}),
        "open notepad": ("open_app", {"name": "notepad"}),
        "open calculator": ("open_app", {"name": "calculator"}),
        "open brave": ("open_app", {"name": "brave"}),
        "open settings": ("open_app", {"name": "settings"}),
        "take screenshot": ("screenshot", {}),
        "lock screen": ("lock_screen", {}),
        "lock the screen": ("lock_screen", {}),
    }

    for trigger, (action, params) in app_keywords.items():
        if trigger in user_lower:
            return action, params

    # Volume
    vol_match = re.search(r'(?:set volume|volume to)\s+(\d+)', user_lower)
    if vol_match:
        return "set_volume", {"level": int(vol_match.group(1))}

    # Brightness
    bright_match = re.search(r'(?:set brightness|brightness to)\s+(\d+)',
                               user_lower)
    if bright_match:
        return "set_brightness", {"level": int(bright_match.group(1))}

    # Web search
    search_match = re.search(r'(?:search for|google|look up)\s+(.+)',
                               user_lower)
    if search_match:
        return "web_search", {"query": search_match.group(1)}

    return None, {}
