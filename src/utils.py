import base64
import colorsys
import logging
import os
import random
import shutil
import uuid
from urllib.parse import quote, unquote

from starlette.requests import Request

from src.settings import MEDIA_DIR, VIDEO_BACKGROUND_SUFFIX, MEDIA_PATH, media_handler
from src.settings import device_queue_manager


def get_device_id(request: Request, cookie_device_id: str) -> str:
    if cookie_device_id:
        return cookie_device_id
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = getattr(request.client, "host", "unknown")
    new_device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_agent + client_ip))
    device_info = {
        "raw_user_agent": user_agent,
        "client_ip": client_ip,
    }
    device_queue_manager.update_device_info(new_device_id, device_info)
    logging.debug(f"New device registered: {new_device_id}, UA: {user_agent}, IP: {client_ip}")
    return new_device_id


def get_random_pastel_color():
    h = random.random()
    s = random.uniform(0.4, 0.6)
    l = random.uniform(0.75, 0.85)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b * 255))


def get_random_svg_gradient():
    gradient_type = random.choice(["linear", "radial"])

    if gradient_type == "linear":
        x1 = f"{random.randint(0, 100)}%"
        y1 = f"{random.randint(0, 100)}%"
        x2 = f"{random.randint(0, 100)}%"
        y2 = f"{random.randint(0, 100)}%"
        gradient_params = f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
    else:
        cx = f"{random.randint(20, 80)}%"
        cy = f"{random.randint(20, 80)}%"
        r = f"{random.randint(30, 60)}%"
        gradient_params = f'cx="{cx}" cy="{cy}" r="{r}"'

    num_stops = random.randint(2, 3)

    if num_stops == 2:
        offsets = [0, 100]
    else:
        offsets = [0, random.randint(20, 80), 100]
    offsets.sort()

    stops = []
    for offset in offsets:
        color = get_random_pastel_color()
        stops.append(f'<stop offset="{offset}%" style="stop-color:{color};stop-opacity:1" />')
    stops_svg = "\n          ".join(stops)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">
      <defs>
        <{gradient_type}Gradient id="grad" {gradient_params}>
          {stops_svg}
        </{gradient_type}Gradient>
      </defs>
      <rect width="400" height="400" fill="url(#grad)" />
    </svg>'''

    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode('utf-8')).decode("utf-8")


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
