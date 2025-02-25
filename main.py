import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Cookie
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src.media import MediaDict
from src.device_manager import DeviceQueueManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

load_dotenv()

# Set media directory from environment or use default "gallery"
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gallery"))
# Initialize MediaDict (auto-syncs files)
media_handler = MediaDict(MEDIA_DIR)
# Initialize DeviceQueueManager using media_handler as the source dictionary
device_queue_manager = DeviceQueueManager(media_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not media_handler:
        media_handler.sync_files()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_media_page(
    request: Request,
    device_id: str = Cookie(None),
):
    # Determine if device_id exists; if not, generate a new one.
    new_id = False
    if not device_id:
        device_id = str(uuid.uuid4())
        new_id = True

    # Retrieve the next media file for the given device_id.
    media = device_queue_manager.get_next(device_id)
    refresh_time = media.duration + 3 if media.is_video else 15

    # Create TemplateResponse.
    response = templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "file_url": f"/media/{media.relative_path}",
            "refresh_time": refresh_time,
            "is_video": media.is_video,
        },
    )
    # Set cookie if a new device_id was generated.
    if new_id:
        response.set_cookie(key="device_id", value=device_id, max_age=31536000, path="/", httponly=True)
    return response

@app.post("/pause")
async def pause():
    return {"redirect_url": "/?refresh=false"}

@app.post("/next")
async def next_file():
    return {"redirect_url": "/"}
