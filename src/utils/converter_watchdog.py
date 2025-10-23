import logging
from pathlib import Path
from threading import Lock, Timer
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.settings import CONVERTER_THROTTLE_SECONDS, UPLOADED_RAW_DIR
from src.utils.converter_control import enqueue_new_files, is_conversion_running, start_conversion
from src.utils.converter_queue import ConversionQueue
from src.utils.converter_types import ALL_EXTENSIONS

logger = logging.getLogger("media converter")


class _ConversionHandler(FileSystemEventHandler):
    def __init__(self, throttle_seconds: int):
        self.throttle_seconds = max(throttle_seconds, 0)
        self._lock = Lock()
        self._timer: Optional[Timer] = None

    def _should_handle(self, src_path: str) -> bool:
        suffix = Path(src_path).suffix.lower()
        return suffix in ALL_EXTENSIONS

    def _schedule(self) -> None:
        delay = self.throttle_seconds
        if delay == 0:
            self._trigger()
            return
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = Timer(delay, self._trigger)
            self._timer.daemon = True
            self._timer.start()

    def _trigger(self) -> None:
        schedule_follow_up = False
        try:
            added = enqueue_new_files()
            running = is_conversion_running()
            if running:
                if added:
                    logger.info("Queued %s new files while converter is running", added)
                schedule_follow_up = True
                return

            queue = ConversionQueue()
            pending_total = len(queue.items)
            if pending_total:
                logger.info("Watchdog starting converter for %s pending files", pending_total)
                start_conversion()
        finally:
            with self._lock:
                if schedule_follow_up:
                    if self._timer:
                        self._timer.cancel()
                    self._timer = Timer(max(self.throttle_seconds, 1), self._trigger)
                    self._timer.daemon = True
                    self._timer.start()
                else:
                    self._timer = None

    def cancel(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def on_created(self, event):
        if event.is_directory or not self._should_handle(event.src_path):
            return
        self._schedule()

    def on_moved(self, event):
        if event.is_directory or not self._should_handle(event.dest_path):
            return
        self._schedule()


class ConversionWatchdog:
    def __init__(self, throttle_seconds: int = CONVERTER_THROTTLE_SECONDS):
        self.handler = _ConversionHandler(throttle_seconds)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(UPLOADED_RAW_DIR), recursive=True)

    def start(self) -> None:
        logger.info("Conversion watchdog started with throttle %ss", self.handler.throttle_seconds)
        self.observer.start()
        try:
            start_conversion()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to auto-start converter on watchdog init: %s", exc)

    def stop(self) -> None:
        self.handler.cancel()
        self.observer.stop()
        self.observer.join()
        logger.info("Conversion watchdog stopped")
