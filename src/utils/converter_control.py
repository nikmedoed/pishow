import errno
import json
import logging
import os
import signal
import time
from datetime import datetime
from threading import Lock, Thread
from typing import Optional

from src.settings import (
    CONVERT_LOCK_FILE,
    CONVERTER_THROTTLE_SECONDS,
)
from src.utils.conversion_state import get_state, update_state
from src.utils.converter import Converter, STOP_EVENT
from src.utils.converter_queue import ConversionQueue

logger = logging.getLogger("media converter")

_PROCESS_LOCK = Lock()
_CONVERTER_THREAD: Optional[Thread] = None


def _thread_is_running() -> bool:
    thread = _CONVERTER_THREAD
    return thread is not None and thread.is_alive()


def _read_lock_payload() -> Optional[dict]:
    if not CONVERT_LOCK_FILE.exists():
        return None
    try:
        with CONVERT_LOCK_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        # Windows raises "invalid parameter" (WinError 87 / errno.EINVAL)
        # when os.kill receives signal 0. Treat it as a non-running process so
        # the stale lock can be cleared without crashing the admin dashboard.
        if exc.errno == errno.EINVAL or getattr(exc, "winerror", None) == 87:
            return False
        raise
    else:
        return True


def _clean_stale_lock() -> None:
    if CONVERT_LOCK_FILE.exists():
        logger.warning("Removing stale converter lock file.")
        CONVERT_LOCK_FILE.unlink(missing_ok=True)
    state = get_state()
    state.update({"status": "idle", "current": None})
    update_state(state)


def _active_pid() -> Optional[int]:
    payload = _read_lock_payload()
    if not payload:
        if CONVERT_LOCK_FILE.exists():
            _clean_stale_lock()
        return None
    pid = payload.get("pid")
    if isinstance(pid, int) and _pid_is_running(pid):
        return pid
    _clean_stale_lock()
    return None


def _write_lock_file() -> None:
    payload = {
        "pid": os.getpid(),
        "started": datetime.now().astimezone().isoformat(),
    }
    try:
        with CONVERT_LOCK_FILE.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except FileExistsError:
        try:
            with CONVERT_LOCK_FILE.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        except OSError as exc:
            logger.warning("Unable to refresh converter lock file: %s", exc)
    except OSError as exc:
        logger.warning("Unable to create converter lock file: %s", exc)


def _remove_lock_file() -> None:
    try:
        CONVERT_LOCK_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Unable to remove converter lock file: %s", exc)


def enqueue_new_files() -> int:
    queue = ConversionQueue()
    pending = len(queue.items)
    if pending:
        logger.debug("Pending files detected: %s", pending)
    return pending


def is_conversion_running() -> bool:
    if _thread_is_running():
        return True
    return _active_pid() is not None


def start_conversion(port: Optional[str] = None) -> str:
    with _PROCESS_LOCK:
        if _thread_is_running():
            return "Conversion already running."
        if _active_pid() is not None:
            return "Conversion already running."

        queue = ConversionQueue()
        pending = len(queue.items)
        if pending == 0:
            update_state(
                {
                    "status": "idle",
                    "total": 0,
                    "processed": 0,
                    "remaining": 0,
                    "percent": 0.0,
                    "current": None,
                }
            )
            return "Nothing to convert"

        converter = Converter(port or "8000")

        def _run_converter() -> None:
            try:
                _write_lock_file()
                converter.run()
            finally:
                _remove_lock_file()
                with _PROCESS_LOCK:
                    global _CONVERTER_THREAD
                    _CONVERTER_THREAD = None

        thread = Thread(target=_run_converter, daemon=True)
        thread.start()
        global _CONVERTER_THREAD
        _CONVERTER_THREAD = thread

    state = get_state()
    state.update(
        {
            "status": "scheduled",
            "total": pending,
            "processed": 0,
            "remaining": pending,
            "percent": 0.0,
            "current": None,
        }
    )
    update_state(state)
    return f"Conversion started for {pending} files."


def request_restart() -> bool:
    with _PROCESS_LOCK:
        thread = _CONVERTER_THREAD if _thread_is_running() else None

    if thread is not None:
        state = get_state()
        state["status"] = "restarting"
        update_state(state)
        STOP_EVENT.set()
        return True

    signal_to_send = getattr(signal, "SIGUSR1", None) or signal.SIGTERM
    pid = _active_pid()
    if pid is None:
        return False
    if pid == os.getpid():
        logger.warning("Converter lock references the web process; clearing stale lock.")
        _clean_stale_lock()
        return False
    try:
        os.kill(pid, signal_to_send)
    except ProcessLookupError:
        _clean_stale_lock()
        return False
    except PermissionError:
        logger.warning("Insufficient permissions to signal converter process %s", pid)
        return False
    state = get_state()
    state["status"] = "restarting"
    update_state(state)
    time.sleep(0.1)
    return True


def _initialize_lock_state() -> None:
    try:
        _active_pid()
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.debug("Converter lock validation failed: %s", exc)


_initialize_lock_state()


def get_conversion_status() -> dict:
    state = get_state()
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
