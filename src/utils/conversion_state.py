import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.settings import CONVERTER_STATE_FILE

logger = logging.getLogger("media converter")

_STATE_LOCK = threading.Lock()

_DEFAULT_STATE: Dict[str, Any] = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "remaining": 0,
    "percent": 0.0,
    "current": None,
    "errors": [],
    "last_update": None,
}


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            tmp_path.replace(path)
            return
        except PermissionError as exc:
            wait = 0.1 * attempt
            logger.warning(
                "Retrying state write due to permission error (attempt %s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            time.sleep(wait)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise
    logger.error(
        "Falling back to direct write for %s after repeated permission errors.",
        path,
    )
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp_path.unlink(missing_ok=True)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def load_state() -> Dict[str, Any]:
    with _STATE_LOCK:
        if not CONVERTER_STATE_FILE.exists():
            return dict(_DEFAULT_STATE)
        try:
            with CONVERTER_STATE_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            return dict(_DEFAULT_STATE)
        return {**_DEFAULT_STATE, **data}


def _formatted_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def save_state(state: Dict[str, Any]) -> None:
    stamped_state = {**_DEFAULT_STATE, **state}
    stamped_state["last_update"] = _formatted_timestamp()
    with _STATE_LOCK:
        _atomic_write(CONVERTER_STATE_FILE, stamped_state)


def reset_state() -> None:
    save_state(dict(_DEFAULT_STATE))
