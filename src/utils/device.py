import logging
import re
import uuid

from starlette.requests import Request

from src.settings import device_queue_manager


def get_device_id(request: Request, cookie_device_id: str) -> str:
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = getattr(request.client, "host", "unknown")

    if cookie_device_id:
        device_queue_manager.update_device_info(
            cookie_device_id,
            user_agent=user_agent,
            ip_address=client_ip,
        )
        logging.debug(
            f"Existing device detected: {cookie_device_id}, UA: {user_agent}, IP: {client_ip}"
        )
        return cookie_device_id

    new_device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_agent + client_ip))
    device_queue_manager.update_device_info(
        new_device_id,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    logging.debug(
        f"New device registered: {new_device_id}, UA: {user_agent}, IP: {client_ip}"
    )
    return new_device_id


def is_outdated_ios(user_agent: str) -> bool:
    if "iPad" in user_agent or "iPhone" in user_agent:
        match = re.search(r'OS (\d+)_', user_agent)
        if match:
            ios_version = int(match.group(1))
            return ios_version < 10
    return False
