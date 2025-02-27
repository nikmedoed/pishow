import shutil
import subprocess
import sys

from fastapi import APIRouter, Request, Form, UploadFile, File
from starlette.responses import RedirectResponse, HTMLResponse

from src.device_manager import SETTINGS_LIST
from src.settings import device_queue_manager, templates, UPLOADED_RAW_DIR

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
    response = templates.TemplateResponse("admin.jinja2", {
        "request": request,
        "devices": devices,
        "media_total": media_total,
        "media_photos": media_photos,
        "media_videos": media_videos,
        "update_msg": update_msg,
        "device_queue_manager": device_queue_manager,
        "settings_checks": SETTINGS_CHECKS
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
        "settings_checks": SETTINGS_LIST
    })


@router.post("/upload")
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    try:
        for file in files:
            destination = UPLOADED_RAW_DIR / file.filename
            with open(destination, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        port = str(request.url.port or "8000")
        subprocess.Popen(
            [sys.executable, "src/utils/converter.py", port],
            start_new_session=True
        )
        message = "Files uploaded. Converting started."
    except Exception as e:
        message = f"Uploading error {e}"
    request.session["update_msg"] = message
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
        name: str = Form("")
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
    return RedirectResponse(url="/admin", status_code=303)
