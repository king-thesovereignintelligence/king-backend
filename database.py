from supabase import create_client, Client
from config import settings
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger("king.database")

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Conversation History ───────────────────────────────────────────────────────

def save_message(role: str, content: str, lang: str = "en") -> None:
    try:
        get_db().table("conversation_history").insert({
            "role": role,
            "content": content,
            "lang": lang,
            "created_at": now_iso()
        }).execute()
    except Exception as e:
        logger.error(f"save_message error: {e}")


def get_recent_messages(limit: int = 20) -> List[Dict]:
    try:
        res = get_db().table("conversation_history") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return list(reversed(res.data or []))
    except Exception as e:
        logger.error(f"get_recent_messages error: {e}")
        return []


def get_all_messages() -> List[Dict]:
    try:
        res = get_db().table("conversation_history") \
            .select("*") \
            .order("created_at") \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_all_messages error: {e}")
        return []


def clear_old_messages(keep_last: int = 200) -> None:
    """Keep only the most recent N messages to prevent bloat."""
    try:
        res = get_db().table("conversation_history") \
            .select("id") \
            .order("created_at", desc=True) \
            .execute()
        all_ids = [r["id"] for r in (res.data or [])]
        if len(all_ids) > keep_last:
            to_delete = all_ids[keep_last:]
            for id_ in to_delete:
                get_db().table("conversation_history") \
                    .delete().eq("id", id_).execute()
    except Exception as e:
        logger.error(f"clear_old_messages error: {e}")


# ── User Memory ────────────────────────────────────────────────────────────────

def set_memory(key: str, value: str) -> None:
    try:
        get_db().table("user_memory").upsert({
            "key": key,
            "value": value,
            "updated_at": now_iso()
        }).execute()
    except Exception as e:
        logger.error(f"set_memory error: {e}")


def get_memory(key: str) -> Optional[str]:
    try:
        res = get_db().table("user_memory") \
            .select("value") \
            .eq("key", key) \
            .single() \
            .execute()
        return res.data["value"] if res.data else None
    except Exception:
        return None


def get_all_memory() -> Dict[str, str]:
    try:
        res = get_db().table("user_memory").select("*").execute()
        return {r["key"]: r["value"] for r in (res.data or [])}
    except Exception as e:
        logger.error(f"get_all_memory error: {e}")
        return {}


# ── Ego State ──────────────────────────────────────────────────────────────────

def get_ego_state() -> Dict:
    try:
        res = get_db().table("ego_state") \
            .select("*") \
            .eq("id", 1) \
            .single() \
            .execute()
        if res.data:
            return res.data
        # Initialize
        default = {"id": 1, "mood": "dormant", "counter": 0,
                   "threshold": 10, "updated_at": now_iso()}
        get_db().table("ego_state").insert(default).execute()
        return default
    except Exception as e:
        logger.error(f"get_ego_state error: {e}")
        return {"mood": "dormant", "counter": 0, "threshold": 10}


def update_ego_state(mood: str, counter: int, threshold: int) -> None:
    try:
        get_db().table("ego_state").upsert({
            "id": 1,
            "mood": mood,
            "counter": counter,
            "threshold": threshold,
            "updated_at": now_iso()
        }).execute()
    except Exception as e:
        logger.error(f"update_ego_state error: {e}")


# ── Reminders ──────────────────────────────────────────────────────────────────

def create_reminder(text: str, remind_at: str) -> Dict:
    try:
        res = get_db().table("reminders").insert({
            "text": text,
            "remind_at": remind_at,
            "done": False,
            "created_at": now_iso()
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"create_reminder error: {e}")
        return {}


def get_pending_reminders() -> List[Dict]:
    try:
        res = get_db().table("reminders") \
            .select("*") \
            .eq("done", False) \
            .order("remind_at") \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_pending_reminders error: {e}")
        return []


def get_due_reminders() -> List[Dict]:
    try:
        now = now_iso()
        res = get_db().table("reminders") \
            .select("*") \
            .eq("done", False) \
            .lte("remind_at", now) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_due_reminders error: {e}")
        return []


def mark_reminder_done(reminder_id: int) -> None:
    try:
        get_db().table("reminders") \
            .update({"done": True}) \
            .eq("id", reminder_id) \
            .execute()
    except Exception as e:
        logger.error(f"mark_reminder_done error: {e}")


# ── Master Mission (Purpose) ───────────────────────────────────────────────────

def get_mission() -> Optional[Dict]:
    try:
        res = get_db().table("master_mission") \
            .select("*") \
            .limit(1) \
            .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"get_mission error: {e}")
        return None


def save_mission(mission_statement: str, standards: list,
                 non_negotiables: list, current_phase: str) -> None:
    try:
        existing = get_mission()
        data = {
            "mission_statement": mission_statement,
            "standards": json.dumps(standards),
            "non_negotiables": json.dumps(non_negotiables),
            "current_phase": current_phase,
            "last_reviewed": now_iso()
        }
        if existing:
            get_db().table("master_mission") \
                .update(data).eq("id", existing["id"]).execute()
        else:
            data["declared_at"] = now_iso()
            get_db().table("master_mission").insert(data).execute()
    except Exception as e:
        logger.error(f"save_mission error: {e}")


# ── Chronicle ──────────────────────────────────────────────────────────────────

