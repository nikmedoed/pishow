import logging

from fastapi import APIRouter, Request, Cookie
from fastapi.responses import HTMLResponse

from src.settings import device_queue_manager, templates, MEDIA_PATH
from src.utils import get_device_id, get_static_background_path

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def get_media_page(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    try:
        media = device_queue_manager.get_next(device_id)
    except Exception as e:
        logging.error(f"Error retrieving media for device {device_id}: {e}")
        return HTMLResponse("Error: no media available", status_code=500)

    if media is None:
        logging.warning(f"No media available for device {device_id}")
        return HTMLResponse("No media available", status_code=404)

    refresh_time = media.duration + 3 if media.is_video else 15

    dynamic_background = False

    content = f"{MEDIA_PATH}/{media.relative_path}"
    background_file_url = content
    if media.is_video and not dynamic_background:
        background_file_url = get_static_background_path(media.relative_path)

    response = templates.TemplateResponse(
        "index.jinja2",
        {
            "request": request,
            "file_url": content,
            "refresh_time": refresh_time,
            "is_video": media.is_video,
            "dynamic_background": dynamic_background,
            "background_file_url": background_file_url,
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
