from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Command / Chat ─────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    text: str
    language: Optional[str] = None   # "en" | "hi" — if already detected client-side
    source: str = "phone"            # "phone" | "pc_agent" | "api"


class CommandResponse(BaseModel):
    reply: str
    language: str                    # language of the reply
    action: Optional[str] = None
    action_params: Optional[dict] = None
    ego_interjection: Optional[str] = None
    instinct_flag: Optional[str] = None
    voice_state: str = "sharp"
    formation_state: str = "online"  # maps to FormationSeal visual state


# ── Memory ─────────────────────────────────────────────────────────────────────

class MemoryItem(BaseModel):
    key: str
    value: str


class MemoryResponse(BaseModel):
    key: str
    value: str
    updated_at: str


# ── Reminders ──────────────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    text: str
    remind_at: str    # ISO 8601


class ReminderResponse(BaseModel):
    id: int
    text: str
    remind_at: str
    done: bool
    created_at: str


# ── Chronicle ──────────────────────────────────────────────────────────────────

class ChronicleEntry(BaseModel):
    id: int
    type: str
    timestamp: str
    arc_name: Optional[str]
    title: Optional[str]
    content: str
    emotion_tag: Optional[str]
    significance: int
    pattern_tag: Optional[str]


class Arc(BaseModel):
    id: int
    name: str
    started_at: str
    ended_at: Optional[str]
    outcome: Optional[str]
    summary: Optional[str]


class ChronicleResponse(BaseModel):
    current_arc: Optional[Arc]
    recent_entries: List[ChronicleEntry]
    patterns: List[dict]
    narrative: str


# ── Sync ───────────────────────────────────────────────────────────────────────

class SyncPush(BaseModel):
    type: str = "sync_push"
    data: dict
    timestamp: int    # unix ms


class FullSyncDump(BaseModel):
    type: str = "full_sync"
    messages: List[dict]
    memory: List[dict]
    reminders: List[dict]
    chronicle: List[dict]
    ego_state: dict
    timestamp: int


# ── System ─────────────────────────────────────────────────────────────────────

class SystemExecuteRequest(BaseModel):
    action: str
    params: Optional[dict] = {}


class SystemInfoResponse(BaseModel):
    cpu_percent: float
    ram_percent: float
    battery_percent: Optional[float]
    uptime_hours: float
    pc_agent_connected: bool
