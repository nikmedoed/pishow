import pickle
from pathlib import Path

from src.queue import DeviceQueue

class DeviceQueueManager:
    def __init__(self, media_dict: dict, storage_dir: Path = Path("storage"), shuffle: bool = True):
        """
        Initialize the DeviceQueueManager.
        media_dict: Dictionary of media files.
        storage_dir: Directory to store device queue files.
        shuffle: If True, new keys are shuffled.
        """
        self.media_dict = media_dict
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(exist_ok=True)
        self.shuffle = shuffle
        self.device_queues = {}  # device_id -> DeviceQueue
        self.devices_info_file = self.storage_dir / "devices.pkl"
        self.devices_info = self._load_devices_info()

    def _load_devices_info(self):
        # Load device information from a pickle file
        if self.devices_info_file.exists():
            try:
                with self.devices_info_file.open("rb") as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Error loading device data: {e}")
        return {}

    def _save_devices_info(self):
        # Save device information to a pickle file
        try:
            with self.devices_info_file.open("wb") as f:
                pickle.dump(self.devices_info, f)
        except Exception as e:
            print(f"Error saving device data: {e}")

    def __getitem__(self, device_id: str):
        # Allow dict-like access to device queues
        return self.get_item(device_id)

    def get_item(self, device_id: str):
        # Return the DeviceQueue for a given device_id; create a new one if needed
        if device_id not in self.device_queues:
            dq = DeviceQueue(device_id, self.media_dict, self.storage_dir, shuffle=self.shuffle)
            dq.update_queue()  # Populate the queue with current keys
            self.device_queues[device_id] = dq
        return self.device_queues[device_id]

    def get_next(self, device_id: str):
        # Return the next media file for the specified device
        dq = self.get_item(device_id)
        media = dq.get_next()
        if media is None:
            raise ValueError("Media file not found.")
        return media

    def update_query(self, keys: list):
        # Update all active queues with the provided list of keys
        for dq in self.device_queues.values():
            dq.update_queue(keys)

    def get_device_info(self, device_id: str):
        return self.devices_info.get(device_id)

    def update_device_info(self, device_id: str, info: dict):
        self.devices_info[device_id] = info
        self._save_devices_info()
