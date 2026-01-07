import pickle
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional, Tuple, Union

from src.media import MediaDict, MediaFile
from src.queue import DeviceQueue
from src.queue import logger
from src.utils.media_collections import (
    COLLECTION_ROOT_ID,
    normalize_collection_id,
    scan_collections,
)

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
    collections: list[str] | None = None
    user_agent: str = ""
    ip_address: str = ""
    name: str = ""

    @property
    def device_name(self) -> str:
        return self.name or f"{self.user_agent} at {self.ip_address}"


class DeviceQueueManager:
    def __init__(
            self,
            media_dict: MediaDict,
            storage_dir: Path = Path("storage"),
            default_collections: Optional[list[str]] = None,
    ):
        """
        Initialize the DeviceQueueManager.
        :param media_dict: Dictionary of media files.
        :param storage_dir: Directory for storing device data.
        """
        self.media_dict = media_dict
        self.storage_dir = storage_dir
        self.device_queues = {}
        self.devices_info_file = self.storage_dir / "devices.pkl"
        self.default_collections_file = self.storage_dir / "collections_default.pkl"
        self.default_collections = self._load_default_collections(default_collections)
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

    def _normalize_collection_ids(self, collection_ids: Optional[list[str]], allow_empty: bool = False):
        if collection_ids is None:
            return None
        normalized = []
        for cid in collection_ids:
            norm = normalize_collection_id(cid)
            if norm not in normalized:
                normalized.append(norm)
        if not normalized and not allow_empty:
            return None
        return normalized

    def _load_default_collections(self, fallback: Optional[list[str]]):
        fallback_normalized = self._normalize_collection_ids(fallback, allow_empty=True) or []
        if self.default_collections_file.exists():
            try:
                with self.default_collections_file.open("rb") as f:
                    stored = pickle.load(f)
                    normalized = self._normalize_collection_ids(stored, allow_empty=True)
                    if normalized:
                        return normalized
            except Exception as e:
                logger.error(f"Error loading default collections: {e}")
        if fallback_normalized:
            return fallback_normalized
        return [COLLECTION_ROOT_ID]

    def _save_default_collections(self):
        try:
            with self.default_collections_file.open("wb") as f:
                pickle.dump(self.default_collections, f)
        except Exception as e:
            logger.error(f"Error saving default collections: {e}")

    def _reset_default_queues(self):
        for device_id, info in self.devices_info.items():
            if info.collections is None:
                if device_id in self.device_queues:
                    self.reset_device_queue(device_id)
                else:
                    storage_file = self.storage_dir / f"queue_{device_id}.pkl"
                    if storage_file.exists():
                        storage_file.unlink()

    def set_default_collections(self, collections: list[str]):
        normalized = self._normalize_collection_ids(collections, allow_empty=True) or [COLLECTION_ROOT_ID]
        self.default_collections = normalized
        self._save_default_collections()
        self._reset_default_queues()

    def list_collections(self):
        return scan_collections(
            self.media_dict.media_dir,
            self.media_dict.background_suffix or "",
            self.media_dict.uploaded_media_raw,
        )

    def delete_queue(self, device_id: str):
        dq = self.device_queues.get(device_id)
        if dq:
            dq.delete_dump()
            del self.device_queues[device_id]
            return
        storage_file = self.storage_dir / f"queue_{device_id}.pkl"
        if storage_file.exists():
            storage_file.unlink()

    def delete_device(self, device_id: str):
        self.delete_queue(device_id)
        if device_id in self.devices_info:
            del self.devices_info[device_id]
            self._save_devices_info()

    def __getitem__(self, device_id: str):
        return self.get_device_data(device_id)

    def get_active_collections(self, device_info: DeviceInfo):
        if device_info.collections is None or len(device_info.collections) == 0:
            return self.default_collections
        return device_info.collections

    def _device_active_keys(self, device_id: str):
        device_info = self.get_device_info(device_id)
        return self.media_dict.keys_for_collections(self.get_active_collections(device_info))

    def reset_device_queue(self, device_id: str):
        dq, _ = self.get_device_data(device_id)
        dq.delete_dump()
        dq.update_queue(replace=True)

    def get_device_data(self, device_id: str) -> Tuple[DeviceQueue, DeviceInfo]:
        device_info = self.get_device_info(device_id)
        if device_id not in self.device_queues:
            dq = DeviceQueue(
                device_id,
                self.media_dict,
                self.storage_dir,
                shuffle=not device_info.sequential_mode,
                active_keys_getter=lambda: self._device_active_keys(device_id),
            )
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

    def update_query(self, _keys: list | None = None):
        for dq in self.device_queues.values():
            dq.update_queue()

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

        queue_reset_needed = False
        collections_value_set = False
        for field, value in update_fields.items():
            if field not in device_info.__dataclass_fields__:
                continue
            if field == "collections":
                collections_value_set = True
                value = self._normalize_collection_ids(value, allow_empty=True)
                if value == []:
                    value = None
                if device_info.collections != value:
                    queue_reset_needed = True
                    device_info.collections = value
                continue
            setattr(device_info, field, value)

        self.devices_info[device_id] = device_info
        self._save_devices_info()

        if queue_reset_needed and collections_value_set:
            self.reset_device_queue(device_id)
