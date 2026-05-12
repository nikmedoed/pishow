import logging
from pathlib import Path
from threading import Event, Thread

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.settings import (
    CONVERT_LOCK_FILE,
    MEDIA_RETRY_INTERVAL_SECONDS,
    media_handler,
    MEDIA_DIR,
    UPLOADED_RAW_DIR,
    ensure_media_directories,
)

logger = logging.getLogger("Watchdog")

class MediaFolderHandler(FileSystemEventHandler):
    def __init__(self, media_dict):
        self.media_dict = media_dict

    def _should_ignore(self, event):
        event_path = Path(event.src_path).resolve()
        if UPLOADED_RAW_DIR.resolve() in event_path.parents:
            return True
        return False

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event) or CONVERT_LOCK_FILE.exists():
            return
        logger.debug("Watchdog syncing after create: %s", event.src_path)
        self.media_dict.sync_files()

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(event) or CONVERT_LOCK_FILE.exists():
            return
        logger.debug("Watchdog syncing after delete: %s", event.src_path)
        self.media_dict.sync_files()


class MediaObserver:
    def __init__(self):
        self._stop_event = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self._observer = None

    @staticmethod
    def _stop_observer(observer):
        try:
            observer.stop()
        except RuntimeError:
            pass
        observer.join()

    def _run(self):
        while not self._stop_event.is_set():
            if not ensure_media_directories():
                self._stop_event.wait(MEDIA_RETRY_INTERVAL_SECONDS)
                continue

            observer = Observer()
            event_handler = MediaFolderHandler(media_handler)
            observer_started = False
            try:
                media_handler.sync_files()
                observer.schedule(event_handler, str(MEDIA_DIR), recursive=True)
                observer.start()
                observer_started = True
            except OSError as exc:
                logger.warning("Media observer waiting for %s: %s", MEDIA_DIR, exc)
                if observer_started:
                    self._stop_observer(observer)
                self._stop_event.wait(MEDIA_RETRY_INTERVAL_SECONDS)
                continue

            self._observer = observer
            logger.info("Media observer started for %s", MEDIA_DIR)
            while not self._stop_event.wait(MEDIA_RETRY_INTERVAL_SECONDS):
                if not ensure_media_directories() or not observer.is_alive():
                    logger.warning("Media observer paused until %s is available", MEDIA_DIR)
                    self._stop_observer(observer)
                    break
            self._observer = None

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        observer = self._observer
        if observer is not None:
            self._stop_observer(observer)
            self._observer = None

    def join(self):
        if self._thread.is_alive():
            self._thread.join(timeout=MEDIA_RETRY_INTERVAL_SECONDS + 1)


media_observer = MediaObserver()
