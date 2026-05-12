import asyncio
import importlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from src.settings import MEDIA_DIR, MEDIA_PATH
from src.utils.converter_watchdog import ConversionWatchdog
from src.utils.watchdg import media_observer

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class OptionalDirectoryStaticFiles(StaticFiles):
    async def check_config(self) -> None:
        try:
            await super().check_config()
        except (RuntimeError, OSError):
            # MEDIA_DIR may live on a removable/network disk. Missing media should
            # be a temporary 404, not an application-level crash.
            return

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except OSError:
            raise HTTPException(status_code=404)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: запускаем наблюдатель в отдельном потоке
    media_observer.start()
    conversion_watchdog = ConversionWatchdog()

    async def kickoff_conversion() -> None:
        await asyncio.sleep(0)
        conversion_watchdog.start()

    asyncio.create_task(kickoff_conversion())
    yield
    # Shutdown: останавливаем наблюдатель
    media_observer.stop()
    media_observer.join()
    logging.info("Media observer stopped.")
    conversion_watchdog.stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
app.mount(MEDIA_PATH, OptionalDirectoryStaticFiles(directory=str(MEDIA_DIR), check_dir=False), name="media")
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
