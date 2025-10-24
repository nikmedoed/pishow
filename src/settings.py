import os
from pathlib import Path

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

media_handler = MediaDict(MEDIA_DIR, VIDEO_BACKGROUND_SUFFIX, UPLOADED_RAW_DIR)
device_queue_manager = DeviceQueueManager(media_handler, STORAGE_DIR)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
