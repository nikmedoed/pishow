import logging
import os
import shutil
from urllib.parse import unquote, quote

from src.settings import MEDIA_DIR, VIDEO_BACKGROUND_SUFFIX, media_handler, MEDIA_PATH
from src.utils.gradient import get_random_svg_gradient


def get_static_background_path(relative_path: str) -> str:
    decoded_path = unquote(relative_path)
    input_path = os.path.join(MEDIA_DIR, decoded_path)
    base, _ = os.path.splitext(decoded_path)
    background_filename = f"{base}{VIDEO_BACKGROUND_SUFFIX}"
    background_file_path = os.path.join(MEDIA_DIR, background_filename)

    if not os.path.exists(background_file_path):
        if shutil.which("ffmpeg"):
            cmd = f'ffmpeg -y -i "{input_path}" -ss 00:00:01.000 -vframes 1 "{background_file_path}"'
            os.system(cmd)
            logging.info(f"Generated background frame: {background_file_path}")
        else:
            logging.warning("ffmpeg not available. Using fallback gradient background.")
            media = media_handler.get_random_photo_background()
            if media:
                return f"{MEDIA_PATH}/{media}"
            return get_random_svg_gradient()

    return f"{MEDIA_PATH}/{quote(background_filename)}"
