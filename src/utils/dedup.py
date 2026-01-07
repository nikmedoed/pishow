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
            logger.info(
                "Deduplicator started (idle=%ss, skip_dir=%s, background_suffix=%s)",
                self.idle_seconds,
                self.skip_dir,
                self.background_suffix,
            )
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
            duplicates_seen = 0
            scanned = 0
            already_linked = 0
            cross_fs_skipped = 0
            hash_failed = 0
            link_failed = 0
            stat_failed = 0
            inode_seen = set()

            files = sorted(_iter_media_files(self.media_dir, self.background_suffix, self.skip_dir))
            for path in files:
                scanned += 1
                try:
                    path_stat = path.stat()
                except FileNotFoundError:
                    stat_failed += 1
                    continue

                inode_key = (path_stat.st_dev, path_stat.st_ino)
                if inode_key in inode_seen:
                    already_linked += 1
                    logger.debug("Skip already-linked inode: %s", path)
                    continue
                inode_seen.add(inode_key)

                try:
                    file_hash = _file_hash(path)
                except Exception as exc:
                    logger.warning("Skip hashing %s: %s", path, exc)
                    hash_failed += 1
                    continue

                primary = hash_to_primary.get(file_hash)
                if primary is None:
                    hash_to_primary[file_hash] = path
                    continue

                duplicates_seen += 1

                if _same_file(primary, path):
                    already_linked += 1
                    logger.debug("Duplicate already linked: %s -> %s", path, primary)
                    continue

                if not primary.exists():
                    hash_to_primary[file_hash] = path
                    continue

                # Hardlinks require same filesystem.
                try:
                    primary_stat = primary.stat()
                except FileNotFoundError:
                    continue
                if primary_stat.st_dev != path_stat.st_dev:
                    logger.warning(
                        "Skip dedup across filesystems: %s (dev %s) vs %s (dev %s)",
                        path,
                        path_stat.st_dev,
                        primary,
                        primary_stat.st_dev,
                    )
                    cross_fs_skipped += 1
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
                    link_failed += 1

            logger.info(
                (
                    "Deduplication finished: scanned=%s, duplicates=%s, replaced=%s, "
                    "already_linked=%s, cross_fs_skipped=%s, hash_failed=%s, link_failed=%s, stat_failed=%s"
                ),
                scanned,
                duplicates_seen,
                replaced,
                already_linked,
                cross_fs_skipped,
                hash_failed,
                link_failed,
                stat_failed,
            )
        finally:
            self._lock.release()
