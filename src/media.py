import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from pymediainfo import MediaInfo

@dataclass
class MediaFile:
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
        print(f"Error fetching video duration for {file_path}: {e}")
    return 0

def compute_key_and_url(file: Path, media_dir: Path):
    """Compute a unique key (MD5 of the relative path) and URL for the file."""
    rel_path = str(file.relative_to(media_dir)).replace("\\", "/")
    key = hashlib.md5(rel_path.encode("utf-8")).hexdigest()
    url = quote(rel_path)
    return key, url

class MediaDict(dict):
    def __init__(self, media_dir: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.media_dir = media_dir
        self.sync_files()

    def sync_files(self):
        """
        Incrementally synchronize the dictionary with the files in the directory:
          - Add new image/video files.
          - Remove keys for files that no longer exist.
        Returns a list of new keys.
        """
        new_keys = []
        found_keys = set()

        for file in self.media_dir.rglob("*"):
            mime_type, _ = mimetypes.guess_type(file)
            if not (mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/"))):
                continue

            key, url = compute_key_and_url(file, self.media_dir)
            found_keys.add(key)
            if key not in self:
                if mime_type.startswith("image/"):
                    self[key] = MediaFile(relative_path=url)
                else:
                    duration = get_video_duration(file)
                    self[key] = MediaFile(relative_path=url, is_video=True, duration=duration)
                new_keys.append(key)

        for key in list(self.keys()):
            if key not in found_keys:
                del self[key]

        return new_keys

    def __getitem__(self, key):
        # Override to check if the file exists on disk
        item = super().__getitem__(key)
        if item is None or not item.relative_path:
            return None
        file_path = self.media_dir / item.relative_path
        if not file_path.exists():
            self.sync_files()
            return None
        return item

if __name__ == '__main__':
    # For testing purposes: define the media directory
    media_dir = Path("../../gallery")
    media_dict = MediaDict(media_dir)

    print("Found media files:")
    for key, media in media_dict.items():
        file_type = "Video" if media.is_video else "Image"
        duration_str = f", Duration: {media.duration} sec" if media.is_video else ""
        print(f"Key: {key} | {file_type} | File: {media.relative_path}{duration_str}")

    new_keys = media_dict.sync_files()
    if new_keys:
        print("\nNew files added with keys:")
        for key in new_keys:
            print(key)
    else:
        print("\nNo new files found.")
