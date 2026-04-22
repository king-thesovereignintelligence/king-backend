from fastapi import FastAPI, HTTPException, Depends, WebSocket, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from models import (
    LoginRequest, TokenResponse, CommandRequest, CommandResponse,
    MemoryItem, MemoryResponse, ReminderCreate, ReminderResponse,
    ChronicleResponse, SystemExecuteRequest, SystemInfoResponse
)
from auth import verify_token, verify_password, create_access_token
from brain import process
from database import (
    get_all_memory, set_memory, get_all_messages,
    create_reminder, get_pending_reminders, export_all_data,
    get_current_arc, get_recent_chronicle, get_active_patterns,
    get_ego_state
)
from chronicle import generate_narrative
from reminders import (start_reminder_scheduler, stop_reminder_scheduler,
                        set_notify_callback, parse_reminder_time)
from sync import (handle_phone_sync, handle_pc_agent,
                   broadcast_to_phones, send_to_pc_agent,
                   get_pc_agent_status)
from voice_stt import transcribe_audio
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s"
)
logger = logging.getLogger("king.main")


# ── Reminder notification callback ────────────────────────────────────────────

async def reminder_notify(reminder: dict) -> None:
    """Called when a reminder is due — push to phone and PC agent."""
    msg = {
        "type": "reminder_due",
        "text": reminder["text"],
        "id": reminder["id"]
    }
    await broadcast_to_phones(msg)
    await send_to_pc_agent(msg)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("KING starting up...")
    set_notify_callback(reminder_notify)
    start_reminder_scheduler()
    logger.info("KING fully online.")
    yield
    logger.info("KING shutting down...")
    stop_reminder_scheduler()


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="KING",
    description="Sovereign Intelligence",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    if not verify_password(request.password):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = create_access_token()
    return TokenResponse(access_token=token)


# ── Command (text) ─────────────────────────────────────────────────────────────

@app.post("/command", response_model=CommandResponse)
async def command(request: CommandRequest,
                   _: str = Depends(verify_token)):
    result = await process(
        request.text,
        source=request.source,
        hint_language=request.language
    )
    return CommandResponse(
        reply=result["reply"],
        language=result["language"],
        action=result.get("action"),
        action_params=result.get("action_params"),
        ego_interjection=result.get("ego_interjection"),
        instinct_flag=result.get("instinct_flag"),
        voice_state=result.get("voice_state", "sharp"),
        formation_state=result.get("formation_state", "online"),
    )


# ── Voice transcription ────────────────────────────────────────────────────────

@app.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    _: str = Depends(verify_token)
):
    audio_bytes = await audio.read()
    result = await transcribe_audio(audio_bytes, audio.filename or "audio.webm")
    return result


# ── Voice command (transcribe + process) ──────────────────────────────────────

@app.post("/voice/command")
async def voice_command(
    audio: UploadFile = File(...),
    _: str = Depends(verify_token)
):
    audio_bytes = await audio.read()
    stt_result = await transcribe_audio(
        audio_bytes, audio.filename or "audio.webm"
    )
    if not stt_result.get("text"):
        return {"error": "Could not transcribe audio.", "reply": ""}

    result = await process(
        stt_result["text"],
        source="phone",
        hint_language=stt_result.get("language")
    )
    result["transcribed_text"] = stt_result["text"]
    return result


# ── Memory ─────────────────────────────────────────────────────────────────────

@app.get("/memory")
async def get_memory_all(_: str = Depends(verify_token)):
    return get_all_memory()


@app.post("/memory")
async def save_memory_item(item: MemoryItem,
                            _: str = Depends(verify_token)):
    set_memory(item.key, item.value)
    return {"status": "saved", "key": item.key}


# ── Reminders ──────────────────────────────────────────────────────────────────

@app.get("/reminders")
async def list_reminders(_: str = Depends(verify_token)):
    return get_pending_reminders()


@app.post("/reminders")
async def add_reminder(reminder: ReminderCreate,
                        _: str = Depends(verify_token)):
    parsed_time = parse_reminder_time(reminder.remind_at)
    if not parsed_time:
        raise HTTPException(status_code=400,
                            detail="Could not parse reminder time.")
    created = create_reminder(reminder.text, parsed_time)
    return created


