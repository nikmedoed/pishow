import logging
import pickle
import random
from pathlib import Path

logger = logging.getLogger(__name__)


class DeviceQueue:
    def __init__(self, device_id: str, media_dict: dict, storage_dir: Path, shuffle: bool = True):
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

    def update_queue(self, keys: list = None):
        """
        Update the queue with new keys.
        If keys is None, use all keys from media_dict.
        Reverse the new keys, merge with the current queue (without duplicates),
        and shuffle if enabled.
        """
        if keys is None:
            keys = list(self.media_dict.keys())
        keys.reverse()
        # Merge new keys with existing ones, avoiding duplicates.
        combined = keys + [key for key in self.queue if key not in keys]
        self.queue = combined
        if self.shuffle:
            random.shuffle(self.queue)
        self.save_queue()
        logger.debug(f"Queue updated for device {self.device_id}: {len(self.queue)} items.")

    def get_next(self):
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
            key = self.queue.pop()
            media = self.media_dict.get(key)
            if media is not None:
                self.save_queue()
                logger.debug(f"Next ok :: did {self.device_id} :: {len(self.queue)} / {len(self.media_dict)} :: {media}")
                return media
