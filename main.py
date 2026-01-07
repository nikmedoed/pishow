import asyncio
import importlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.settings import MEDIA_DIR, MEDIA_PATH, deduplicator
from src.utils.converter_watchdog import ConversionWatchdog
from src.utils.watchdg import observer_thread, observer

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: запускаем наблюдатель в отдельном потоке
    observer_thread.start()
    logging.info("Media observer started.")
    conversion_watchdog = ConversionWatchdog()
    deduplicator.start()

    async def kickoff_conversion() -> None:
        await asyncio.sleep(0)
        conversion_watchdog.start()

    asyncio.create_task(kickoff_conversion())
    yield
    # Shutdown: останавливаем наблюдатель
    observer.stop()
    observer.join()
    logging.info("Media observer stopped.")
    deduplicator.stop()
    conversion_watchdog.stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
app.mount(MEDIA_PATH, StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/static", StaticFiles(directory="src/static"), name="static")

routes_path = os.path.join(os.path.dirname(__file__), "src", "routes")

for file in os.listdir(routes_path):
    try:
        module_name = os.path.splitext(file)[0]
        imported_module = importlib.import_module(f"src.routes.{module_name}")
        if hasattr(imported_module, "router"):
            app.include_router(imported_module.router)
    except Exception as e:
        logging.warning(f"Skipped {file} :: {e}")
