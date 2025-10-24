import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from threading import Lock, Thread
from typing import Optional

from src.settings import (
    CONVERT_LOCK_FILE,
    CONVERTER_THROTTLE_SECONDS,
)
from src.utils.conversion_state import load_state, save_state
from src.utils.converter_queue import ConversionQueue

logger = logging.getLogger("media converter")

_PROCESS_LOCK = Lock()
_RUNNING_PROCESS: Optional[subprocess.Popen] = None


def _tracked_process() -> Optional[subprocess.Popen]:
    """Return the currently tracked converter process if it is still running."""

    global _RUNNING_PROCESS
    process = _RUNNING_PROCESS
    if process is None:
        return None
    if process.poll() is None:
        return process
    # The process has exited; clear the cached handle.
    _RUNNING_PROCESS = None
    return None


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
    else:
        return True


def _clean_stale_lock() -> None:
    if CONVERT_LOCK_FILE.exists():
        logger.warning("Removing stale converter lock file.")
        CONVERT_LOCK_FILE.unlink(missing_ok=True)
    state = load_state()
    state.update({"status": "idle", "current": None})
    save_state(state)


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


def enqueue_new_files() -> int:
    queue = ConversionQueue()
    pending = len(queue.items)
    if pending:
        logger.debug("Pending files detected: %s", pending)
    return pending


def is_conversion_running() -> bool:
    if _tracked_process() is not None:
        return True
    return _active_pid() is not None


def start_conversion(port: Optional[str] = None) -> str:
    with _PROCESS_LOCK:
        if _tracked_process() is not None:
            return "Conversion already running."
        queue = ConversionQueue()
        pending = len(queue.items)
        if pending == 0:
            save_state(
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
        cmd = [sys.executable, "src/utils/converter.py"]
        if port:
            cmd.append(port)
        try:
            process = subprocess.Popen(cmd, start_new_session=True)
        except OSError as exc:
            logger.error("Failed to launch converter: %s", exc)
            return f"Failed to launch converter: {exc}"

        def _wait_for_exit(proc: subprocess.Popen) -> None:
            try:
                proc.wait()
            finally:
                with _PROCESS_LOCK:
                    global _RUNNING_PROCESS
                    if _RUNNING_PROCESS is proc:
                        _RUNNING_PROCESS = None

        global _RUNNING_PROCESS
        _RUNNING_PROCESS = process
        Thread(target=_wait_for_exit, args=(process,), daemon=True).start()

    state = load_state()
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
    save_state(state)
    return f"Conversion started for {pending} files."


def request_restart() -> bool:
    with _PROCESS_LOCK:
        process = _tracked_process()
    signal_to_send = getattr(signal, "SIGUSR1", None) or signal.SIGTERM
    if process is not None:
        try:
            process.send_signal(signal_to_send)
        except ProcessLookupError:
            _tracked_process()
            return False
        except PermissionError:
            logger.warning("Insufficient permissions to signal converter process")
            return False
        except AttributeError:  # pragma: no cover - defensive fallback
            process.terminate()
        state = load_state()
        state["status"] = "restarting"
        save_state(state)
        time.sleep(0.1)
        return True

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
    state = load_state()
    state["status"] = "restarting"
    save_state(state)
    time.sleep(0.1)
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
