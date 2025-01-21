from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pathlib import Path
from urllib.parse import quote
import random
import ffmpeg

app = FastAPI()

# Конфигурация
MEDIA_DIR = Path("Y:/gallery")
SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")
SUPPORTED_VIDEOS = (".mp4",)
MEDIA_FILES = []
CURRENT_INDEX = 0

# Шаблоны
templates = Jinja2Templates(directory="templates")

# Статические файлы
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# Инициализация медиафайлов
def initialize_media():
    global MEDIA_FILES
    files = [
        quote(str(file.relative_to(MEDIA_DIR)).replace("\\", "/"))  # Корректная кодировка
        for file in MEDIA_DIR.rglob("*")
        if file.suffix.lower() in SUPPORTED_IMAGES + SUPPORTED_VIDEOS
    ]
    random.shuffle(files)
    MEDIA_FILES = files


@app.on_event("startup")
async def startup_event():
    initialize_media()


def get_video_duration(file_path: Path) -> int:
    try:
        probe = ffmpeg.probe(str(file_path))
        duration = float(probe['format']['duration'])
        return int(duration)
    except Exception:
        return 0


@app.get("/", response_class=HTMLResponse)
async def get_media_page(request: Request):
    global CURRENT_INDEX
    if not MEDIA_FILES:
        raise HTTPException(status_code=404, detail="No media files found.")

    file = MEDIA_FILES[CURRENT_INDEX]
    CURRENT_INDEX = (CURRENT_INDEX + 1) % len(MEDIA_FILES)

    file_path = MEDIA_DIR / file
    if file_path.suffix.lower() in SUPPORTED_VIDEOS:
        refresh_time = get_video_duration(file_path) + 4
        is_video = True
    else:
        refresh_time = 7
        is_video = False

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "file_url": f"/media/{file}",
            "refresh_time": refresh_time,
            "is_video": is_video
        }
    )
