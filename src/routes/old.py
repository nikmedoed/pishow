import logging

from fastapi import APIRouter, Request, Cookie
from fastapi.responses import HTMLResponse

from src.settings import device_queue_manager, templates, MEDIA_PATH
from src.utils.device import get_device_id, is_outdated_ios
from src.utils.gradient import get_random_svg_gradient
from src.utils.video_background import get_static_background_path

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def get_media_page(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)

    dynamic_background = False
    counters = True
    only_photo = False
    show_time = 15

    try:
        if counters:
            media, position, total = device_queue_manager.get_next(device_id, counters=True, only_photo=only_photo)
            counters_text = f"{position} / {total}"
        else:
            media = device_queue_manager.get_next(device_id, only_photo=only_photo)
            counters_text = None
    except Exception as e:
        logging.error(f"Error retrieving media for device {device_id}: {e}")
        media = None
        counters_text = "No media for your setting"

    if media is None:
        content = None
        refresh_time = show_time * 2
        is_video = False
        background_file_url = get_random_svg_gradient()
        include_inline_video = False
    else:
        refresh_time = media.duration + 3 if media.is_video else show_time
        content = f"{MEDIA_PATH}/{media.relative_path}"
        background_file_url = content
        if media.is_video and not dynamic_background:
            background_file_url = get_static_background_path(media.relative_path)
        is_video = media.is_video
        include_inline_video = is_outdated_ios(request.headers.get("user-agent", ""))

    response = templates.TemplateResponse(
        "index.jinja2",
        {
            "request": request,
            "file_url": content,
            "refresh_time": refresh_time,
            "is_video": is_video,
            "dynamic_background": dynamic_background,
            "background_file_url": background_file_url,
            "include_inline_video": include_inline_video,
            "counters_text": counters_text,
        },
    )
    response.set_cookie(key="device_id", value=device_id, max_age=31536000, path="/", httponly=True)
    return response


@router.post("/pause")
async def pause():
    return {"redirect_url": "/?refresh=false"}


@router.post("/next")
async def next_file():
    return {"redirect_url": "/"}
