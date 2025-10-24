import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.settings import UPLOADED_RAW_DIR
from src.utils.converter_types import ALL_EXTENSIONS, VIDEO_EXTENSIONS

VIDEO_SUFFIXES = {ext.lower() for ext in VIDEO_EXTENSIONS}

logger = logging.getLogger("media converter")


@dataclass
class QueueItem:
    relative_path: str
    file_type: str

    @property
    def absolute_path(self) -> Path:
        return UPLOADED_RAW_DIR / self.relative_path


class ConversionQueue:
    def __init__(self) -> None:
        self.items: List[QueueItem] = []
        self.refresh_from_disk()

    def __len__(self) -> int:
        return len(self.items)

    def _existing_items(self) -> List[QueueItem]:
        existing: List[QueueItem] = []
        for item in self.items:
            if item.absolute_path.exists():
                existing.append(item)
        return existing

    def refresh_from_disk(self) -> int:
        """Reload queue items by scanning the raw upload directory."""
        preserved = self._existing_items()
        known_paths = {item.relative_path for item in preserved}
        new_items: List[QueueItem] = []
        for file_path in sorted(UPLOADED_RAW_DIR.rglob("*")):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(UPLOADED_RAW_DIR)
            parts = relative_path.parts
            if parts and parts[0] == "failed":
                continue
            suffix = file_path.suffix.lower()
            if suffix == ".txt" or suffix not in ALL_EXTENSIONS:
                continue
            relative = relative_path.as_posix()
            if relative in known_paths:
                continue
            file_type = "video" if suffix in VIDEO_SUFFIXES else "image"
            new_items.append(QueueItem(relative_path=relative, file_type=file_type))
        new_items.sort(key=lambda item: item.relative_path)
        if new_items:
            logger.debug("Queued %s new files", len(new_items))
        self.items = preserved + new_items
        return len(new_items)

    def pop_next(self) -> Optional[QueueItem]:
        if not self.items:
            return None
        return self.items.pop(0)

    def push_back(self, item: QueueItem) -> None:
        if item.absolute_path.exists():
            self.items.append(item)

    def push_front(self, item: QueueItem) -> None:
        if item.absolute_path.exists():
            self.items.insert(0, item)
