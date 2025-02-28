import pickle
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Tuple, Union, Optional

from src.media import MediaDict, MediaFile
from src.queue import DeviceQueue
from src.queue import logger

SETTINGS_LIST = {
    'only_photo': 'Photo only mode',
    # 'modern_mode': 'Modern Mode',
    'sequential_mode': 'Sequential mode',
    'show_counters': 'Show counters',
    'show_names': 'Show file names'
}


@dataclass
class DeviceInfo:
    photo_time: int = 15
    only_photo: bool = False
    modern_mode: bool = False
    sequential_mode: bool = False
    show_counters: bool = False
    video_background: bool = False
    show_names: bool = False
    user_agent: str = ""
    ip_address: str = ""
    name: str = ""
    huy: int = 13452345

    @property
    def device_name(self) -> str:
        return self.name or f"{self.user_agent} at {self.ip_address}"


class DeviceQueueManager:
    def __init__(self, media_dict: MediaDict, storage_dir: Path = Path("storage")):
        """
        Initialize the DeviceQueueManager.
        :param media_dict: Dictionary of media files.
        :param storage_dir: Directory for storing device data.
        """
        self.media_dict = media_dict
        self.storage_dir = storage_dir
        self.device_queues = {}
        self.devices_info_file = self.storage_dir / "devices.pkl"
        self.devices_info = self._load_devices_info()

    def _load_devices_info(self):
        if self.devices_info_file.exists():
            try:
                with self.devices_info_file.open("rb") as f:
                    info = pickle.load(f)
                    valid_fields = {f.name for f in fields(DeviceInfo)}
                    for k in list(info.keys()):
                        v = info[k]
                        if isinstance(v, DeviceInfo):
                            v = v.__dict__
                        elif not isinstance(v, dict):
                            logger.warning(f"Incorrect info structure for {k} :: skipped")
                            del info[k]
                            continue
                        info[k] = DeviceInfo(**{k: v for k, v in v.items() if k in valid_fields})
                    return info
            except Exception as e:
                logger.error(f"Error loading device info: {e}")
        return {}

    def _save_devices_info(self):
        try:
            with self.devices_info_file.open("wb") as f:
                pickle.dump(self.devices_info, f)
        except Exception as e:
            print(f"Error saving device info: {e}")

    def delete_queue(self, device_id: str):
        dq, _ = self.get_device_data(device_id)
        dq.delete_dump()
        del self.device_queues[device_id]

    def delete_device(self, device_id: str):
        self.delete_queue(device_id)
        if device_id in self.devices_info:
            del self.devices_info[device_id]
            self._save_devices_info()

    def __getitem__(self, device_id: str):
        return self.get_device_data(device_id)

    def get_device_data(self, device_id: str) -> Tuple[DeviceQueue, DeviceInfo]:
        device_info = self.get_device_info(device_id)
        if device_id not in self.device_queues:
            dq = DeviceQueue(device_id, self.media_dict, self.storage_dir, shuffle=not device_info.sequential_mode)
            self.device_queues[device_id] = dq
        else:
            dq = self.device_queues[device_id]
            dq.shuffle = not device_info.sequential_mode
        return dq, device_info

    def get_next(self, device_id: str) -> Optional[Union[MediaFile, Tuple[MediaFile, int, int]]]:
        dq, device_info = self.get_device_data(device_id)
        only_photo = device_info.only_photo
        media = dq.get_next_counters(only_photo) if device_info.show_counters else dq.get_next(only_photo)
        if media is None:
            logger.warning(f"No media found for device and settings {device_id}.")
        return media

    def update_query(self, keys: list):
        for dq in self.device_queues.values():
            dq.update_queue(keys)

    def get_device_info(self, device_id: str) -> DeviceInfo:
        info = self.devices_info.get(device_id)
        if info is None:
            info = DeviceInfo()
            self.devices_info[device_id] = info
            self._save_devices_info()
        return info

    def update_device_info(self, device_id: str, info=None, **kwargs) -> None:
        if device_id in self.devices_info:
            device_info = self.devices_info[device_id]
        else:
            device_info = DeviceInfo()

        update_fields = {}
        if info is not None:
            if isinstance(info, dict):
                update_fields.update(info)
            elif isinstance(info, DeviceInfo):
                update_fields.update(info.__dict__)
            else:
                raise ValueError("info must be a dict or a DeviceInfo instance")
        update_fields.update(kwargs)

        for field, value in update_fields.items():
            if field in device_info.__dataclass_fields__:
                setattr(device_info, field, value)

        self.devices_info[device_id] = device_info
        self._save_devices_info()
