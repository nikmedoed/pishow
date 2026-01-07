import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("deduplicator")


def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _iter_media_files(
    media_dir: Path,
    background_suffix: str = "",
    skip_dir: Optional[Path] = None,
) -> Iterable[Path]:
    media_dir = media_dir.resolve()
    skip_dir_resolved = skip_dir.resolve() if skip_dir else None
    for path in media_dir.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink():
            continue
        if _is_hidden(path.relative_to(media_dir)):
            continue
        if background_suffix and str(path).endswith(background_suffix):
            continue
        if skip_dir_resolved and path.resolve().is_relative_to(skip_dir_resolved):
            continue
        yield path


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _same_file(a: Path, b: Path) -> bool:
    try:
        sa = a.stat()
        sb = b.stat()
    except FileNotFoundError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


class Deduplicator:
    def __init__(
        self,
        media_dir: Path,
        background_suffix: str = "",
        skip_dir: Optional[Path] = None,
        idle_seconds: int = 900,
        lock_file: Optional[Path] = None,
        run_on_start: bool = True,
    ):
        self.media_dir = media_dir
        self.background_suffix = background_suffix
        self.skip_dir = skip_dir
        self.idle_seconds = idle_seconds
        self.lock_file = lock_file
        self.run_on_start = run_on_start

        self._last_change: Optional[float] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._runner_thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        if not self._runner_thread.is_alive():
            if self.run_on_start and self._last_change is None:
                # Force a run soon after start to catch pre-existing changes.
                self._last_change = time.time() - self.idle_seconds
            self._runner_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._runner_thread.is_alive():
            self._runner_thread.join(timeout=5)

    def mark_change(self):
        self._last_change = time.time()

    def _loop(self):
        while not self._stop_event.is_set():
            self.check_and_run()
            self._stop_event.wait(30)

    def check_and_run(self):
        if self._last_change is None:
            return
        if self.lock_file and self.lock_file.exists():
            return
        now = time.time()
        if now - self._last_change < self.idle_seconds:
            return
        # Clear the marker before running to avoid retrigger storm on failures.
        self._last_change = None
        try:
            self._dedup()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Deduplication failed: %s", exc)

    def _dedup(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            logger.info("Deduplication started.")
            hash_to_primary: dict[str, Path] = {}
            replaced = 0
            scanned = 0

            for path in _iter_media_files(self.media_dir, self.background_suffix, self.skip_dir):
                scanned += 1
                try:
                    file_hash = _file_hash(path)
                except Exception as exc:
                    logger.warning("Skip hashing %s: %s", path, exc)
                    continue

                primary = hash_to_primary.get(file_hash)
                if primary is None:
                    hash_to_primary[file_hash] = path
                    continue

                if _same_file(primary, path):
                    continue

                if not primary.exists():
                    hash_to_primary[file_hash] = path
                    continue

                temp_path = path.with_suffix(path.suffix + ".dedup_tmp")
                try:
                    path.rename(temp_path)
                    os.link(primary, path)
                    temp_path.unlink(missing_ok=True)
                    replaced += 1
                    logger.debug("Replaced duplicate %s with hardlink to %s", path, primary)
                except Exception as exc:
                    logger.warning("Failed to replace %s with link to %s: %s", path, primary, exc)
                    if temp_path.exists():
                        temp_path.rename(path)

            logger.info("Deduplication finished: scanned %s files, replaced %s duplicates.", scanned, replaced)
        finally:
            self._lock.release()
