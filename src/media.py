import hashlib
import logging
import mimetypes
import random
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
                 uploaded_media_raw: str = None,
                 *args, **kwargs):
        """
        Initialize the MediaDict.
        :param media_dir: Directory containing media files.
        """
        super().__init__(*args, **kwargs)
        self.media_dir = media_dir
        self.background_suffix = background_suffix
        self.uploaded_media_raw = uploaded_media_raw
        self.sync_files()

    def sync_files(self):
        """
        Synchronize media files from the directory.
        Returns a list of new keys.
        """
        new_keys = []
        found_keys = set()

        for file in self.media_dir.rglob("*"):
            if (self.background_suffix is not None and str(file).endswith(self.background_suffix)
                    or self.uploaded_media_raw is not None and file.is_relative_to(self.uploaded_media_raw)):
                continue
            mime_type, _ = mimetypes.guess_type(file)
            if not (mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/"))):
                continue

            rel_path = str(file.relative_to(self.media_dir)).replace("\\", "/")
            key = hashlib.md5(rel_path.encode("utf-8")).hexdigest()
            url = quote(rel_path)

            found_keys.add(key)
            if key not in self:
                if mime_type.startswith("image/"):
                    self[key] = MediaFile(relative_path=url, file=rel_path)
                else:
                    duration = get_video_duration(file)
                    self[key] = MediaFile(relative_path=url, file=rel_path, is_video=True, duration=duration)
                new_keys.append(key)

        for key in list(self.keys()):
            if key not in found_keys:
                del self[key]

        self.photo_keys = tuple(key for key, media in self.items() if not media.is_video)
        self.video_keys = tuple(key for key, media in self.items() if media.is_video)

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