def save_chronicle_entry(type_: str, content: str, title: str = "",
                         arc_name: str = "", emotion_tag: str = "",
                         significance: int = 5,
                         pattern_tag: str = "") -> int:
    try:
        res = get_db().table("chronicle_entries").insert({
            "type": type_,
            "timestamp": now_iso(),
            "arc_name": arc_name,
            "title": title,
            "content": content,
            "emotion_tag": emotion_tag,
            "significance": significance,
            "pattern_tag": pattern_tag
        }).execute()
        return res.data[0]["id"] if res.data else -1
    except Exception as e:
        logger.error(f"save_chronicle_entry error: {e}")
        return -1


def save_mythology(entry_id: int, title: str, summary: str) -> None:
    try:
        get_db().table("mythology").insert({
            "entry_id": entry_id,
            "title": title,
            "summary": summary,
            "timestamp": now_iso()
        }).execute()
    except Exception as e:
        logger.error(f"save_mythology error: {e}")


def get_current_arc() -> Optional[Dict]:
    try:
        res = get_db().table("arcs") \
            .select("*") \
            .is_("ended_at", "null") \
            .order("started_at", desc=True) \
            .limit(1) \
            .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"get_current_arc error: {e}")
        return None


def start_arc(name: str) -> None:
    try:
        get_db().table("arcs").insert({
            "name": name,
            "started_at": now_iso()
        }).execute()
    except Exception as e:
        logger.error(f"start_arc error: {e}")


def end_arc(arc_id: int, outcome: str, summary: str) -> None:
    try:
        get_db().table("arcs").update({
            "ended_at": now_iso(),
            "outcome": outcome,
            "summary": summary
        }).eq("id", arc_id).execute()
    except Exception as e:
        logger.error(f"end_arc error: {e}")


def get_recent_chronicle(limit: int = 10) -> List[Dict]:
    try:
        res = get_db().table("chronicle_entries") \
            .select("*") \
            .order("timestamp", desc=True) \
            .limit(limit) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_recent_chronicle error: {e}")
        return []


def get_active_patterns() -> List[Dict]:
    try:
        res = get_db().table("pattern_library") \
            .select("*") \
            .eq("status", "active") \
            .order("frequency", desc=True) \
            .limit(5) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_active_patterns error: {e}")
        return []


def upsert_pattern(name: str, description: str) -> None:
    try:
        existing = get_db().table("pattern_library") \
            .select("*").eq("name", name).execute()
        if existing.data:
            p = existing.data[0]
            get_db().table("pattern_library").update({
                "frequency": p["frequency"] + 1,
                "last_seen": now_iso()
            }).eq("id", p["id"]).execute()
        else:
            get_db().table("pattern_library").insert({
                "name": name,
                "description": description,
                "first_seen": now_iso(),
                "frequency": 1,
                "last_seen": now_iso(),
                "status": "active"
            }).execute()
    except Exception as e:
        logger.error(f"upsert_pattern error: {e}")


# ── Instinct ───────────────────────────────────────────────────────────────────

def save_state_history(detected_state: str, signals: dict) -> None:
    try:
        get_db().table("state_history").insert({
            "timestamp": now_iso(),
            "detected_state": detected_state,
            "signals": json.dumps(signals)
        }).execute()
    except Exception as e:
        logger.error(f"save_state_history error: {e}")


def save_danger_flag(flag_type: str, context: str) -> None:
    try:
        get_db().table("danger_flags").insert({
            "flag_type": flag_type,
            "detected_at": now_iso(),
            "resolved": False,
            "context": context
        }).execute()
    except Exception as e:
        logger.error(f"save_danger_flag error: {e}")


def get_instinct_patterns() -> List[Dict]:
    try:
        res = get_db().table("instinct_patterns") \
            .select("*") \
            .order("confidence", desc=True) \
            .limit(10) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_instinct_patterns error: {e}")
        return []


def upsert_instinct_pattern(pattern_name: str,
                             trigger_description: str,
                             confidence_delta: float = 0.1) -> None:
    try:
        existing = get_db().table("instinct_patterns") \
            .select("*").eq("pattern_name", pattern_name).execute()
        if existing.data:
            p = existing.data[0]
            new_conf = min(1.0, p["confidence"] + confidence_delta)
            get_db().table("instinct_patterns").update({
                "confidence": new_conf,
                "times_detected": p["times_detected"] + 1,
                "last_triggered": now_iso()
            }).eq("id", p["id"]).execute()
        else:
            get_db().table("instinct_patterns").insert({
                "pattern_name": pattern_name,
                "trigger_description": trigger_description,
                "confidence": 0.5,
                "times_detected": 1,
                "last_triggered": now_iso()
            }).execute()
    except Exception as e:
        logger.error(f"upsert_instinct_pattern error: {e}")


# ── Full Sync Export ───────────────────────────────────────────────────────────

def export_all_data() -> Dict:
    """Full data dump for phone sync."""
    from datetime import timezone
    return {
        "messages": get_recent_messages(100),
        "memory": [{"key": k, "value": v} for k, v in get_all_memory().items()],
        "reminders": get_pending_reminders(),
        "chronicle": get_recent_chronicle(20),
        "ego_state": get_ego_state(),
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
    }


# ── Last Seen ──────────────────────────────────────────────────────────────────

def update_last_seen() -> None:
    set_memory("last_seen", now_iso())


def get_days_since_last_seen() -> int:
    last = get_memory("last_seen")
    if not last:
        return 0
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        return (now_dt - last_dt).days
    except Exception:
        return 0
