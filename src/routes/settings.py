from fastapi import APIRouter, Request, Form, Cookie
from starlette.responses import RedirectResponse

from src.device_manager import SETTINGS_LIST
from src.settings import device_queue_manager, templates
from src.utils.device import get_device_id

router = APIRouter(prefix="/go", tags=["settings"])


@router.get("")
async def device_settings(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    device_info = device_queue_manager.get_device_info(device_id) or {}
    collections, collection_labels = device_queue_manager.list_collections()
    selected_collections = device_info.collections or device_queue_manager.default_collections
    return templates.TemplateResponse("settings.jinja2", {
        "request": request,
        "settings": device_info.__dict__,
        "device_id": device_id,
        "form_action": "/go",
        "settings_checks": SETTINGS_LIST,
        "collections": collections,
        "collection_labels": collection_labels,
        "selected_collections": selected_collections,
        "default_collections": device_queue_manager.default_collections,
        "uses_default_collections": device_info.collections is None,
        "show_default_controls": device_info.collections is not None,
        "reset_action": "/go/reset",
        "quick_start_action": "/go/quick_start",
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
        device_id: str = Cookie(None),
        collections: list[str] = Form(None),
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
        name=name,
        collections=collections,

    )
    return RedirectResponse(url="/", status_code=303)


@router.post("/reset")
async def reset_device_collections(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    device_queue_manager.update_device_info(device_id, collections=None)
    return RedirectResponse(url="/go", status_code=303)


@router.post("/quick_start")
async def quick_start_collection(request: Request, collection: str = Form(...), device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    device_queue_manager.update_device_info(device_id, collections=[collection], force_reset_queue=True)
    return RedirectResponse(url="/", status_code=303)
