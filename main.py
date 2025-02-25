import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.device_manager import DeviceQueueManager
from src.media import MediaDict

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gallery"))
media_handler = MediaDict(MEDIA_DIR)
device_queue_manager = DeviceQueueManager(media_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not media_handler:
        media_handler.sync_files()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
templates = Jinja2Templates(directory="templates")


def get_device_id(request: Request, cookie_device_id: str) -> str:
    """
    Return the device ID from cookie if available.
    Otherwise, compute a new one based on raw User-Agent and client IP,
    update device info, and return the new ID.
    """
    if cookie_device_id:
        return cookie_device_id
    # Compute new device ID if cookie is missing.
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    new_device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_agent + client_ip))
    device_info = {
        "raw_user_agent": user_agent,
        "client_ip": client_ip,
    }
    device_queue_manager.update_device_info(new_device_id, device_info)
    logging.debug(f"New device registered: {new_device_id} with raw UA: {user_agent}")
    return new_device_id


@app.get("/", response_class=HTMLResponse)
async def get_media_page(
        request: Request,
        device_id: str = Cookie(None),
):
    # Use the cookie device_id if available; otherwise, compute a new one.
    device_id = get_device_id(request, device_id)
    try:
        media = device_queue_manager.get_next(device_id)
    except Exception as e:
        logging.error(f"Error retrieving media for device {device_id}: {e}")
        return HTMLResponse("Error: no media available", status_code=500)

    refresh_time = media.duration + 3 if media.is_video else 15

    response = templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "file_url": f"/media/{media.relative_path}",
            "refresh_time": refresh_time,
            "is_video": media.is_video,
        },
    )
    # Всегда устанавливаем device_id в куки.
    response.set_cookie(key="device_id", value=device_id, max_age=31536000, path="/", httponly=True)
    return response


@app.post("/pause")
async def pause():
    # Перенесённый роут для обработки паузы.
    return {"redirect_url": "/?refresh=false"}


@app.post("/next")
async def next_file():
    # Перенесённый роут для получения следующего файла.
    return {"redirect_url": "/"}
