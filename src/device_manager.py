import pickle
from pathlib import Path

from src.queue import DeviceQueue


class DeviceQueueManager:
    def __init__(self, media_dict: dict, storage_dir: Path = Path("storage"), shuffle: bool = True):
        """
        Initialize the DeviceQueueManager.
        :param media_dict: Dictionary of media files.
        :param storage_dir: Directory for storing device data.
        :param shuffle: Whether to shuffle new queue items.
        """
        self.media_dict = media_dict
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(exist_ok=True)
        self.shuffle = shuffle
        self.device_queues = {}  # Mapping from device_id to DeviceQueue instance.
        self.devices_info_file = self.storage_dir / "devices.pkl"
        self.devices_info = self._load_devices_info()

    def _load_devices_info(self):
        if self.devices_info_file.exists():
            try:
                with self.devices_info_file.open("rb") as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Error loading device info: {e}")
        return {}

    def _save_devices_info(self):
        try:
            with self.devices_info_file.open("wb") as f:
                pickle.dump(self.devices_info, f)
        except Exception as e:
            print(f"Error saving device info: {e}")

    def __getitem__(self, device_id: str):
        return self.get_item(device_id)

    def get_item(self, device_id: str):
        if device_id not in self.device_queues:
            # Create DeviceQueue; its constructor now loads persisted queue and only updates if empty.
            dq = DeviceQueue(device_id, self.media_dict, self.storage_dir, shuffle=self.shuffle)
            self.device_queues[device_id] = dq
        return self.device_queues[device_id]

    def get_next(self, device_id: str):
        dq = self.get_item(device_id)
        media = dq.get_next()
        if media is None:
            raise ValueError("No media found for device.")
        return media

    def update_query(self, keys: list):
        for dq in self.device_queues.values():
            dq.update_queue(keys)

    def get_device_info(self, device_id: str):
        return self.devices_info.get(device_id)

    def update_device_info(self, device_id: str, info: dict):
        self.devices_info[device_id] = info
        self._save_devices_info()
