"""Тонкий клиент к Keitaro Admin API (/admin_api/v1)."""

from typing import Any

import logging

import httpx

log = logging.getLogger("keitaro")


class KeitaroError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(f"Keitaro API {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_key_header: str = "Api-Key",
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/admin_api/v1",
            headers={api_key_header: api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, json: Any = None, params: dict | None = None) -> Any:
        try:
            resp = self._http.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise KeitaroError(502, f"Keitaro недоступен: {exc}") from exc

        if resp.status_code >= 400:
            # Полный запрос и ответ в лог, чтобы видеть, какое поле Keitaro отверг.
            log.warning(
                "Keitaro %s %s -> %s\n  params: %s\n  request body: %s\n  response: %s",
                method, path, resp.status_code, params, json, resp.text,
            )
            raise KeitaroError(resp.status_code, resp.text[:500])
        if not resp.content:
            return None
        return resp.json()

    # --- Кампании ---------------------------------------------------------

    def list_campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns") or []

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, data: dict) -> dict:
        return self._request("POST", "/campaigns", json=data)

    def update_campaign(self, campaign_id: int, data: dict) -> dict:
        # Keitaro обновляет только переданные поля.
        return self._request("PUT", f"/campaigns/{campaign_id}", json=data)

    # --- Потоки (streams) -------------------------------------------------

    def create_stream(self, data: dict) -> dict:
        return self._request("POST", "/streams", json=data)

    def list_streams(self, campaign_id: int) -> list[dict]:
        # Потоки кампании: GET /campaigns/{id}/streams (GET /streams?campaign_id=... в Keitaro не существует)
        return self._request("GET", f"/campaigns/{campaign_id}/streams") or []

    def update_stream(self, stream_id: int, data: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=data)

    # --- Справочники для выпадающих списков -------------------------------

    def list_groups(self, group_type: str = "campaigns") -> list[dict]:
        # Keitaro требует параметр type; для групп кампаний это "campaigns".
        return self._request("GET", "/groups", params={"type": group_type}) or []

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources") or []

    def list_domains(self) -> list[dict]:
        return self._request("GET", "/domains") or []

    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers") or []
