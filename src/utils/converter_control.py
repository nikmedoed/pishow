import logging
import subprocess
import sys
from datetime import datetime
from typing import Optional

from src.settings import (
    CONVERT_LOCK_FILE,
    CONVERTER_RESTART_FILE,
    CONVERTER_THROTTLE_SECONDS,
)
from src.utils.conversion_state import load_state, save_state
from src.utils.converter_queue import ConversionQueue

logger = logging.getLogger("media converter")


def enqueue_new_files() -> int:
    queue = ConversionQueue()
    added = queue.refresh_from_disk()
    if added:
        logger.info("Added %s new files to conversion queue", added)
    return added


def is_conversion_running() -> bool:
    return CONVERT_LOCK_FILE.exists()


def start_conversion(port: Optional[str] = None) -> str:
    queue = ConversionQueue()
    added = queue.refresh_from_disk()
    if is_conversion_running():
        state = load_state()
        current = state.get("current")
        processed = state.get("processed", 0) or 0
        include_current = 1 if current else 0
        total = processed + len(queue.items) + include_current
        state["total"] = total
        state["remaining"] = len(queue.items) + include_current
        state["percent"] = round((processed / total) * 100, 2) if total else 0.0
        save_state(state)
        return "Conversion already running."
    if len(queue.items) == 0:
        save_state({"status": "idle", "total": 0, "processed": 0, "remaining": 0, "percent": 0})
        return "Nothing to convert"
    cmd = [sys.executable, "src/utils/converter.py"]
    if port:
        cmd.append(port)
    subprocess.Popen(cmd, start_new_session=True)
    state = load_state()
    state["status"] = "scheduled"
    state["total"] = len(queue.items)
    state["processed"] = 0
    state["remaining"] = len(queue.items)
    state["percent"] = 0.0
    state["current"] = None
    save_state(state)
    files_msg = len(queue.items)
    return f"Conversion started for {files_msg} files."


def request_restart() -> bool:
    if not is_conversion_running():
        return False
    CONVERTER_RESTART_FILE.touch(exist_ok=True)
    state = load_state()
    state["status"] = "restarting"
    save_state(state)
    return True


def get_conversion_status() -> dict:
    state = load_state()
    throttle = max(CONVERTER_THROTTLE_SECONDS, 0)
    state.setdefault("throttle_seconds", throttle)
    last_update = state.get("last_update")

    def _normalize(ts: Optional[str]) -> Optional[str]:
        if not ts or not isinstance(ts, str):
            return ts
        candidate = ts
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return ts
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    normalized_last = _normalize(last_update)
    if normalized_last:
        state["last_update"] = normalized_last

    errors = state.get("errors") or []
    for error in errors:
        if isinstance(error, dict):
            ts = error.get("timestamp")
            normalized = _normalize(ts)
            if normalized:
                error["timestamp"] = normalized
    return state
