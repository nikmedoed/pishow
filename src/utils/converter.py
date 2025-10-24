import json
import logging
import os
import re
import signal
import subprocess
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from PIL import Image

from src.settings import (
    CONVERT_LOCK_FILE,
    CONVERTER_HIGH_RES_PRESET,
    CONVERTER_MAX_VIDEO_HEIGHT,
    CONVERTER_MAX_VIDEO_LONG_EDGE,
    CONVERTER_MAX_VIDEO_SHORT_EDGE,
    CONVERTER_MAX_VIDEO_WIDTH,
    CONVERTER_VIDEO_PRESET,
    UPLOADED_DIR,
    UPLOADED_RAW_DIR,
)
from src.utils.conversion_state import update_state
from src.utils.converter_queue import ConversionQueue, QueueItem
from src.utils.files import get_capture_date, get_video_capture_date

try:  # pragma: no cover - optional dependency
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass

logger = logging.getLogger("media converter")


def _debug_enabled() -> bool:
    value = os.getenv("DEBUG")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configure_logging() -> None:
    debug_enabled = _debug_enabled()
    logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    else:
        logger.propagate = True

    pillow_level = logging.INFO if debug_enabled else logging.WARNING
    for name in ("PIL", "PIL.TiffImagePlugin"):
        pillow_logger = logging.getLogger(name)
        pillow_logger.setLevel(pillow_level)
        pillow_logger.propagate = False


_configure_logging()

STOP_EVENT = Event()


def _handle_signal(signum, _frame) -> None:  # pragma: no cover - signal handler
    if not STOP_EVENT.is_set():
        logger.info("Received signal %s. Converter will stop soon.", signum)
    STOP_EVENT.set()


def _install_signal_handlers() -> None:  # pragma: no cover - signal handling
    for candidate in (getattr(signal, "SIGUSR1", None), signal.SIGTERM, getattr(signal, "SIGINT", None)):
        if candidate is None:
            continue
        try:
            signal.signal(candidate, _handle_signal)
        except (AttributeError, ValueError):
            continue

IMAGE_MAX_WIDTH = 3840
IMAGE_MAX_HEIGHT = 2160
IMAGE_QUALITY = 60


class StopRequested(Exception):
    """Raised when the worker should abort and exit."""


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_datetime_from_name(name: str) -> Optional[datetime]:
    base = Path(name).stem
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_ ]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})", base)
    if match:
        parts = [int(value) for value in match.groups()]
        try:
            return datetime(*parts)
        except ValueError:
            return None
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", base)
    if match:
        y, m, d = [int(value) for value in match.groups()]
        try:
            return datetime(y, m, d)
        except ValueError:
            return None
    return None


def _clean_base_name(original_name: str) -> str:
    base = Path(original_name).stem
    base = re.sub(r"\(\d+\)$", "", base)
    base = re.sub(r"^(\d{4}[-_]?\d{2}[-_]?\d{2}([-_ ]?\d{2}[-_]?\d{2}[-_]?\d{2})?)", "", base)
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"[^A-Za-z0-9-_]", "-", base)
    base = re.sub(r"[-_]{2,}", "-", base)
    return base.strip("-_")


def get_new_filename(original_name: str, capture_date: Optional[datetime] = None, ext: Optional[str] = None) -> str:
    capture = capture_date or _parse_datetime_from_name(original_name) or _now()
    if capture.tzinfo:
        capture = capture.astimezone().replace(tzinfo=None)
    suffix = ext if ext is not None else Path(original_name).suffix
    suffix = suffix.lower() if suffix else ""
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    base = _clean_base_name(original_name)
    date_part = capture.strftime("%Y%m%d")
    time_part = capture.strftime("%H%M%S")
    if base:
        return f"{date_part}-{time_part}-{base}{suffix}"
    return f"{date_part}-{time_part}{suffix}"


def _write_error_log(file_path: Path, error_text: str) -> None:
    file_path.with_suffix(".txt").write_text(error_text, encoding="utf-8")


