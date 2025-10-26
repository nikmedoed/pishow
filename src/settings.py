import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates

from src.device_manager import DeviceQueueManager
from src.media import MediaDict

load_dotenv()

MEDIA_PATH = '/media'
VIDEO_BACKGROUND_SUFFIX = ".background.jpg"
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gallery"))

UPLOADED_RAW_DIR = MEDIA_DIR / "uploaded_raw"
UPLOADED_DIR = MEDIA_DIR / "uploaded"
UPLOADED_RAW_DIR.mkdir(parents=True, exist_ok=True)
UPLOADED_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
CONVERT_LOCK_FILE = STORAGE_DIR / "converter.lock"
CONVERTER_THROTTLE_SECONDS = int(os.getenv("CONVERTER_THROTTLE_SECONDS", "30"))
CONVERTER_STARTUP_DELAY_SECONDS = int(
    os.getenv("CONVERTER_STARTUP_DELAY_SECONDS", "10")
)
CONVERTER_MAX_VIDEO_WIDTH = int(os.getenv("CONVERTER_MAX_VIDEO_WIDTH", "1920"))
CONVERTER_MAX_VIDEO_HEIGHT = int(os.getenv("CONVERTER_MAX_VIDEO_HEIGHT", "1080"))
CONVERTER_MAX_VIDEO_LONG_EDGE = int(os.getenv("CONVERTER_MAX_VIDEO_LONG_EDGE", "0"))
CONVERTER_MAX_VIDEO_SHORT_EDGE = int(os.getenv("CONVERTER_MAX_VIDEO_SHORT_EDGE", "0"))
CONVERTER_VIDEO_PRESET = os.getenv("CONVERTER_VIDEO_PRESET", "medium")
CONVERTER_HIGH_RES_PRESET = os.getenv("CONVERTER_HIGH_RES_PRESET", "veryfast")


def _positive_int_env(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


CONVERTER_FFMPEG_THREADS = _positive_int_env("CONVERTER_FFMPEG_THREADS")

_syncthing_auto_pause = os.getenv("SYNCTHING_AUTO_PAUSE", "false").strip().lower()
SYNCTHING_AUTO_PAUSE = _syncthing_auto_pause in {"1", "true", "yes", "on"}
SYNCTHING_API_URL = os.getenv("SYNCTHING_API_URL", "http://localhost:8384")
SYNCTHING_API_KEY = os.getenv("SYNCTHING_API_KEY")
SYNCTHING_FOLDER_ID = os.getenv("SYNCTHING_FOLDER_ID")

media_handler = MediaDict(MEDIA_DIR, VIDEO_BACKGROUND_SUFFIX, UPLOADED_RAW_DIR)
device_queue_manager = DeviceQueueManager(media_handler, STORAGE_DIR)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
