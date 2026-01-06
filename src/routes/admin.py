import shutil
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse, HTMLResponse

from src.device_manager import SETTINGS_LIST
from src.settings import device_queue_manager, templates, UPLOADED_RAW_DIR, UPLOADED_DIR
from src.utils.converter_control import (
    get_conversion_status,
    is_conversion_running,
    request_restart,
    start_conversion,
)
from src.utils.files import count_files_recursive

router = APIRouter(prefix="/admin", tags=["admin"])

SETTINGS_CHECKS = {**SETTINGS_LIST, "video_background": "Video Background"}


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    devices = device_queue_manager.devices_info
    md = device_queue_manager.media_dict
    media_total = len(md)
    media_photos = len(md.photo_keys) if md.photo_keys else 0
    media_videos = len(md.video_keys) if md.video_keys else 0

    update_msg = request.session.pop("update_msg", None)
    conversion_state = get_conversion_status()
    collections = md.get_collections_tree()
    response = templates.TemplateResponse("admin.jinja2", {
        "request": request,
        "devices": devices,
        "media_total": media_total,
        "media_photos": media_photos,
        "media_videos": media_videos,
        "update_msg": update_msg,
        "device_queue_manager": device_queue_manager,
        "settings_checks": SETTINGS_CHECKS,
        "collections": collections,
        "default_collections": device_queue_manager.default_collections,
        "collection_labels": device_queue_manager.get_collection_labels(),
        "upload_raw": count_files_recursive(UPLOADED_RAW_DIR),
        "uploaded": count_files_recursive(UPLOADED_DIR),
        "conversion_state": conversion_state,
        "conversion_active": is_conversion_running() or conversion_state.get("status") in {"running", "scheduled", "restarting"},
    })
    return response


@router.post("/update_content")
async def update_content(request: Request):
    new_keys = device_queue_manager.media_dict.sync_files()
    if new_keys:
        device_queue_manager.update_query(new_keys)
        update_status = f"New media added: {len(new_keys)}"
    else:
        update_status = "No new media found."
    request.session["update_msg"] = update_status
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/defaults/collections")
async def update_default_collections(request: Request, collections: list[str] = Form([])):
    device_queue_manager.set_default_collections(collections)
    request.session["update_msg"] = "Default collections updated."
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/clear_queue")
async def clear_queue(request: Request, device_id: str = Form(...)):
    device_queue_manager.delete_queue(device_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/delete_device")
async def delete_device(request: Request, device_id: str = Form(...)):
    device_queue_manager.delete_device(device_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/{device_id}", response_class=HTMLResponse)
async def admin_device_settings(request: Request, device_id: str):
    device_info = device_queue_manager.get_device_info(device_id)
    return templates.TemplateResponse("settings.jinja2", {
        "request": request,
        "settings": device_info.__dict__,
        "device_id": device_id,
        "form_action": f"/admin/{device_id}",
        "settings_checks": SETTINGS_LIST,
        "collections": device_queue_manager.media_dict.get_collections_tree(),
        "selected_collections": device_queue_manager.get_active_collections(device_info),
        "default_collections": device_queue_manager.default_collections,
        "collection_labels": device_queue_manager.get_collection_labels(),
        "uses_default_collections": device_queue_manager.uses_default_collections(device_info),
        "show_default_controls": True,
        "quick_start_action": f"/admin/{device_id}/collections/quick_start",
        "reset_action": f"/admin/{device_id}/collections/reset",
    })


@router.post("/upload")
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    try:
        for file in files:
            destination = UPLOADED_RAW_DIR / file.filename
            with open(destination, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        port = str(request.url.port or "8000")
        conversion_message = start_conversion(port)
        message = f"Files uploaded. {conversion_message}"
    except Exception as e:
        message = f"Uploading error: {e}"
    request.session["update_msg"] = message
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/convert")
async def convert_existing_files(request: Request):
    port = str(request.url.port or "8000")
    request.session["update_msg"] = start_conversion(port)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/conversion/restart")
async def restart_conversion(request: Request):
    if request_restart():
        message = "Conversion restart requested."
    else:
        message = "Converter is not active."
    request.session["update_msg"] = message
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/conversion/status")
async def conversion_status() -> JSONResponse:
    return JSONResponse(get_conversion_status())


@router.post("/{device_id}/collections/reset")
async def reset_device_collections(request: Request, device_id: str):
    device_queue_manager.set_device_collections(device_id, None)
    request.session["update_msg"] = "Device collections reset to default."
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/{device_id}/collections/quick_start")
async def quick_start_collection(request: Request, device_id: str, collection: str | None = Form(None)):
    # Replace selection with a single collection and rebuild queue.
    collection = collection or ""
    device_queue_manager.set_device_collections(device_id, [collection])
    label = device_queue_manager.get_collection_labels().get(collection, collection or "/")
    request.session["update_msg"] = f"Started collection {label} for device."
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/{device_id}")
async def update_admin_device_settings(
        request: Request,
        device_id: str,
        photo_time: int = Form(15),
        only_photo: bool = Form(False),
        modern_mode: bool = Form(False),
        sequential_mode: bool = Form(False),
        show_counters: bool = Form(False),
        show_names: bool = Form(False),
        video_background: str = Form("static"),
        name: str = Form(""),
        collections: list[str] = Form([])
):
    photo_time = max(photo_time, 5)
    device_queue_manager.update_device_info(
        device_id,
        photo_time=photo_time,
        only_photo=only_photo,
        modern_mode=modern_mode,
        sequential_mode=sequential_mode,
        show_counters=show_counters,
        video_background=video_background == "video",
        show_names=show_names,
        name=name
    )
    device_queue_manager.set_device_collections(device_id, collections, keep_default_if_same=True)
    return RedirectResponse(url="/admin", status_code=303)
