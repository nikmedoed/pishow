import logging
import pickle
import random
from pathlib import Path

from src.media import MediaDict

logger = logging.getLogger(__name__)


class DeviceQueue:
    def __init__(self, device_id: str, media_dict: MediaDict, storage_dir: Path, shuffle: bool = True):
        """
        Initialize the device queue.
        :param device_id: Device identifier.
        :param media_dict: Global media dictionary.
        :param storage_dir: Directory to store the queue file.
        :param shuffle: Whether to shuffle the queue.
        """
        self.device_id = device_id
        self.media_dict = media_dict
        self.storage_file = storage_dir / f"queue_{device_id}.pkl"
        self.shuffle = shuffle
        self.allowed_keys: tuple[str, ...] | None = None
        self.queue = []
        self.load_queue()
        # Only update the queue if it is empty.
        if not self.queue:
            self.update_queue()

    def load_queue(self):
        """Load queue from file or initialize empty queue."""
        if self.storage_file.exists():
            try:
                with self.storage_file.open("rb") as f:
                    self.queue = pickle.load(f)
            except Exception as e:
                logger.error(f"Error loading queue for {self.device_id}: {e}")
                self.queue = []
        else:
            self.queue = []
        self.save_queue()

    def save_queue(self):
        """Save the current queue to file."""
        try:
            with self.storage_file.open("wb") as f:
                pickle.dump(self.queue, f)
        except Exception as e:
            logger.error(f"Error saving queue for {self.device_id}: {e}")

    def delete_dump(self):
        """Delete queue file (if exists) and clear in-memory queue."""
        try:
            if self.storage_file.exists():
                self.storage_file.unlink()
                logger.debug(f"Queue file {self.storage_file} deleted for device {self.device_id}.")
        except Exception as e:
            logger.error(f"Error deleting queue file for device {self.device_id}: {e}")
        self.queue = []

    def set_allowed_keys(self, keys: list[str] | tuple[str, ...] | None) -> None:
        """
        Restrict queue to provided keys (device collections).
        If None is passed, all media are allowed.
        """
        new_allowed = None if keys is None else tuple(dict.fromkeys(keys))
        changed = self.allowed_keys != new_allowed
        self.allowed_keys = new_allowed
        allowed_set = set(self.allowed_keys) if self.allowed_keys is not None else None
        if allowed_set is not None:
            self.queue = [k for k in self.queue if k in allowed_set]
        if changed or not self.queue:
            # Rebuild to reflect fresh selection.
            self.queue = []
            self.update_queue()
        else:
            self.save_queue()

    def update_queue(self, keys: list = None):
        """
        Update the queue with new keys.
        If keys is None, use all keys from media_dict.
        Queue is always rebuilt from allowed set to avoid order bias.
        """
        allowed = list(self.allowed_keys) if self.allowed_keys is not None else list(self.media_dict.keys())

        if keys is None:
            base_keys = list(dict.fromkeys(allowed))
        else:
            # Keep provided order for keys, then fill with remaining allowed ones.
            base_keys = [k for k in dict.fromkeys(keys) if k in allowed]
            remaining = [k for k in allowed if k not in base_keys]
            base_keys.extend(remaining)

        if self.shuffle:
            self.queue = random.sample(base_keys, len(base_keys))
        else:
            self.queue = base_keys

        self.save_queue()
        logger.debug(f"Queue updated for device {self.device_id}: {len(self.queue)} items.")

    def get_next_counters(self, only_photo=False):
        total_allowed = len(self.allowed_keys) if self.allowed_keys is not None else len(self.media_dict)
        return self.get_next(only_photo=only_photo), total_allowed - len(self.queue), total_allowed

    def get_next(self, only_photo=False):
        """
        Retrieve the next valid media file from the queue.
        If the queue is empty after update, return None.
        """
        while True:
            if not self.queue:
                self.update_queue()
                if not self.queue:
                    logger.error("Queue update resulted in empty queue.")
                    return None
            if only_photo and len(self.media_dict.photo_keys) == 0:
                return None
            key = self.queue.pop()
            media = self.media_dict.get(key)
            if media is None or only_photo and media.is_video:
                continue
            self.save_queue()
            logger.debug(
                f"Next ok :: did {self.device_id} :: {len(self.queue)} / {len(self.media_dict)} :: {media}")
            return media
