import random
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from pymediainfo import MediaInfo

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png"}
SUPPORTED_VIDEOS = {".mp4", ".mov"}


@dataclass
class MediaFile:
    relative_path: str
    is_video: bool = False
    duration: int = None


def get_video_duration(file_path: Path) -> int:
    """Get the duration of a video file in seconds."""
    try:
        media_info = MediaInfo.parse(file_path)
        for track in media_info.tracks:
            if track.track_type == "Video" and track.duration:
                return int(track.duration / 1000)
    except Exception as e:
        print(f"Error fetching video duration for {file_path}: {e}")
    return 0


class MediaHandler:
    def __init__(self, media_dir: Path,
                 supported_images: set = SUPPORTED_IMAGES,
                 supported_videos: set = SUPPORTED_VIDEOS,
                 shuffle_on_load: bool = True):
        """
        Initialize the media handler.
        Args:
            media_dir (Path): Directory containing media files.
            supported_images (set): Supported image file extensions.
            supported_videos (set): Supported video file extensions.
            shuffle_on_load (bool): Shuffle media files after loading.
        """
        self.media_dir = media_dir
        self.supported_images = supported_images
        self.supported_videos = supported_videos
        self.media_files = self._load_media_files()
        self.current_index = -1

        if shuffle_on_load:
            random.shuffle(self.media_files)

    def _load_media_files(self):
        """Load all media files from the directory."""
        files = []
        for file in self.media_dir.rglob("*"):
            low = file.suffix.lower()
            url = quote(str(file.relative_to(self.media_dir)).replace("\\", "/"))
            if low in self.supported_images:
                files.append(MediaFile(relative_path=url))
            elif low in self.supported_videos:
                duration = get_video_duration(file)
                files.append(MediaFile(relative_path=url, is_video=True, duration=duration))
        return files

    def next(self):
        """Get the next media file."""
        if not self.media_files:
            raise ValueError("No media files available.")

        self.current_index += 1
        if self.current_index >= len(self.media_files):
            random.shuffle(self.media_files)
            self.current_index = 0

        return self.media_files[self.current_index]

    def reset(self):
        """Reset the media handler to the initial state."""
        self.current_index = -1
        random.shuffle(self.media_files)

    def get_current(self):
        """Get the current media file without advancing."""
        if not self.media_files:
            raise ValueError("No media file is currently selected.")
        if self.current_index == -1:
            self.current_index = 0
        return self.media_files[self.current_index]


# Example usage
if __name__ == "__main__":
    MEDIA_DIR = Path("Y:/gallery")

    media_handler = MediaHandler(MEDIA_DIR)

    try:
        for _ in range(10):
            media = media_handler.next()
            print(f"File: {media.relative_path}, is_video: {media.is_video}, Duration: {media.duration}")
    except ValueError as e:
        print(f"Error: {e}")
