import logging
import pickle
import random
from pathlib import Path
from threading import Thread

from src.media import MediaDict

logger = logging.getLogger(__name__)


class DeviceQueue:
    def __init__(
            self,
            device_id: str,
            media_dict: MediaDict,
            storage_dir: Path,
            shuffle: bool = True,
            active_keys_getter=None
    ):
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
        self.active_keys_getter = active_keys_getter
        self.queue = []
        self._prefetch_thread: Thread | None = None
        self._prefetch_only_photo = False
        self.load_queue()
        # Only update the queue if it is empty.
        if not self.queue:
            self.update_queue(replace=True)

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

    def update_queue(self, keys: list = None, replace: bool = False):
        """
        Update the queue with new keys.
        If keys is None, use keys from the active_keys_getter or media_dict.
        When replace=True the queue is rebuilt from scratch.
        """
        keys = self._get_keys(keys)
        if not keys:
            self.queue = []
            self.save_queue()
            logger.warning("Queue update resulted in empty queue for %s", self.device_id)
            return

        if replace:
            combined = list(dict.fromkeys(keys))
        else:
            incoming = list(keys)
            incoming.reverse()
            combined = incoming + [key for key in self.queue if key not in incoming]

        queue_data = combined
        if self.shuffle:
            random.shuffle(queue_data)
        self.queue = queue_data
        self.save_queue()
        logger.debug(f"Queue updated for device {self.device_id}: {len(self.queue)} items.")
        self._prefetch_next()

    def get_next_counters(self, only_photo=False):
        media = self.get_next(only_photo=only_photo)
        total = len(self._get_keys(None))
        if media is None or total == 0:
            return None
        position = total - len(self.queue)
        return media, position, total

    def get_next(self, only_photo=False):
        """
        Retrieve the next valid media file from the queue.
        If the queue is empty after update, return None.
        """
        self._prefetch_only_photo = only_photo
        while True:
            if not self.queue:
                self.update_queue(replace=True)
                if not self.queue:
                    logger.error("Queue update resulted in empty queue.")
                    return None
            if only_photo and len(self.media_dict.photo_keys) == 0:
                return None
            key = self.queue.pop()
            media = self.media_dict.ensure_metadata(key)
            if media is None:
                self.save_queue()
                continue
            if only_photo and media.is_video:
                self.save_queue()
                self._prefetch_next()
                continue
            self.save_queue()
            self._prefetch_next(only_photo)
            logger.debug(
                f"Next ok :: did {self.device_id} :: {len(self.queue)} / {len(self.media_dict)} :: {media}")
            return media

    def _get_keys(self, keys):
        if keys is not None:
            return list(dict.fromkeys(keys))
        if self.active_keys_getter is not None:
            try:
                return list(dict.fromkeys(self.active_keys_getter()))
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to fetch active keys for %s: %s", self.device_id, exc)
                return []
        return list(dict.fromkeys(self.media_dict.keys()))

    def _ensure_video_background(self, media):
        """Warm up static background for videos if missing."""
        try:
            from src.utils.video_background import get_static_background_path
        except Exception as exc:  # pragma: no cover - defensive import
            logger.debug("Video background helper unavailable: %s", exc)
            return
        try:
            get_static_background_path(media.file)
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug("Background warm-up failed for %s: %s", media.file, exc)

    def _prefetch_next(self, only_photo: bool | None = None):
        """
        Check queued items in background: drop missing, warm metadata and video backgrounds.
        Processes the entire queue in playback order to avoid heavy work on the main thread.
        """
        if only_photo is not None:
            self._prefetch_only_photo = only_photo
        if not self.queue:
            return
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return

        def worker():
            modified = False
            for key in list(reversed(self.queue)):
                current_only_photo = self._prefetch_only_photo
                media = self.media_dict.ensure_metadata(key)
                if media is None or (current_only_photo and media.is_video):
                    try:
                        self.queue.remove(key)
                        modified = True
                    except ValueError:
                        pass
                    continue
                if media.is_video:
                    self._ensure_video_background(media)
            if modified:
                self.save_queue()
            self._prefetch_thread = None

        self._prefetch_thread = Thread(target=worker, daemon=True)
        self._prefetch_thread.start()
