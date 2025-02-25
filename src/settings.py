import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates

from src.device_manager import DeviceQueueManager
from src.media import MediaDict

load_dotenv()

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gallery"))
media_handler = MediaDict(MEDIA_DIR)
device_queue_manager = DeviceQueueManager(media_handler)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
