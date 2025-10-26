import logging
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Dict, Optional

import httpx


logger = logging.getLogger("media converter")


class SyncthingPauseManager:
    def __init__(
        self,
        base_url: str,
        folder_id: str,
        *,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.folder_id = folder_id
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[httpx.Response]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._headers(),
                timeout=5.0,
            )
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network failures
            logger.warning("Unable to %s Syncthing API (%s): %s", method.upper(), url, exc)
            return None
        return response

    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, object]]:
        response = self._request("GET", path, params=params)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _put(
        self,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self._request("PUT", path, params=params, json_body=json_body) is not None

    def get_folder_status(self) -> Optional[Dict[str, object]]:
        return self._get("rest/db/status", {"folder": self.folder_id})

    def _get_folder_config(self) -> Optional[Dict[str, Any]]:
        result = self._get(f"rest/config/folders/{self.folder_id}")
        if result is None:
            logger.warning("Unable to load Syncthing folder config for %s", self.folder_id)
        return result

    def _set_folder_paused(self, paused: bool) -> bool:
        config = self._get_folder_config()
        if not config:
            return False
        if bool(config.get("paused")) == paused:
            return True
        payload = deepcopy(config)
        payload["paused"] = paused
        if self._put(f"rest/config/folders/{self.folder_id}", json_body=payload):
            logger.info(
                "%s Syncthing folder %s",
                "Paused" if paused else "Resumed",
                self.folder_id,
            )
            return True
        return False

    def pause_folder(self) -> bool:
        return self._set_folder_paused(True)

    def resume_folder(self) -> bool:
        return self._set_folder_paused(False)

    @contextmanager
    def pause_during_conversion(self):
        should_resume = False
        was_paused = False
        status = self.get_folder_status()
        if status is not None:
            was_paused = bool(status.get("paused"))
        if not was_paused:
            should_resume = self.pause_folder()
        try:
            yield
        finally:
            if should_resume and not was_paused:
                self.resume_folder()
