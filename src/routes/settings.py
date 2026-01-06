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
    return templates.TemplateResponse("settings.jinja2", {
        "request": request,
        "settings": device_info.__dict__,
        "device_id": device_id,
        "form_action": "/go",
        "settings_checks": SETTINGS_LIST,
        "collections": device_queue_manager.media_dict.get_collections_tree(),
        "selected_collections": device_queue_manager.get_active_collections(device_info),
        "default_collections": device_queue_manager.default_collections,
        "collection_labels": device_queue_manager.get_collection_labels(),
        "uses_default_collections": device_queue_manager.uses_default_collections(device_info),
        "show_default_controls": True,
        "quick_start_action": "/go/collections/quick_start",
        "reset_action": "/go/collections/reset",
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
        collections: list[str] = Form([])
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
    device_queue_manager.set_device_collections(device_id, collections, keep_default_if_same=True)
    return RedirectResponse(url="/", status_code=303)


@router.post("/collections/reset")
async def reset_device_collections(request: Request, device_id: str = Cookie(None)):
    device_id = get_device_id(request, device_id)
    device_queue_manager.set_device_collections(device_id, None)
    return RedirectResponse(url="/go", status_code=303)


@router.post("/collections/quick_start")
async def quick_start_collection(
        request: Request,
        collection: str | None = Form(None),
        device_id: str = Cookie(None),
):
    device_id = get_device_id(request, device_id)
    device_queue_manager.set_device_collections(device_id, [collection or ""])
    # Redirect straight to slideshow
    return RedirectResponse(url="/", status_code=303)
