import hashlib
import logging
import mimetypes
import pickle
import random
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from pymediainfo import MediaInfo

from src.utils.media_collections import (
    collection_id_from_relative_path,
    normalize_collection_id,
)

logger = logging.getLogger(__name__)


@dataclass
class MediaFile:
    file: str
    relative_path: str
    collection_id: str = "/"
    is_video: bool = False
    duration: int = None


def get_video_duration(file_path: Path) -> int:
    """Return video duration in seconds."""
    try:
        media_info = MediaInfo.parse(file_path)
        for track in media_info.tracks:
            if track.track_type == "Video" and track.duration:
                return int(track.duration / 1000)
    except Exception as e:
        logger.error("Error fetching video duration for %s: %s", file_path, e)
    return 0


class MediaDict(dict):
    photo_keys = None
    video_keys = None

    def __init__(self, media_dir: Path,
                 background_suffix: str = None,
                 uploaded_media_raw: Path = None,
                 metadata_cache_file: Path | None = None,
                 *args, **kwargs):
        """
        Initialize the MediaDict.
        :param media_dir: Directory containing media files.
        """
        super().__init__(*args, **kwargs)
        self.media_dir = media_dir
        self.background_suffix = background_suffix
        self.uploaded_media_raw = uploaded_media_raw
        self.metadata_cache_file = metadata_cache_file
        self._metadata_cache = self._load_metadata_cache()
        self._metadata_cache_dirty = False
        self.collections_index = {}
        self.sync_files()

    def sync_files(self):
        """
        Synchronize media files from the directory.
        Returns a list of new keys.
        """
        new_keys = []
        found_keys = set()
        collections_index = {}
        found_rel_paths = set()

        for file in self.media_dir.rglob("*"):
            if (self.background_suffix is not None and str(file).endswith(self.background_suffix)
                    or self.uploaded_media_raw is not None and file.is_relative_to(self.uploaded_media_raw)):
                continue
            # Skip hidden files and directories (starting with dot)
            rel_parts = file.relative_to(self.media_dir).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            mime_type, _ = mimetypes.guess_type(file)
            if not (mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/"))):
                continue

            rel_path = str(file.relative_to(self.media_dir)).replace("\\", "/")
            found_rel_paths.add(rel_path)
            key = hashlib.md5(rel_path.encode("utf-8")).hexdigest()
            collection_id = collection_id_from_relative_path(rel_path)
            url = quote(rel_path)

            found_keys.add(key)
            if key not in self:
                if mime_type.startswith("image/"):
                    self[key] = MediaFile(relative_path=url, file=rel_path, collection_id=collection_id)
                else:
                    duration = self._get_cached_duration(file, rel_path)
                    self[key] = MediaFile(
                        relative_path=url,
                        file=rel_path,
                        collection_id=collection_id,
                        is_video=True,
                        duration=duration
                    )
                new_keys.append(key)
            else:
                existing = super().get(key)
                if existing and existing.collection_id != collection_id:
                    existing.collection_id = collection_id
            collections_index.setdefault(collection_id, []).append(key)

        for key in list(self.keys()):
            if key not in found_keys:
                del self[key]

        # Drop stale metadata cache entries for removed files.
        for rel_path in list(self._metadata_cache.keys()):
            if rel_path not in found_rel_paths:
                del self._metadata_cache[rel_path]
                self._metadata_cache_dirty = True
        self._save_metadata_cache()

        self.collections_index = {cid: tuple(keys) for cid, keys in collections_index.items()}
        self.photo_keys = tuple(key for key, media in self.items() if not media.is_video)
        self.video_keys = tuple(key for key, media in self.items() if media.is_video)
        logger.debug(f"New files {len(new_keys)} total {len(self)}")
        return new_keys

    def __getitem__(self, key):
        item = super().__getitem__(key)
        if item is None or not item.relative_path:
            return None
        if not hasattr(item, "collection_id"):
            item.collection_id = collection_id_from_relative_path(item.file)
        file_path = self.media_dir / item.file
        if not file_path.exists():
            self.sync_files()
            return None
        return item

    def ensure_duration(self, media: MediaFile) -> MediaFile:
        """Fill video duration if missing, using cache to avoid repeated heavy reads."""
        if media is None or not media.is_video:
            return media
        if media.duration not in (None, 0):
            return media
        file_path = self.media_dir / media.file
        cached = self._get_cached_duration(file_path, media.file)
        if cached is not None:
            media.duration = cached
            return media
        duration = get_video_duration(file_path)
        media.duration = duration
        self._set_cached_duration(file_path, media.file, duration)
        return media

    def get_random_photo_background(self):
        for _ in range(5):
            if not self.photo_keys:
                return
            key = random.choice(self.photo_keys)
            item = self[key]
            if not item:
                continue
            file_path = self.media_dir / item.file
            if file_path.exists():
                return item.file

    def keys_for_collections(self, collection_ids):
        self.sync_files()
        if not collection_ids:
            return list(self.keys())
        result = []
        seen = set()
        for collection_id in collection_ids:
            normalized = normalize_collection_id(collection_id)
            for key in self.collections_index.get(normalized, ()):
                if key in seen:
                    continue
                seen.add(key)
                result.append(key)
        return result

    def _load_metadata_cache(self):
        if self.metadata_cache_file and self.metadata_cache_file.exists():
            try:
                with self.metadata_cache_file.open("rb") as f:
                    data = pickle.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load metadata cache: %s", exc)
        return {}

    def _save_metadata_cache(self):
        if not self.metadata_cache_file or not self._metadata_cache_dirty:
            return
        try:
            with self.metadata_cache_file.open("wb") as f:
                pickle.dump(self._metadata_cache, f)
            self._metadata_cache_dirty = False
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to save metadata cache: %s", exc)

    def _get_cached_duration(self, file_path: Path, rel_path: str):
        entry = self._metadata_cache.get(rel_path)
        if not entry:
            return None
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return None
        if entry.get("size") == stat.st_size and abs(entry.get("mtime", 0) - stat.st_mtime) < 0.001:
            return entry.get("duration")
        return None

    def _set_cached_duration(self, file_path: Path, rel_path: str, duration: int):
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return
        self._metadata_cache[rel_path] = {"duration": duration, "size": stat.st_size, "mtime": stat.st_mtime}
        self._metadata_cache_dirty = True
        self._save_metadata_cache()


if __name__ == '__main__':
    media_dir = Path("../../gallery")
    media_dict = MediaDict(media_dir)

    logger.info("Found media files:")
    for key, media in media_dict.items():
        file_type = "Video" if media.is_video else "Image"
        duration_str = f", Duration: {media.duration} sec" if media.is_video else ""
        logger.info("Key: %s | %s | File: %s%s", key, file_type, media.relative_path, duration_str)

    new_keys = media_dict.sync_files()
    if new_keys:
        logger.info("\nNew files added with keys:")
        for key in new_keys:
            logger.info(key)
    else:
        logger.info("\nNo new files found.")
