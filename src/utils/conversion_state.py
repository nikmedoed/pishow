from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Dict

__all__ = ["get_state", "update_state", "reset_state"]

_STATE_LOCK = Lock()
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
_STATE: Dict[str, Any] = deepcopy(_DEFAULT_STATE)


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def get_state() -> Dict[str, Any]:
    with _STATE_LOCK:
        return deepcopy(_STATE)


def update_state(state: Dict[str, Any]) -> None:
    stamped_state: Dict[str, Any] = {**_DEFAULT_STATE, **state}
    errors = stamped_state.get("errors")
    if isinstance(errors, list):
        stamped_state["errors"] = deepcopy(errors[-10:])
    else:
        stamped_state["errors"] = []
    stamped_state["last_update"] = _timestamp()

    with _STATE_LOCK:
        _STATE.update(deepcopy(stamped_state))


def reset_state() -> None:
    with _STATE_LOCK:
        _STATE.clear()
        _STATE.update(deepcopy(_DEFAULT_STATE))
