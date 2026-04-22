from fastapi import WebSocket, WebSocketDisconnect
from database import export_all_data, set_memory, create_reminder, now_iso
import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("king.sync")

# ── Connected clients registry ─────────────────────────────────────────────────

_phone_connections: list[WebSocket] = []
_pc_agent_connection: Optional[WebSocket] = None
_pc_agent_info: dict = {"connected": False, "last_seen": None}


def get_pc_agent_status() -> dict:
    return _pc_agent_info


async def broadcast_to_phones(message: dict) -> None:
    """Send a message to all connected phone clients."""
    dead = []
    for ws in _phone_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _phone_connections.remove(ws)


async def send_to_pc_agent(message: dict) -> bool:
    """Send a command to the PC agent. Returns True if sent."""
    if _pc_agent_connection is None:
        return False
    try:
        await _pc_agent_connection.send_json(message)
        return True
    except Exception as e:
        logger.warning(f"PC agent send failed: {e}")
        return False


# ── Phone WebSocket handler ────────────────────────────────────────────────────

async def handle_phone_sync(websocket: WebSocket) -> None:
    """Handle phone client sync WebSocket connection."""
    await websocket.accept()
    _phone_connections.append(websocket)
    logger.info("Phone client connected for sync.")

    try:
        # Send full sync immediately on connect
        full_data = export_all_data()
        await websocket.send_json({
            "type": "full_sync",
            **full_data
        })

        # Delta sync loop
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=300.0
                )
                data = json.loads(raw)
                await _handle_phone_push(data)

            except asyncio.TimeoutError:
                # Keep-alive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("Phone client disconnected.")
    except Exception as e:
        logger.error(f"Phone sync error: {e}")
    finally:
        if websocket in _phone_connections:
            _phone_connections.remove(websocket)


async def _handle_phone_push(data: dict) -> None:
    """Merge data pushed from phone."""
    if data.get("type") != "sync_push":
        return

    payload = data.get("data", {})

    # Merge memory items (latest timestamp wins)
    for item in payload.get("memory", []):
        key = item.get("key")
        value = item.get("value")
        if key and value:
            set_memory(key, value)

    # Merge reminders
    for reminder in payload.get("reminders", []):
        text = reminder.get("text")
        remind_at = reminder.get("remindAt") or reminder.get("remind_at")
        if text and remind_at:
            try:
                create_reminder(text, remind_at)
            except Exception:
                pass


# ── PC Agent WebSocket handler ─────────────────────────────────────────────────

async def handle_pc_agent(websocket: WebSocket,
                            reminder_callback=None) -> None:
    """Handle PC agent WebSocket connection."""
    global _pc_agent_connection, _pc_agent_info

    await websocket.accept()
    _pc_agent_connection = websocket
    _pc_agent_info = {"connected": True, "last_seen": now_iso()}
    logger.info("PC agent connected.")

    try:
        # Acknowledge connection
        await websocket.send_json({
            "type": "connected",
            "message": "KING cloud connected to PC agent."
        })

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=60.0
                )
                data = json.loads(raw)
                _pc_agent_info["last_seen"] = now_iso()

                await _handle_pc_message(data, websocket, reminder_callback)

            except asyncio.TimeoutError:
                # Keep-alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("PC agent disconnected.")
    except Exception as e:
        logger.error(f"PC agent error: {e}")
    finally:
        _pc_agent_connection = None
        _pc_agent_info = {"connected": False, "last_seen": _pc_agent_info.get("last_seen")}


async def _handle_pc_message(data: dict, websocket: WebSocket,
                               reminder_callback=None) -> None:
    """Process a message from the PC agent."""
    msg_type = data.get("type")

    if msg_type == "pong":
        return

    elif msg_type == "system_info":
        # PC agent sent system info — forward to phone clients
        await broadcast_to_phones({
            "type": "system_info",
            "data": data.get("data", {})
        })

    elif msg_type == "command_result":
        # Result of a system command execution
        await broadcast_to_phones({
            "type": "command_result",
            "action": data.get("action"),
            "result": data.get("result"),
            "success": data.get("success", False)
        })

    elif msg_type == "voice_input":
        # PC agent received voice input — process through KING
        from brain import process
        text = data.get("text", "")
        lang = data.get("language", "en")
        if text:
            result = await process(text, source="pc_agent", hint_language=lang)
            # Send reply back to PC agent for TTS playback
            await websocket.send_json({
                "type": "speak",
                "text": result["voice_reply"],
                "language": result["language"],
                "voice_state": result["voice_state"],
                "action": result.get("action"),
                "action_params": result.get("action_params", {})
            })
            # Also forward to phone
            await broadcast_to_phones({
                "type": "message",
                "role": "king",
                "content": result["reply"],
                "language": result["language"],
                "formation_state": result.get("formation_state", "online")
            })

    elif msg_type == "reminder_ack":
        logger.info(f"PC agent acknowledged reminder: {data.get('id')}")
