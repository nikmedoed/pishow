import datetime
import logging
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo  # Python 3.9+

import httpx
from PIL import Image

# Register HEIF opener so that Pillow can read HEIC files.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logging.info("pillow-heif registered successfully")
except Exception as e:
    logging.warning("pillow-heif could not be registered: %s", e)

from src.settings import UPLOADED_DIR, UPLOADED_RAW_DIR

logger = logging.getLogger("media converter")
logging.basicConfig(level=logging.INFO)

# Define supported extensions.
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.heic', '.png', '.bmp', '.tiff', '.tif', '.webp']
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv']


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


def get_new_filename(original_name: str, capture_date: datetime.datetime = None, ext: str = None) -> str:
    """
    Generate a new filename using the capture date (if available) and enforce a given extension.
    Format: YYYYMMDD_HHMMSS-basename.ext
    """
    if capture_date is None:
        capture_date = datetime.datetime.now()
    dt_str = capture_date.strftime("%Y%m%d_%H%M%S")
    base = Path(original_name).stem
    if ext is None:
        ext = Path(original_name).suffix
    return f"{dt_str}-{base}{ext}"


def convert_video(input_path: Path, output_path: Path):
    """
    Convert a video file to MP4 using ffmpeg.
    Uses a medium preset and forces a maximum level of 4.0.
    """
    cmd = [
        "ffmpeg", "-i", str(input_path),
        "-c:v", "libx264", "-preset", "medium", "-crf", "30",
        "-profile:v", "high", "-level:v", "4.0",
        "-pix_fmt", "yuv420p", "-movflags", "faststart",
        "-c:a", "aac", "-b:a", "128k", "-map_metadata", "-1",
        str(output_path)
    ]
    logger.info("Converting video: %s", input_path.name)
    subprocess.run(cmd, check=True)


def convert_image(input_path: Path) -> str:
    """
    Convert an image (JPEG, HEIC, PNG, BMP, TIFF, etc.) to JPG using Pillow.
    The new filename is generated based on the capture date (if available).
    The image is resized if it exceeds 3840x2160.
    Metadata is removed by rebuilding the image from pixel data.
    Returns the new filename.
    """
    try:
        with Image.open(input_path) as img:
            # Ensure image is in RGB mode for JPEG.
            img = img.convert("RGB")
            capture_date = get_capture_date(img)
            new_filename = get_new_filename(input_path.name, capture_date, ext=".jpg")
            output_path = UPLOADED_DIR / new_filename

            width, height = img.size
            max_width, max_height = 3840, 2160
            ratio = min(1, max_width / width, max_height / height)
            if ratio < 1:
                new_size = (int(width * ratio), int(height * ratio))
                logger.info("Resizing image %s from %s to %s", input_path.name, img.size, new_size)
                img = img.resize(new_size, Image.LANCZOS)
            else:
                logger.info("Image %s dimensions %s are within allowed limits", input_path.name, img.size)

            # Remove metadata by creating a new image from pixel data.
            data = list(img.getdata())
            img_no_meta = Image.new(img.mode, img.size)
            img_no_meta.putdata(data)

            img_no_meta.save(output_path, "JPEG", quality=60, optimize=True)
            logger.info("Image saved: %s", output_path.name)
            return new_filename
    except Exception as e:
        logger.error("Error converting image %s: %s", input_path.name, e)
        raise


def process_files(server_port: str):
    for file in UPLOADED_RAW_DIR.iterdir():
        if not file.is_file():
            continue

        suffix = file.suffix.lower()
        try:
            if suffix in VIDEO_EXTENSIONS:
                video_date = get_video_capture_date(file)
                new_filename = get_new_filename(file.name, video_date, ext=".mp4")
                output_path = UPLOADED_DIR / new_filename
                convert_video(file, output_path)
            elif suffix in IMAGE_EXTENSIONS:
                new_filename = convert_image(file)
            else:
                logger.info("Unsupported file type: %s", file.name)
                continue

            file.unlink()
            logger.info("Deleted original file: %s", file.name)
        except Exception as e:
            logger.error("Error processing file %s: %s", file.name, e)

    try:
        url = f"http://localhost:{server_port}/admin/update_content"
        response = httpx.post(url, follow_redirects=True)
        if response.status_code in [200, 303]:
            logger.info("Server update successful: %s", response.text)
        else:
            logger.error("Server update failed: %s", response.text)
    except Exception as e:
        logger.error("Error calling /admin/update_content: %s", e)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = "8000"
    process_files(port)
