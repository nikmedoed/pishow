import logging
import uuid

from fastapi import APIRouter, Request, Cookie
from fastapi.responses import HTMLResponse

from src.settings import device_queue_manager, templates

router = APIRouter()


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

    response = templates.TemplateResponse(
        "index.jinja2",
        {
            "request": request,
            "file_url": f"/media/{media.relative_path}",
            "refresh_time": refresh_time,
            "is_video": media.is_video,
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
