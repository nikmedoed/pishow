from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media import MediaHandler
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MEDIA_DIR = Path(r"gallery")
media_handler = MediaHandler(MEDIA_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not media_handler.media_files:
        media_handler.reset()
    yield


app = FastAPI()
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def get_media_page(request: Request, refresh: bool = True):
    try:
        media = media_handler.next() if refresh else media_handler.get_current()
        refresh_time = media.duration + 3 if media.is_video else 15
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "file_url": f"/media/{media.relative_path}",
                "refresh_time": refresh and refresh_time,
                "is_video": media.is_video,
            },
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="No media files found.")


@app.post("/pause")
async def pause():
    return {"redirect_url": "/?refresh=false"}


@app.post("/next")
async def next_file():
    media_handler.next()
    return {"redirect_url": "/"}
