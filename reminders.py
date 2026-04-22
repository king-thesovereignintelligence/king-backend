from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import get_due_reminders, mark_reminder_done
from datetime import datetime, timezone
import logging
from typing import Callable, Optional

logger = logging.getLogger("king.reminders")

_scheduler: Optional[AsyncIOScheduler] = None
_notify_callback: Optional[Callable] = None


def set_notify_callback(callback: Callable) -> None:
    """Set the callback to notify when a reminder is due."""
    global _notify_callback
    _notify_callback = callback


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def check_due_reminders() -> None:
    """Check for due reminders and fire notifications."""
    try:
        due = get_due_reminders()
        for reminder in due:
            logger.info(f"Reminder due: {reminder['text']}")
            mark_reminder_done(reminder["id"])
            if _notify_callback:
                await _notify_callback({
                    "type": "reminder",
                    "text": reminder["text"],
                    "id": reminder["id"]
                })
    except Exception as e:
        logger.error(f"check_due_reminders error: {e}")


def start_reminder_scheduler() -> None:
    """Start the reminder check loop."""
    scheduler = get_scheduler()
    scheduler.add_job(
        check_due_reminders,
        trigger=IntervalTrigger(minutes=1),
        id="reminder_check",
        replace_existing=True
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Reminder scheduler started.")


def stop_reminder_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("Reminder scheduler stopped.")


def parse_reminder_time(time_str: str) -> Optional[str]:
    """
    Parse natural or ISO time strings.
    Accepts: ISO 8601, "HH:MM", "tomorrow HH:MM"
    Returns ISO 8601 string or None if unparseable.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # Already ISO
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        pass

    # HH:MM today
    time_match_today = None
    import re
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str.strip())
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        dt = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)
        return dt.isoformat()

    # "tomorrow HH:MM"
    m = re.match(r'tomorrow\s+(\d{1,2}):(\d{2})', time_str.strip().lower())
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        dt = (now + timedelta(days=1)).replace(
            hour=h, minute=mn, second=0, microsecond=0)
        return dt.isoformat()

    # "in X minutes/hours"
    m = re.match(r'in\s+(\d+)\s+(minute|hour)s?', time_str.strip().lower())
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "minute":
            dt = now + timedelta(minutes=amount)
        else:
            dt = now + timedelta(hours=amount)
        return dt.isoformat()

    return None