# ── Chronicle ──────────────────────────────────────────────────────────────────

@app.get("/chronicle")
async def get_chronicle(_: str = Depends(verify_token)):
    arc = get_current_arc()
    entries = get_recent_chronicle(20)
    patterns = get_active_patterns()
    narrative = generate_narrative()

    from models import Arc, ChronicleEntry
    arc_model = None
    if arc:
        arc_model = {
            "id": arc.get("id", 0),
            "name": arc.get("name", ""),
            "started_at": arc.get("started_at", ""),
            "ended_at": arc.get("ended_at"),
            "outcome": arc.get("outcome"),
            "summary": arc.get("summary"),
        }

    return {
        "current_arc": arc_model,
        "recent_entries": entries,
        "patterns": patterns,
        "narrative": narrative
    }


# ── System info ────────────────────────────────────────────────────────────────

@app.get("/system/info")
async def system_info(_: str = Depends(verify_token)):
    pc_status = get_pc_agent_status()
    return {
        "pc_agent_connected": pc_status["connected"],
        "pc_agent_last_seen": pc_status.get("last_seen"),
        "cloud_status": "online"
    }


# ── System execute (relay to PC agent) ────────────────────────────────────────

@app.post("/system/execute")
async def system_execute(request: SystemExecuteRequest,
                          _: str = Depends(verify_token)):
    sent = await send_to_pc_agent({
        "type": "execute",
        "action": request.action,
        "params": request.params or {}
    })
    if not sent:
        raise HTTPException(
            status_code=503,
            detail="PC agent not connected. Start the PC agent on your laptop."
        )
    return {"status": "sent", "action": request.action}


# ── Sync dump ──────────────────────────────────────────────────────────────────

@app.get("/sync/dump")
async def sync_dump(_: str = Depends(verify_token)):
    return export_all_data()


# ── Ego state ──────────────────────────────────────────────────────────────────

@app.get("/ego/state")
async def ego_state_get(_: str = Depends(verify_token)):
    return get_ego_state()


# ── Conversation history ───────────────────────────────────────────────────────

@app.get("/conversation/history")
async def conversation_history(_: str = Depends(verify_token)):
    return get_all_messages()


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "online", "service": "KING"}


# ── WebSocket: Phone chat ──────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Real-time chat WebSocket for phone."""
    # Validate token from query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return

    from auth import verify_token as _vt
    from jose import JWTError
    try:
        from jose import jwt
        from config import settings
        payload = jwt.decode(token, settings.jwt_secret,
                              algorithms=[settings.jwt_algorithm])
        if payload.get("sub") != "risen":
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    import json as json_mod

    try:
        while True:
            raw = await websocket.receive_text()
            data = json_mod.loads(raw)
            text = data.get("text", "")
            lang = data.get("language")

            if not text:
                continue

            # Stream thinking state to phone
            await websocket.send_json({"type": "state", "state": "thinking"})

            result = await process(text, source="phone", hint_language=lang)

            await websocket.send_json({
                "type": "message",
                "role": "king",
                "content": result["reply"],
                "language": result["language"],
                "voice_state": result["voice_state"],
                "formation_state": result["formation_state"],
                "ego_interjection": result.get("ego_interjection"),
                "instinct_flag": result.get("instinct_flag"),
                "action": result.get("action"),
                "action_params": result.get("action_params"),
            })

            await websocket.send_json({"type": "state", "state": "online"})

    except Exception as e:
        logger.error(f"ws_chat error: {e}")


# ── WebSocket: Phone sync ──────────────────────────────────────────────────────

@app.websocket("/ws/sync")
async def ws_sync(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        from jose import jwt
        from config import settings
        payload = jwt.decode(token, settings.jwt_secret,
                              algorithms=[settings.jwt_algorithm])
        if payload.get("sub") != "risen":
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await handle_phone_sync(websocket)


# ── WebSocket: PC Agent ────────────────────────────────────────────────────────

@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        from jose import jwt
        from config import settings
        payload = jwt.decode(token, settings.jwt_secret,
                              algorithms=[settings.jwt_algorithm])
        if payload.get("sub") != "risen":
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await handle_pc_agent(websocket, reminder_callback=reminder_notify)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7777, reload=False)
