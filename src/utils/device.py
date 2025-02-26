import logging
import uuid

from starlette.requests import Request

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
