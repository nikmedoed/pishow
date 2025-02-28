import logging
from pathlib import Path
from threading import Thread

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.settings import CONVERT_LOCK_FILE, media_handler, MEDIA_DIR, UPLOADED_RAW_DIR

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
        logger.debug("Watchdog on_created")
        if not event.is_directory and not CONVERT_LOCK_FILE.exists():
            self.media_dict.sync_files()

    def on_deleted(self, event):
        logger.debug("Watchdog on_deleted")
        if not event.is_directory and not CONVERT_LOCK_FILE.exists():
            self.media_dict.sync_files()


event_handler = MediaFolderHandler(media_handler)
observer = Observer()
observer.schedule(event_handler, str(MEDIA_DIR), recursive=True)


def run_observer():
    observer.start()
    observer.join()


observer_thread = Thread(target=run_observer, daemon=True)
