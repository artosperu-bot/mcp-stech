from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class VtexImageApiError(RuntimeError):
    def __init__(self, *, operation: str, status: int | None, body: str, url: str):
        self.operation = operation
        self.status = status
        self.body = body
        self.url = url
        status_text = f"HTTP {status}" if status is not None else "network error"
        detail = body.strip() or "sin detalle"
        super().__init__(f"VTEX {status_text} en {operation}: {detail}")


class VtexImageClient:
    def __init__(
        self,
        *,
        account_name: str,
        environment: str,
        app_key: str,
        app_token: str,
        timeout_seconds: int = 30,
        opener: Callable[[Request, int], Any] | None = None,
    ):
        self.account_name = str(account_name or "").strip()
        self.environment = str(environment or "").strip().lstrip(".")
        self.app_key = str(app_key or "").strip()
        self.app_token = str(app_token or "").strip()
        self.timeout_seconds = int(timeout_seconds)
        self.opener = opener or (lambda request, timeout: urlopen(request, timeout=timeout))
        if not self.account_name or not self.environment:
            raise ValueError("VTEX account_name and environment are required")
        if not self.app_key or not self.app_token:
            raise ValueError("VTEX app_key and app_token are required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.base_url = f"https://{self.account_name}.{self.environment}"

    def _request(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {
            "Accept": "application/json",
            "X-VTEX-API-AppKey": self.app_key,
            "X-VTEX-API-AppToken": self.app_token,
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url=url, data=data, headers=headers, method=method.upper())
        try:
            with self.opener(request, self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(exc)
            raise VtexImageApiError(
                operation=operation,
                status=int(exc.code),
                body=body,
                url=url,
            ) from exc
        except URLError as exc:
            raise VtexImageApiError(
                operation=operation,
                status=None,
                body=str(exc.reason or exc),
                url=url,
            ) from exc

        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def resolve_sku_id(self, ref_id: str) -> int:
        ref = str(ref_id or "").strip()
        if not ref:
            raise ValueError("ref_id is required")
        result = self._request(
            operation="resolve_sku_id",
            method="GET",
            path=f"/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{quote(ref, safe='')}",
        )
        value: Any = result
        if isinstance(result, dict):
            value = result.get("Id") if result.get("Id") is not None else result.get("id")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise VtexImageApiError(
                operation="resolve_sku_id",
                status=200,
                body=f"respuesta sin SKU ID válido: {result!r}",
                url=f"{self.base_url}/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{quote(ref, safe='')}",
            ) from exc
        if parsed <= 0:
            raise VtexImageApiError(
                operation="resolve_sku_id",
                status=200,
                body=f"SKU ID inválido: {parsed}",
                url=f"{self.base_url}/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{quote(ref, safe='')}",
            )
        return parsed

    def list_sku_files(self, sku_id: int) -> list[dict[str, Any]]:
        parsed = int(sku_id)
        result = self._request(
            operation="list_sku_files",
            method="GET",
            path=f"/api/catalog/pvt/stockkeepingunit/{parsed}/file",
        )
        if result is None:
            return []
        if not isinstance(result, list):
            raise VtexImageApiError(
                operation="list_sku_files",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}/api/catalog/pvt/stockkeepingunit/{parsed}/file",
            )
        return [row for row in result if isinstance(row, dict)]

    def create_sku_file(self, sku_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        parsed = int(sku_id)
        result = self._request(
            operation="create_sku_file",
            method="POST",
            path=f"/api/catalog/pvt/stockkeepingunit/{parsed}/file",
            payload=payload,
        )
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="create_sku_file",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}/api/catalog/pvt/stockkeepingunit/{parsed}/file",
            )
        return result
