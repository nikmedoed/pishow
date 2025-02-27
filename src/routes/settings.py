from fastapi import APIRouter, Request, Form, Cookie
from starlette.responses import RedirectResponse

from src.settings import device_queue_manager, templates
from src.utils.device import get_device_id

router = APIRouter()


@router.get("")
async def device_settings(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    device_info = device_queue_manager.get_device_info(device_id) or {}
    return templates.TemplateResponse("settings.jinja2", {
        "request": request,
        "settings": device_info.__dict__,
        "device_id": device_id
    })


@router.post("")
async def update_device_settings(
        request: Request,
        photo_time: int = Form(15),
        only_photo: bool = Form(False),
        modern_mode: bool = Form(False),
        sequential_mode: bool = Form(False),
        show_counters: bool = Form(False),
        show_names: bool = Form(False),
        video_background: str = Form("static"),
        name: str = Form(""),
        device_id: str = Cookie(None)
):
    device_id = get_device_id(request, device_id)
    photo_time = max(photo_time, 5)
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = getattr(request.client, "host", "unknown")
    device_queue_manager.update_device_info(
        device_id,
        photo_time=photo_time,
        only_photo=only_photo,
        modern_mode=modern_mode,
        sequential_mode=sequential_mode,
        show_counters=show_counters,
        video_background=video_background == "video",
        user_agent=user_agent,
        show_names=show_names,
        ip_address=client_ip,
        name=name

    )
    return RedirectResponse(url="/", status_code=303)