def _remove_error_log(file_path: Path) -> None:
    error_path = file_path.with_suffix(".txt")
    if error_path.exists():
        error_path.unlink()


def _probe_video_duration(input_path: Path) -> Optional[float]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except Exception as exc:  # pragma: no cover - depends on ffprobe availability
        logger.warning("Unable to read duration for %s: %s", input_path.name, exc)
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _probe_video_dimensions(input_path: Path) -> Optional[tuple[int, int]]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=,:p=0",
        str(input_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except Exception as exc:  # pragma: no cover - depends on ffprobe availability
        logger.warning("Unable to read dimensions for %s: %s", input_path.name, exc)
        return None
    line = result.stdout.strip()
    if not line:
        return None
    parts = line.split(",")
    if len(parts) != 2:
        return None
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _scaled_dimensions(width: int, height: int) -> Optional[tuple[int, int]]:
    constraints: List[float] = []
    max_width = max(CONVERTER_MAX_VIDEO_WIDTH, 0)
    max_height = max(CONVERTER_MAX_VIDEO_HEIGHT, 0)
    max_long_edge = max(CONVERTER_MAX_VIDEO_LONG_EDGE, 0)
    max_short_edge = max(CONVERTER_MAX_VIDEO_SHORT_EDGE, 0)
    long_edge = max(width, height)
    short_edge = min(width, height)

    if max_width:
        constraints.append(width / max_width)
    if max_height:
        constraints.append(height / max_height)
    if max_long_edge:
        constraints.append(long_edge / max_long_edge)
    if max_short_edge:
        constraints.append(short_edge / max_short_edge)

    if not constraints:
        return None

    scale_factor = max(constraints)
    if scale_factor <= 1.0:
        return None
    new_width = max(2, int(width / scale_factor))
    new_height = max(2, int(height / scale_factor))
    # x264 requires even dimensions
    new_width -= new_width % 2
    new_height -= new_height % 2
    if new_width < 2 or new_height < 2:
        return None
    return new_width, new_height


class Converter:
    def __init__(self, server_port: str):
        self.server_port = server_port
        self.queue = ConversionQueue()
        self.processed = 0
        self.errors: List[Dict[str, str]] = []
        self.current: Optional[QueueItem] = None
        self._last_state_payload: Optional[Dict[str, object]] = None

    @staticmethod
    def _check_stop(process: Optional[subprocess.Popen] = None) -> None:
        if not STOP_EVENT.is_set():
            return
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise StopRequested

    def _state_payload(self, status: str, current: Optional[Dict[str, object]]) -> Dict[str, object]:
        current_percent = 0.0
        if current and isinstance(current.get("percent"), (int, float)):
            current_percent = max(0.0, min(float(current["percent"]), 100.0))
        pending = len(self.queue)
        total = self.processed + pending + (1 if current else 0)
        if total:
            completed = self.processed + (current_percent / 100.0)
            percent = round((completed / total) * 100.0, 2)
        else:
            percent = 0.0
        return {
            "status": status,
            "total": total,
            "processed": self.processed,
            "remaining": pending,
            "percent": percent,
            "current": current,
            "errors": [dict(error) for error in self.errors],
        }

    def _publish_state(self, payload: Dict[str, object], *, force: bool = False) -> None:
        if not force and self._last_state_payload == payload:
            return
        self._last_state_payload = deepcopy(payload)
        update_state(payload)

    def _set_state(
        self,
        status: str,
        current: Optional[Dict[str, object]],
        *,
        force: bool = False,
    ) -> None:
        self._publish_state(self._state_payload(status, current), force=force)

    def _remember_error(self, item: QueueItem, message: str) -> None:
        entry = {
            "file": item.relative_path,
            "message": message,
            "timestamp": _now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.errors.append(entry)
        self.errors[:] = self.errors[-10:]

    def _current_payload(
        self,
        item: QueueItem,
        *,
        percent: Optional[float] = None,
        eta: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "file": item.relative_path,
            "type": item.file_type,
            "index": self.processed + 1,
        }
        if percent is not None:
            payload["percent"] = round(max(0.0, min(percent, 100.0)), 2)
        if eta is not None:
            payload["eta_seconds"] = round(max(eta, 0.0), 1)
        if duration is not None:
            payload["duration_seconds"] = round(max(duration, 0.0), 1)
        return payload

    def _ensure_stop(self) -> None:
        if STOP_EVENT.is_set():
            raise StopRequested

    def _convert_image(self, item: QueueItem) -> None:
        path = item.absolute_path
        if not path.exists():
            return
        self._ensure_stop()
        with Image.open(path) as img:
            capture = get_capture_date(img) or _parse_datetime_from_name(path.name) or _now()
            width, height = img.size
            ratio = min(1.0, IMAGE_MAX_WIDTH / max(width, 1), IMAGE_MAX_HEIGHT / max(height, 1))
            if img.mode not in ("RGB", "L"):
                working = img.convert("RGB")
            else:
                working = img.copy()
            if ratio < 1.0:
                new_size = (int(width * ratio), int(height * ratio))
                working = working.resize(new_size, Image.LANCZOS)
            output_name = get_new_filename(path.name, capture, ext=".jpg")
            output_path = UPLOADED_DIR / output_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_stop()
            working.save(output_path, "JPEG", quality=IMAGE_QUALITY, optimize=True)
        self._ensure_stop()
        _remove_error_log(path)
        path.unlink(missing_ok=True)
        logger.info("Converted image %s -> %s", item.relative_path, output_name)

    def _convert_video(self, item: QueueItem) -> None:
        path = item.absolute_path
        if not path.exists():
            return
        capture = get_video_capture_date(path)
        output_name = get_new_filename(path.name, capture, ext=".mp4")
        output_path = UPLOADED_DIR / output_name
        duration = _probe_video_duration(path)
        if duration is not None and duration <= 0:
            duration = None
        dimensions = _probe_video_dimensions(path)
        scale_args: List[str] = []
        preset = CONVERTER_VIDEO_PRESET
        if dimensions is not None:
            width, height = dimensions
            scaled = _scaled_dimensions(width, height)
            if scaled is not None:
                target_width, target_height = scaled
                scale_args = ["-vf", f"scale={target_width}:{target_height}"]
                if CONVERTER_HIGH_RES_PRESET:
                    preset = CONVERTER_HIGH_RES_PRESET
                triggers = []
                if CONVERTER_MAX_VIDEO_WIDTH and width > CONVERTER_MAX_VIDEO_WIDTH:
                    triggers.append(f"width>{CONVERTER_MAX_VIDEO_WIDTH}")
                if CONVERTER_MAX_VIDEO_HEIGHT and height > CONVERTER_MAX_VIDEO_HEIGHT:
                    triggers.append(f"height>{CONVERTER_MAX_VIDEO_HEIGHT}")
                long_edge = max(width, height)
                short_edge = min(width, height)
                if CONVERTER_MAX_VIDEO_LONG_EDGE and long_edge > CONVERTER_MAX_VIDEO_LONG_EDGE:
                    triggers.append(f"long_edge>{CONVERTER_MAX_VIDEO_LONG_EDGE}")
                if CONVERTER_MAX_VIDEO_SHORT_EDGE and short_edge > CONVERTER_MAX_VIDEO_SHORT_EDGE:
                    triggers.append(f"short_edge>{CONVERTER_MAX_VIDEO_SHORT_EDGE}")
                trigger_text = ", ".join(triggers) if triggers else "constraints"
                logger.info(
                    "Scaling video %s from %sx%s to %sx%s (%s)",
                    item.relative_path,
                    width,
                    height,
                    target_width,
                    target_height,
                    trigger_text,
                )
        current = self._current_payload(item, percent=0.0, eta=duration, duration=duration)
        self._set_state("running", current, force=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "faststart",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-map_metadata",
            "-1",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            *scale_args,
            str(output_path),
        ]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        last_percent = 0.0
        try:
            for line in iter(process.stdout.readline, ""):
                self._check_stop(process)
                line = line.strip()
                if not line.startswith("out_time_ms=") or duration is None:
                    continue
                try:
                    current_seconds = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                if duration <= 0:
                    continue
                last_percent = max(0.0, min((current_seconds / duration) * 100.0, 100.0))
                eta = max(duration - current_seconds, 0.0)
                progress = self._current_payload(item, percent=last_percent, eta=eta, duration=duration)
                self._set_state("running", progress)
        except StopRequested:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            raise
        finally:
            if process.stdout:
                process.stdout.close()
        stderr = process.stderr.read() if process.stderr else ""
        if process.stderr:
            process.stderr.close()
        return_code = process.wait()
        try:
            self._check_stop()
        except StopRequested:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            raise
        if return_code != 0:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg exited with code {return_code}: {stderr}")
        final_payload = self._current_payload(item, percent=100.0, eta=0.0, duration=duration)
        self._set_state("running", final_payload, force=True)
        _remove_error_log(path)
        path.unlink(missing_ok=True)
        logger.info("Converted video %s -> %s", item.relative_path, output_name)

    def _process_item(self, item: QueueItem) -> None:
        if not item.absolute_path.exists():
            logger.warning("File %s missing, skipping", item.relative_path)
            return
        logger.info("Processing %s", item.relative_path)
        self.current = item
        current_payload = self._current_payload(item, percent=0.0)
        self._set_state("running", current_payload, force=True)
        try:
            if item.file_type == "video":
                self._convert_video(item)
            else:
                self._convert_image(item)
        finally:
            self.current = None

    def _notify_server(self) -> None:
        if not self.server_port:
            return
        try:
            url = f"http://localhost:{self.server_port}/admin/update_content"
            httpx.post(url, follow_redirects=True, timeout=5.0)
        except Exception as exc:
            logger.warning("Unable to notify server: %s", exc)

    def run(self) -> None:
        self.queue.refresh_from_disk()
        if not len(self.queue):
            self._set_state("idle", None, force=True)
            logger.info("No files to convert.")
            return
        STOP_EVENT.clear()
        self._set_state("running", None, force=True)
        try:
            while not STOP_EVENT.is_set():
                if not len(self.queue):
                    if not self.queue.refresh_from_disk():
                        break
                    continue
                item = self.queue.pop_next()
                if item is None:
                    continue
                try:
                    self._process_item(item)
                except StopRequested:
                    self.queue.push_front(item)
                    raise
                except Exception as exc:
                    logger.exception("Error processing %s", item.relative_path)
                    _write_error_log(item.absolute_path, str(exc))
                    self._remember_error(item, str(exc))
                    self._set_state("running", None, force=True)
                else:
                    self.processed += 1
                finally:
                    self._set_state("running", None)
                    self.queue.refresh_from_disk()
        except StopRequested:
            logger.info("Stop requested. Leaving remaining files in the queue.")
            if self.current is not None:
                self.queue.push_front(self.current)
            self._set_state("restarting", None, force=True)
        finally:
            self.queue.refresh_from_disk()
            self._set_state("idle", None, force=True)
            logger.info("Conversion finished. Processed %s files", self.processed)
            self._notify_server()


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    if CONVERT_LOCK_FILE.exists():
        logger.info("Converter already running.")
        return
    payload = {"pid": os.getpid(), "started": _now().isoformat()}
    try:
        with CONVERT_LOCK_FILE.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except FileExistsError:
        logger.info("Converter already running.")
        return
    except OSError as exc:
        logger.error("Unable to create lock file: %s", exc)
        return
    try:
        STOP_EVENT.clear()
        _install_signal_handlers()
        converter = Converter(port)
        converter.run()
    except Exception:
        logger.exception("Unexpected converter crash")
    finally:
        if CONVERT_LOCK_FILE.exists():
            CONVERT_LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
