import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes.old import router as old
from src.settings import MEDIA_DIR

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

app = FastAPI()
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.include_router(old)
