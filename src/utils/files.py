import datetime
import logging
import os
import subprocess
from pathlib import Path

from PIL import Image

from src.settings import VIDEO_BACKGROUND_SUFFIX

logger = logging.getLogger("media converter")


def count_files_recursive(directory):
    return sum(
        1
        for root, dirs, files in os.walk(directory)
        for file in files
        if not file.endswith(VIDEO_BACKGROUND_SUFFIX)
    )


def get_capture_date(img: Image.Image) -> datetime.datetime:
    """
    Attempt to extract the capture date from the image's EXIF data.
    Returns a datetime object if available, otherwise None.
    """
    try:
        exif = img.getexif()
        if exif:
            # EXIF tag 36867 is DateTimeOriginal; fallback to tag 306 (DateTime)
            dt_str = exif.get(36867) or exif.get(306)
            if dt_str:
                dt_str = dt_str.strip()
                return datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        logger.warning("Failed to extract image capture date: %s", e)
    return None


def get_video_capture_date(input_path: Path) -> datetime.datetime:
    """
    Use ffprobe to extract the video's creation time from metadata.
    Attempts to parse the ISO8601 string so that if a timezone offset is present it is preserved.
    If no offset is found, assumes UTC.
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format_tags=creation_time",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        creation_time = result.stdout.strip()
        if creation_time:
            # If the creation_time string ends with 'Z', it indicates UTC.
            if creation_time.endswith("Z"):
                creation_time = creation_time.rstrip("Z")
                dt = datetime.datetime.fromisoformat(creation_time)
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            else:
                try:
                    dt = datetime.datetime.fromisoformat(creation_time)
                except ValueError:
                    # Fallback: assume UTC if parsing fails
                    try:
                        dt = datetime.datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        dt = datetime.datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%S")
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
            # Convert to local timezone using the offset provided in metadata if any.
            return dt.astimezone()
    except Exception as e:
        logger.warning("Failed to extract video capture date for %s: %s", input_path.name, e)
    return None
