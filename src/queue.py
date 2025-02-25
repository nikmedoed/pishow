import pickle
import random
from pathlib import Path

class DeviceQueue:
    def __init__(self, device_id: str, media_dict: dict, storage_dir: Path, shuffle: bool = True):
        """
        Initialize the device queue.
        device_id: Identifier of the device.
        media_dict: Global dictionary of media files.
        storage_dir: Directory for storing the queue file.
        shuffle: If True, new keys are shuffled.
        """
        self.device_id = device_id
        self.media_dict = media_dict
        self.storage_file = storage_dir / f"queue_{device_id}.pkl"
        self.shuffle = shuffle
        self.queue = []  # Instance-specific queue list
        self.load_queue()

    def load_queue(self):
        """Load the queue from a pickle file; if not present, initialize an empty queue."""
        if self.storage_file.exists():
            try:
                with self.storage_file.open("rb") as f:
                    self.queue = pickle.load(f)
            except Exception as e:
                print(f"Error loading queue for {self.device_id}: {e}")
                self.queue = []
        else:
            self.queue = []
        self.save_queue()

    def save_queue(self):
        """Save the current queue to a pickle file."""
        try:
            with self.storage_file.open("wb") as f:
                pickle.dump(self.queue, f)
        except Exception as e:
            print(f"Error saving queue for {self.device_id}: {e}")

    def update_queue(self, keys: list = None):
        """
        Update the queue with new keys.
        If keys is None, use all keys from media_dict.
        The keys list is reversed then merged with the current queue.
        If shuffle is enabled, the final queue is shuffled.
        """
        if keys is None:
            keys = list(self.media_dict.keys())
        keys.reverse()
        self.queue = keys + self.queue
        if self.shuffle:
            random.shuffle(self.queue)
        self.save_queue()

    def get_next(self):
        """
        Return the next valid media file from the queue.
        If the queue is empty, update it with current media keys.
        Each key is validated against the media_dict.
        """
        while True:
            if not self.queue:
                self.update_queue()
            key = self.queue.pop()
            media = self.media_dict.get(key)
            if media is not None:
                self.save_queue()
                return media
