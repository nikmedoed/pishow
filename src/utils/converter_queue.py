import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.settings import (
    CONVERTER_QUEUE_FILE,
    UPLOADED_RAW_DIR,
)
from src.utils.converter_types import ALL_EXTENSIONS, VIDEO_EXTENSIONS

logger = logging.getLogger("media converter")


@dataclass
class QueueItem:
    relative_path: str
    file_type: str
    attempts: int = 0
    duration: Optional[float] = None

    @property
    def absolute_path(self) -> Path:
        return UPLOADED_RAW_DIR / self.relative_path

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "file_type": self.file_type,
            "attempts": self.attempts,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "QueueItem":
        return cls(
            relative_path=payload["relative_path"],
            file_type=payload["file_type"],
            attempts=payload.get("attempts", 0),
            duration=payload.get("duration"),
        )


class ConversionQueue:
    def __init__(self):
        self.items: List[QueueItem] = []
        self.load()

    def load(self) -> None:
        if CONVERTER_QUEUE_FILE.exists():
            try:
                with CONVERTER_QUEUE_FILE.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    self.items = [QueueItem.from_dict(item) for item in data.get("items", [])]
            except json.JSONDecodeError:
                logger.warning("Queue file corrupted. Recreating queue.")
                self.items = []
        else:
            self.items = []
        self._remove_missing_files()
        self.save()

    def save(self) -> None:
        payload = {"items": [item.to_dict() for item in self.items]}
        tmp_path = CONVERTER_QUEUE_FILE.with_suffix(CONVERTER_QUEUE_FILE.suffix + ".tmp")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(CONVERTER_QUEUE_FILE)

    def __len__(self) -> int:
        return len(self.items)

    def _remove_missing_files(self) -> bool:
        existing = []
        changed = False
        for item in self.items:
            if item.absolute_path.exists():
                existing.append(item)
            else:
                changed = True
        if changed:
            self.items = existing
        return changed

    def refresh_from_disk(self) -> int:
        removed = self._remove_missing_files()
        known_paths = {item.relative_path for item in self.items}
        new_items: List[QueueItem] = []
        for file_path in sorted(UPLOADED_RAW_DIR.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix == ".txt":
                continue
            if suffix not in ALL_EXTENSIONS:
                continue
            rel_path = file_path.relative_to(UPLOADED_RAW_DIR).as_posix()
            if rel_path in known_paths:
                continue
            file_type = "video" if suffix in [ext.lower() for ext in VIDEO_EXTENSIONS] else "image"
            new_items.append(QueueItem(relative_path=rel_path, file_type=file_type))
            known_paths.add(rel_path)
        if new_items or removed:
            self.items.extend(new_items)
            self.save()
        return len(new_items)

    def pop_next(self) -> Optional[QueueItem]:
        if not self.items:
            return None
        item = self.items.pop(0)
        self.save()
        return item

    def push_back(self, item: QueueItem) -> None:
        self.items.append(item)
        self.save()
