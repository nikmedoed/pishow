import os
import re
import shutil
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
import subprocess

import httpx
from PIL import Image

from src.settings import (
    CONVERT_LOCK_FILE,
    CONVERTER_RESTART_FILE,
    UPLOADED_DIR,
    UPLOADED_RAW_DIR,
)
from src.utils.conversion_state import reset_state, save_state
from src.utils.converter_queue import ConversionQueue, QueueItem
from src.utils.files import get_capture_date, get_video_capture_date

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    logging.info("pillow-heif registered successfully")
except Exception as exc:  # pragma: no cover - optional dependency
    logging.warning("pillow-heif could not be registered: %s", exc)

logger = logging.getLogger("media converter")
logging.basicConfig(level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO)

MAX_ATTEMPTS_PER_FILE = 3


class RestartRequested(Exception):
    """Raised when a manual restart is requested."""


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_datetime_from_name(name: str) -> Optional[datetime]:
    base = Path(name).stem
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_ ]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})", base)
    if match:
        y, mo, d, h, mi, s = match.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
        except ValueError:
            return None
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", base)
    if match:
        y, mo, d = match.groups()
        try:
            return datetime(int(y), int(mo), int(d))
        except ValueError:
            return None
    return None


def _clean_base_name(original_name: str) -> str:
    base = Path(original_name).stem
    base = re.sub(r"\(\d+\)$", "", base)
    base = re.sub(r"^(\d{4}[-_]?\d{2}[-_]?\d{2}([-_ ]?\d{2}[-_]?\d{2}[-_]?\d{2})?)", "", base)
    base = base.replace(" ", "-")
    base = re.sub(r"-+", "-", base)
    base = re.sub(r"[^A-Za-z0-9-_]", "-", base)
    base = re.sub(r"_+", "_", base)
    base = re.sub(r"-+", "-", base)
    base = re.sub(r"-_", "-", base)
    base = re.sub(r"_-", "-", base)
    base = base.strip("-_")
    return base


def get_new_filename(original_name: str, capture_date: Optional[datetime] = None, ext: Optional[str] = None) -> str:
    if capture_date is None:
        capture_date = _parse_datetime_from_name(original_name) or _now()
    if capture_date.tzinfo:
        capture_date = capture_date.astimezone().replace(tzinfo=None)
    if ext is None:
        ext = Path(original_name).suffix
    if not ext.startswith('.'):
        ext = f".{ext}"
    ext = ext.lower()

    base = _clean_base_name(original_name)
    date_part = capture_date.strftime("%Y%m%d")
    time_part = capture_date.strftime("%H%M%S")
    if base:
        return f"{date_part}-{time_part}-{base}{ext}"
    return f"{date_part}-{time_part}{ext}"


def _write_error_log(file_path: Path, error_text: str) -> None:
    error_file = file_path.with_suffix('.txt')
    with error_file.open("w", encoding="utf-8") as handle:
        handle.write(error_text)


def _remove_error_log(file_path: Path) -> None:
    error_file = file_path.with_suffix('.txt')
    if error_file.exists():
        error_file.unlink()


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
        return float(result.stdout.strip())
    except Exception as exc:  # pragma: no cover - depends on ffprobe availability
        logger.warning("Unable to read duration for %s: %s", input_path.name, exc)
        return None


