import logging
from pathlib import Path
from threading import Lock, Thread, Timer
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.settings import (
    CONVERTER_STARTUP_DELAY_SECONDS,
    CONVERTER_THROTTLE_SECONDS,
    UPLOADED_RAW_DIR,
)
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
    def __init__(
        self,
        throttle_seconds: int = CONVERTER_THROTTLE_SECONDS,
        startup_delay_seconds: int = CONVERTER_STARTUP_DELAY_SECONDS,
    ):
        self.handler = _ConversionHandler(throttle_seconds)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(UPLOADED_RAW_DIR), recursive=True)
        self.startup_delay_seconds = max(startup_delay_seconds, 0)
        self._state_lock = Lock()
        self._start_timer: Optional[Timer] = None
        self._started = False
        self._stopped = False

    def _start_converter_in_background(self) -> None:
        def _kickoff() -> None:
            try:
                start_conversion()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to auto-start converter on watchdog init: %s", exc)

        Thread(target=_kickoff, daemon=True).start()

    def _do_start(self, auto_start: bool) -> None:
        with self._state_lock:
            if self._stopped:
                logger.debug("Skipping conversion watchdog start because it was stopped")
                return
            if self._started:
                logger.debug("Conversion watchdog already started")
                return
            self._started = True

        self.observer.start()
        logger.info(
            "Conversion watchdog started with throttle %ss",
            self.handler.throttle_seconds,
        )
        if auto_start:
            self._start_converter_in_background()

    def start(self, auto_start: bool = True, delay_seconds: Optional[int] = None) -> None:
        start_delay = self.startup_delay_seconds if delay_seconds is None else max(delay_seconds, 0)

        def _run_start() -> None:
            with self._state_lock:
                self._start_timer = None
            self._do_start(auto_start)

        with self._state_lock:
            if self._stopped:
                logger.debug("Skipping conversion watchdog scheduling because it was stopped")
                return
            if self._started:
                logger.debug("Conversion watchdog already started; ignoring schedule request")
                return
            if self._start_timer:
                self._start_timer.cancel()
                self._start_timer = None

            if start_delay > 0:
                timer = Timer(start_delay, _run_start)
                timer.daemon = True
                self._start_timer = timer
                logger.info(
                    "Conversion watchdog startup deferred for %ss",
                    start_delay,
                )
                timer.start()
                return

        _run_start()

    def kickoff(self) -> None:
        with self._state_lock:
            if self._stopped:
                logger.debug("Skipping converter kickoff because watchdog is stopped")
                return
        self._start_converter_in_background()

    def stop(self) -> None:
        with self._state_lock:
            self._stopped = True
            timer = self._start_timer
            self._start_timer = None
            started = self._started
        if timer:
            timer.cancel()
        self.handler.cancel()
        if started:
            self.observer.stop()
            self.observer.join()
        logger.info("Conversion watchdog stopped")
