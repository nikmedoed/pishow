from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import random

app = FastAPI()

# Конфигурация
MEDIA_DIR = Path("Y:/gallery")
SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")
SUPPORTED_VIDEOS = (".mp4",)
MEDIA_FILES = []
CURRENT_INDEX = 0
IS_PAUSED = False

# Шаблоны
templates = Jinja2Templates(directory="templates")

# Раздача статики
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


# Функция инициализации
def initialize_media():
    global MEDIA_FILES
    files = [
        str(file.relative_to(MEDIA_DIR))  # Сохраняем относительный путь
        for file in MEDIA_DIR.rglob("*")
        if file.suffix.lower() in SUPPORTED_IMAGES + SUPPORTED_VIDEOS
    ]
    random.shuffle(files)
    MEDIA_FILES = files


# Инициализация при запуске
@app.on_event("startup")
async def startup_event():
    initialize_media()


# Главная страница (рендер из шаблона)
@app.get("/")
async def get_slideshow_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Получить следующий файл
@app.get("/next")
async def next_file():
    global CURRENT_INDEX, IS_PAUSED
    if IS_PAUSED:
        return {"status": "paused", "message": "Playback is paused."}
    if not MEDIA_FILES:
        raise HTTPException(status_code=404, detail="No media files found.")

    CURRENT_INDEX = (CURRENT_INDEX + 1) % len(MEDIA_FILES)
    file = MEDIA_FILES[CURRENT_INDEX]
    return {"file_url": f"/media/{file}", "is_video": file.endswith(SUPPORTED_VIDEOS)}


# Получить предыдущий файл
@app.get("/prev")
async def prev_file():
    global CURRENT_INDEX, IS_PAUSED
    if IS_PAUSED:
        return {"status": "paused", "message": "Playback is paused."}
    if not MEDIA_FILES:
        raise HTTPException(status_code=404, detail="No media files found.")

    CURRENT_INDEX = (CURRENT_INDEX - 1) % len(MEDIA_FILES)
    file = MEDIA_FILES[CURRENT_INDEX]
    return {"file_url": f"/media/{file}", "is_video": file.endswith(SUPPORTED_VIDEOS)}


# Пауза воспроизведения
@app.post("/pause")
async def pause():
    global IS_PAUSED
    IS_PAUSED = True
    return {"status": "paused"}


# Возобновление воспроизведения
@app.post("/resume")
async def resume():
    global IS_PAUSED
    IS_PAUSED = False
    return {"status": "playing"}


# Сброс прогресса
@app.post("/reset")
async def reset():
    global CURRENT_INDEX
    CURRENT_INDEX = 0
    return {"status": "reset", "current_index": CURRENT_INDEX}