@dataclass
class ConversionContext:
    queue: ConversionQueue
    processed: int = 0
    errors: List[Dict[str, str]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def total_items(self, include_current: bool = False) -> int:
        total = self.processed + len(self.queue.items)
        if include_current:
            total += 1
        return total

    def record_error(self, relative_path: str, message: str) -> None:
        timestamp = _now().strftime("%Y-%m-%d %H:%M:%S")
        self.errors.append({
            "file": relative_path,
            "message": message,
            "timestamp": timestamp,
        })
        self.errors = self.errors[-10:]

    def snapshot(self, status: str, current: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        total = self.total_items(include_current=bool(current))
        remaining = max(total - self.processed, 0)
        percent = round((self.processed / total) * 100, 2) if total else 0.0
        return {
            "status": status,
            "total": total,
            "processed": self.processed,
            "remaining": remaining,
            "percent": percent,
            "current": current,
            "errors": self.errors,
        }


class Converter:
    def __init__(self, server_port: str):
        self.server_port = server_port
        self.queue = ConversionQueue()
        self.context = ConversionContext(self.queue)
        self.current_item: Optional[QueueItem] = None

    def check_for_restart(self, process: Optional[subprocess.Popen] = None) -> None:
        if not CONVERTER_RESTART_FILE.exists():
            return
        logger.info("Restart requested by admin. Restarting conversion loop.")
        CONVERTER_RESTART_FILE.unlink(missing_ok=True)
        if process and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise RestartRequested

    def update_state(self, status: str, current: Optional[Dict[str, object]] = None) -> None:
        payload = self.context.snapshot(status=status, current=current)
        save_state(payload)

    def build_current_payload(
        self,
        item: QueueItem,
        percent: Optional[float] = 0.0,
        eta_seconds: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "file": item.relative_path,
            "type": item.file_type,
            "percent": None if percent is None else round(percent, 2),
            "eta_seconds": None if eta_seconds is None else round(eta_seconds, 1),
            "index": self.context.processed + 1,
            "attempt": item.attempts + 1,
        }
        if duration is not None:
            payload["duration_seconds"] = round(duration, 1)
        return payload

    def convert_image(self, item: QueueItem) -> None:
        file_path = item.absolute_path
        original_size = file_path.stat().st_size
        capture_date: Optional[datetime] = None
        output_path: Optional[Path] = None
        keep_original_only = False
        with Image.open(file_path) as img:
            capture_date = (
                get_capture_date(img)
                or _parse_datetime_from_name(file_path.name)
                or _now()
            )
            width, height = img.size
            max_width, max_height = 3840, 2160
            ratio = min(1, max_width / width, max_height / height)
            original_suffix = file_path.suffix.lower()
            keep_original_only = ratio == 1 and original_suffix in {".jpg", ".jpeg"}
            if keep_original_only:
                output_path = None
            else:
                working_image = img.convert("RGB")
                if ratio < 1:
                    new_size = (int(width * ratio), int(height * ratio))
                    logger.info(
                        "Resizing image %s from %s to %s",
                        file_path.name,
                        img.size,
                        new_size,
                    )
                    working_image = working_image.resize(new_size, Image.LANCZOS)
                data = list(working_image.getdata())
                img_no_meta = Image.new(working_image.mode, working_image.size)
                img_no_meta.putdata(data)
                new_filename = get_new_filename(file_path.name, capture_date, ext=".jpg")
                output_path = UPLOADED_DIR / new_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.unlink(missing_ok=True)
                img_no_meta.save(output_path, "JPEG", quality=60, optimize=True)
        if keep_original_only:
            assert capture_date is not None
            original_ext = file_path.suffix if file_path.suffix else ".jpg"
            new_name = get_new_filename(file_path.name, capture_date, ext=original_ext)
            final_path = UPLOADED_DIR / new_name
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.unlink(missing_ok=True)
            shutil.move(str(file_path), final_path)
            logger.info(
                "Moved original image without recompression: %s -> %s",
                file_path.name,
                final_path.name,
            )
        elif output_path is not None and output_path.exists():
            converted_size = output_path.stat().st_size
            if converted_size >= original_size:
                original_ext = file_path.suffix if file_path.suffix else ".jpg"
                fallback_name = get_new_filename(
                    file_path.name,
                    capture_date or _now(),
                    ext=original_ext,
                )
                fallback_path = UPLOADED_DIR / fallback_name
                fallback_path.parent.mkdir(parents=True, exist_ok=True)
                fallback_path.unlink(missing_ok=True)
                shutil.move(str(file_path), fallback_path)
                output_path.unlink(missing_ok=True)
                logger.info(
                    "Converted image %s larger than original (%s >= %s). Kept original file.",
                    file_path.name,
                    converted_size,
                    original_size,
                )
            else:
                UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
        _remove_error_log(file_path)

    def convert_video(self, item: QueueItem) -> None:
        file_path = item.absolute_path
        capture_date = get_video_capture_date(file_path)
        new_filename = get_new_filename(file_path.name, capture_date, ext=".mp4")
        output_path = UPLOADED_DIR / new_filename
        duration = item.duration or _probe_video_duration(file_path)
        item.duration = duration
        output_path.unlink(missing_ok=True)
        if duration:
            initial_eta = duration
        else:
            initial_eta = None
        initial_payload = self.build_current_payload(
            item,
            percent=0.0,
            eta_seconds=initial_eta,
            duration=duration,
        )
        self.update_state(status="running", current=initial_payload)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(file_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "30",
            "-profile:v", "high", "-level:v", "4.0",
            "-pix_fmt", "yuv420p", "-movflags", "faststart",
            "-c:a", "aac", "-b:a", "128k", "-map_metadata", "-1",
            "-progress", "pipe:1", "-nostats", "-loglevel", "error",
            str(output_path)
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
        start_time = time.time()
        try:
            for line in iter(process.stdout.readline, ""):
                self.check_for_restart(process)
                line = line.strip()
                if not line:
                    continue
                if line.startswith("out_time_ms=") and duration:
                    raw_value = line.split("=", 1)[1]
                    try:
                        microseconds = int(raw_value)
                    except ValueError:
                        logger.debug(
                            "Skipping out_time_ms update with non-numeric value %s for %s",
                            raw_value,
                            item.relative_path,
                        )
                        continue
                    seconds_done = microseconds / 1_000_000
                    percent = min(100.0, (seconds_done / duration) * 100)
                    last_percent = percent
                    eta_seconds = max(duration - seconds_done, 0.0)
                    payload = self.build_current_payload(
                        item,
                        percent=percent,
                        eta_seconds=eta_seconds,
                        duration=duration,
                    )
                    self.update_state(status="running", current=payload)
            self.check_for_restart(process)
        finally:
            process_stdout = process.stdout
            if process_stdout:
                process_stdout.close()
        stderr_output = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg exited with code {return_code}: {stderr_output}")
        if last_percent < 100.0:
            elapsed = time.time() - start_time
            eta = max((duration or 0) - elapsed, 0.0)
            payload = self.build_current_payload(
                item,
                percent=100.0,
                eta_seconds=eta,
                duration=duration,
            )
            self.update_state(status="running", current=payload)
        _remove_error_log(file_path)

    def process_item(self, item: QueueItem) -> None:
        file_path = item.absolute_path
        if not file_path.exists():
            logger.warning("File %s no longer exists. Skipping.", item.relative_path)
            return
        logger.info(
            "Starting conversion of %s (type: %s, attempt %d)",
            item.relative_path,
            item.file_type,
            item.attempts + 1,
        )
        current_info = self.build_current_payload(item)
        self.update_state(status="running", current=current_info)
        if item.file_type == "video":
            self.convert_video(item)
        else:
            self.convert_image(item)
            finished_payload = self.build_current_payload(item, percent=100.0, eta_seconds=0.0)
            self.update_state(status="running", current=finished_payload)
        file_path.unlink(missing_ok=True)
        logger.info("Deleted original file: %s", file_path)

    def run(self) -> None:
        self.queue.refresh_from_disk()
        if len(self.queue) == 0:
            reset_state()
            logger.info("No files to convert.")
            return
        self.update_state(status="running", current=None)
        try:
            while True:
                self.queue.refresh_from_disk()
                item = self.queue.pop_next()
                if item is None:
                    break
                self.current_item = item
                try:
                    self.check_for_restart()
                    self.process_item(item)
                    self.context.processed += 1
                    self.update_state(status="running", current=None)
                except RestartRequested:
                    logger.info("Restarting converter: moving %s to queue tail", item.relative_path)
                    self.queue.push_back(item)
                    self.update_state(status="restarting", current=None)
                    continue
                except Exception as exc:
                    logger.exception("Error processing %s: %s", item.relative_path, exc)
                    error_text = traceback.format_exc()
                    _write_error_log(item.absolute_path, error_text)
                    self.context.record_error(item.relative_path, str(exc))
                    item.attempts += 1
                    if item.attempts < MAX_ATTEMPTS_PER_FILE:
                        self.queue.push_back(item)
                    else:
                        logger.error("Max attempts reached for %s. Leaving file in raw directory for manual review.", item.relative_path)
                    self.update_state(status="running", current=None)
                finally:
                    self.current_item = None
                if len(self.queue) == 0:
                    self.queue.refresh_from_disk()
                if len(self.queue) == 0:
                    break
        finally:
            summary = self.context.snapshot(status="idle", current=None)
            save_state(summary)
            logger.info("Conversion finished. Processed: %s", self.context.processed)
            self.notify_server()

    def notify_server(self) -> None:
        if not self.server_port:
            return
        try:
            url = f"http://localhost:{self.server_port}/admin/update_content"
            response = httpx.post(url, follow_redirects=True, timeout=5.0)
            if response.status_code in [200, 303]:
                logger.info("Server update successful: %s", response.text)
            else:
                logger.error("Server update failed: %s", response.text)
        except Exception as exc:
            logger.error("Error calling /admin/update_content: %s", exc)


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    if CONVERT_LOCK_FILE.exists():
        logger.info("Converter already running.")
        return
    CONVERT_LOCK_FILE.touch(exist_ok=False)
    try:
        converter = Converter(port)
        converter.run()
    except Exception:
        logger.exception("Unexpected converter crash")
    finally:
        if CONVERTER_RESTART_FILE.exists():
            CONVERTER_RESTART_FILE.unlink(missing_ok=True)
        if CONVERT_LOCK_FILE.exists():
            CONVERT_LOCK_FILE.unlink()


if __name__ == "__main__":
    main()
