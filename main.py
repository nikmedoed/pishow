import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes.old import router as old
from src.routes.settings import router as settings
from src.settings import MEDIA_DIR, MEDIA_PATH

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

app = FastAPI()
app.mount(MEDIA_PATH, StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/static", StaticFiles(directory="src/static"), name="static")

app.include_router(old)
app.include_router(settings, prefix="/go", tags=["settings"])
