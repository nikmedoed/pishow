import hashlib
import logging
import mimetypes
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from pymediainfo import MediaInfo

logger = logging.getLogger(__name__)


@dataclass
class MediaFile:
    file: str
    relative_path: str
    is_video: bool = False
    duration: int = None


@dataclass
class CollectionInfo:
    """
    Represents a collection mapped to a folder inside MEDIA_DIR.
    Collection is non-recursive: it contains only files directly inside the folder.
    """

    id: str
    name: str
    path: Path
    parent_id: str | None
    depth: int
    files_count: int = 0

    @property
    def display_name(self) -> str:
        return self.name or "Root"

    @property
    def display_path(self) -> str:
        if not self.id:
            return "/"
        return f"/{self.id}"


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

    def __init__(
        self,
        media_dir: Path,
        background_suffix: str = None,
        uploaded_media_raw: Path = None,
        *args,
        **kwargs,
    ):
        """
        Initialize the MediaDict.
        :param media_dir: Directory containing media files.
        """
        super().__init__(*args, **kwargs)
        self.media_dir = media_dir
        self.background_suffix = background_suffix
        self.uploaded_media_raw = uploaded_media_raw
        self.collections: dict[str, CollectionInfo] = {}
        self.collection_keys: dict[str, list[str]] = {}
        self.file_id_to_key: dict[str, str] = {}
        self.key_to_file_id: dict[str, str] = {}
        self.sync_files()

    # region helpers
    def _canonical_path(self, path: Path) -> str:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path.absolute()
        resolved_str = resolved.as_posix()
        if os.name == "nt":
            resolved_str = resolved_str.lower()
        return resolved_str

    def _file_identity(self, path: Path) -> str:
        try:
            stat = path.stat()
            inode = getattr(stat, "st_ino", 0)
            if inode:
                return f"inode:{getattr(stat, 'st_dev', 0)}:{inode}"
        except Exception:
            # Fall back to canonical path when inode is unavailable.
            pass
        return f"path:{self._canonical_path(path)}"

    def _collection_id(self, file_path: Path) -> str:
        try:
            rel_parent = file_path.parent.relative_to(self.media_dir)
        except ValueError:
            rel_parent = Path(".")
        rel = str(rel_parent).replace("\\", "/")
        return "" if rel == "." else rel

    def _register_collection(self, folder: Path) -> None:
        collection_id = self._collection_id(folder / "dummy")
        parent = folder.parent if folder != self.media_dir else None
        parent_id = None
        if parent and parent != self.media_dir:
            parent_id = str(parent.relative_to(self.media_dir)).replace("\\", "/")
        depth = 0 if not collection_id else collection_id.count("/") + 1
        self.collections[collection_id] = CollectionInfo(
            id=collection_id,
            name=folder.name if folder != self.media_dir else "Root",
            path=folder,
            parent_id=parent_id,
            depth=depth,
        )
        self.collection_keys.setdefault(collection_id, [])

    def _is_ignored(self, path: Path) -> bool:
        if self.background_suffix and str(path).endswith(self.background_suffix):
            return True
        if self.uploaded_media_raw is not None:
            try:
                if path.resolve().is_relative_to(self.uploaded_media_raw.resolve()):
                    return True
            except Exception:
                # For Python <3.12 we fallback to manual check.
                raw_dir = self.uploaded_media_raw.resolve()
                try:
                    if raw_dir in path.resolve().parents:
                        return True
                except Exception:
                    return False
        return False

    def _resolve_shortcut(self, path: Path) -> Path | None:
        """
        Resolve Windows .lnk shortcut to its target path.
        Returns None if resolution fails or not a .lnk.
        """
        if os.name != "nt" or path.suffix.lower() != ".lnk":
            return None
        path_str = str(path)
        escaped = path_str.replace("'", "''")
        ps_cmd = (
            "$sh = New-Object -ComObject WScript.Shell;"
            f"$lnk = (Resolve-Path -LiteralPath '{escaped}').Path;"
            "$sc = $sh.CreateShortcut($lnk);"
            "$t = $sc.TargetPath;"
            "Write-Output $t"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
        except Exception as exc:
            logger.warning("Failed to resolve shortcut %s: %s", path, exc)
            return None
        target = (result.stdout or "").strip()
        if not target:
            logger.debug("Shortcut has empty target, skipped: %s", path)
            return None
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = (path.parent / target_path).resolve()
        if not target_path.exists():
            logger.debug("Shortcut target missing, skipped: %s -> %s", path, target_path)
            return None
        return target_path

    # endregion

    def sync_files(self):
        """
        Synchronize media files from the directory.
        Returns a list of new keys.
        """
        new_keys: list[str] = []
        found_keys: set[str] = set()
        self.collection_keys = {}
        self.collections = {}

        # Register all folders as collections (non-recursive grouping).
        self._register_collection(self.media_dir)
        for folder in sorted(self.media_dir.rglob("*")):
            if folder.is_dir() and not self._is_ignored(folder):
                self._register_collection(folder)

        for file in sorted(self.media_dir.rglob("*")):
            if not file.is_file() or self._is_ignored(file):
                continue
            link_target = self._resolve_shortcut(file)
            source_file = link_target or file
            if link_target:
                try:
                    source_file.relative_to(self.media_dir)
                except ValueError:
                    logger.debug("Shortcut target outside media dir skipped: %s -> %s", file, source_file)
                    continue
                logger.debug("Shortcut resolved: %s -> %s", file, source_file)
            mime_type, _ = mimetypes.guess_type(source_file)
            if not (mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/"))):
                logger.debug("Skipped non-media %s (mime=%s)", source_file, mime_type)
                continue

            try:
                rel_path = str(source_file.relative_to(self.media_dir)).replace("\\", "/")
            except Exception:
                logger.debug("Failed to build relative path for %s (likely outside media dir)", source_file)
                continue
            collection_id = self._collection_id(file)
            url = quote(rel_path)
            file_identity = self._file_identity(source_file)

            if file_identity in self.file_id_to_key:
                key = self.file_id_to_key[file_identity]
                media = super().get(key)
                if media:
                    updated = False
                    is_video = mime_type.startswith("video/")
                    if media.is_video != is_video:
                        media.is_video = is_video
                        updated = True
                    if media.file != rel_path or media.relative_path != url:
                        media.file = rel_path
                        media.relative_path = url
                        updated = True
                    if media.is_video and (media.duration is None or updated):
                        media.duration = get_video_duration(source_file)
                        updated = True
                    if updated:
                        self[key] = media
            else:
                key = hashlib.md5(self._canonical_path(source_file).encode("utf-8")).hexdigest()
                is_video = mime_type.startswith("video/")
                duration = get_video_duration(source_file) if is_video else None
                self[key] = MediaFile(relative_path=url, file=rel_path, is_video=is_video, duration=duration)
                self.file_id_to_key[file_identity] = key
                self.key_to_file_id[key] = file_identity
                new_keys.append(key)

            found_keys.add(key)
            coll_keys = self.collection_keys.setdefault(collection_id, [])
            if key not in coll_keys:
                coll_keys.append(key)

        for key in list(self.keys()):
            if key not in found_keys:
                try:
                    file_id = self.key_to_file_id.pop(key, None)
                    if file_id:
                        self.file_id_to_key.pop(file_id, None)
                finally:
                    del self[key]

        self.photo_keys = tuple(key for key, media in self.items() if not media.is_video)
        self.video_keys = tuple(key for key, media in self.items() if media.is_video)

        for cid, info in self.collections.items():
            info.files_count = len(self.collection_keys.get(cid, []))

        logger.debug("New files %s total %s", len(new_keys), len(self))
        return new_keys

    def __getitem__(self, key):
        item = super().__getitem__(key)
        if item is None or not item.relative_path:
            return None
        file_path = self.media_dir / item.relative_path
        if not file_path.exists():
            self.sync_files()
            return None
        return item

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

    def get_collections_tree(self) -> list[CollectionInfo]:
        """Return collection metadata ordered by path depth/name for rendering."""
        return sorted(
            self.collections.values(),
            key=lambda c: c.display_path.lower(),
        )

    def get_keys_for_collections(self, collection_ids: list[str] | tuple[str, ...]) -> list[str]:
        """
        Return unique media keys for the provided collections.
        Duplicates (symlinks/shortcuts) are removed via file identity mapping.
        """
        if not collection_ids:
            return []

        seen: set[str] = set()
        result: list[str] = []
        for cid in collection_ids:
            for key in self.collection_keys.get(cid, []):
                file_id = self.key_to_file_id.get(key, key)
                if file_id in seen:
                    continue
                seen.add(file_id)
                result.append(key)
        return result


if __name__ == "__main__":
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
