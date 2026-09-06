from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "exception_type": type(self).__name__,
            "operation": self.operation,
            "status_http": self.status,
            "url": self.url,
            "body": self.body,
            "message": str(self),
        }


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

    def _request_url(
        self,
        *,
        operation: str,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        include_api_credentials: bool = True,
    ) -> Any:
        if payload is not None and data is not None:
            raise ValueError("payload and data are mutually exclusive")

        request_headers = {"Accept": "application/json"}
        if include_api_credentials:
            request_headers.update(
                {
                    "X-VTEX-API-AppKey": self.app_key,
                    "X-VTEX-API-AppToken": self.app_token,
                }
            )
        if headers:
            request_headers.update(headers)

        request_data = data
        if payload is not None:
            request_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        request = Request(
            url=url,
            data=request_data,
            headers=request_headers,
            method=method.upper(),
        )
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

    def _request(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        return self._request_url(
            operation=operation,
            method=method,
            url=f"{self.base_url}{path}",
            payload=payload,
        )

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
                body=f"respuesta sin SKU ID vÃ¡lido: {result!r}",
                url=f"{self.base_url}/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{quote(ref, safe='')}",
            ) from exc
        if parsed <= 0:
            raise VtexImageApiError(
                operation="resolve_sku_id",
                status=200,
                body=f"SKU ID invÃ¡lido: {parsed}",
                url=f"{self.base_url}/api/catalog_system/pvt/sku/stockkeepingunitidbyrefid/{quote(ref, safe='')}",
            )
        return parsed

    def get_sku_context(self, sku_id: int) -> dict[str, Any]:
        parsed = int(sku_id)
        result = self._request(
            operation="get_sku_context",
            method="GET",
            path=f"/api/catalog_system/pvt/sku/stockkeepingunitbyid/{parsed}",
        )
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="get_sku_context",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}/api/catalog_system/pvt/sku/stockkeepingunitbyid/{parsed}",
            )
        return result

    # Classic Catalog endpoints are intentionally kept for compatibility and
    # diagnostics. CatalogV2 image sync does not call them.
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

    def get_seller_product_by_external_id(self, external_id: str) -> dict[str, Any]:
        token = str(external_id or "").strip()
        if not token:
            raise ValueError("external_id is required")
        path = f"/api/catalog-seller-portal/products/external-id={quote(token, safe='')}"
        result = self._request(
            operation="get_seller_product_by_external_id",
            method="GET",
            path=path,
        )
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="get_seller_product_by_external_id",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}{path}",
            )
        return result

    def get_seller_product(self, product_id: str | int) -> dict[str, Any]:
        token = str(product_id or "").strip()
        if not token:
            raise ValueError("product_id is required")
        path = f"/api/catalog-seller-portal/products/{quote(token, safe='')}"
        result = self._request(
            operation="get_seller_product",
            method="GET",
            path=path,
        )
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="get_seller_product",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}{path}",
            )
        return result

    def update_seller_product(self, product_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
        token = str(product_id or "").strip()
        if not token:
            raise ValueError("product_id is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        path = f"/api/catalog-seller-portal/products/{quote(token, safe='')}"
        result = self._request(
            operation="update_seller_product",
            method="PUT",
            path=path,
            payload=payload,
        )
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="update_seller_product",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=f"{self.base_url}{path}",
            )
        return result

    def get_local_token(self) -> str:
        url = (
            "https://api.vtexcommercestable.com.br/api/vtexid/apptoken/login?an="
            f"{quote(self.account_name, safe='')}"
        )
        result = self._request_url(
            operation="get_local_token",
            method="POST",
            url=url,
            payload={"appkey": self.app_key, "apptoken": self.app_token},
            include_api_credentials=False,
        )
        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="get_local_token",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=url,
            )
        token = str(result.get("token") or "").strip()
        auth_status = str(result.get("authStatus") or "").strip()
        if not token or (auth_status and auth_status.lower() != "success"):
            raise VtexImageApiError(
                operation="get_local_token",
                status=200,
                body=f"authStatus={auth_status or 'desconocido'}; token_present={bool(token)}",
                url=url,
            )
        return token

    @staticmethod
    def _first_https_url(value: Any) -> str | None:
        if isinstance(value, str):
            match = re.search(r"https://[^\s\"'<>}]+", value)
            return match.group(0) if match else None
        if isinstance(value, dict):
            for item in value.values():
                found = VtexImageClient._first_https_url(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = VtexImageClient._first_https_url(item)
                if found:
                    return found
        return None

    def _validate_catalog_asset(self, asset: dict[str, Any], *, file_name: str, url: str) -> dict[str, Any]:
        asset_id = str(asset.get("id") or file_name).strip()
        full_url = str(asset.get("fullUrl") or asset.get("url") or "").strip()
        expected_prefix = f"https://{self.account_name}.vtexassets.com/assets/"
        if not asset_id or not full_url.startswith(expected_prefix):
            raise VtexImageApiError(
                operation="upload_catalog_image",
                status=200,
                body=f"respuesta sin asset vÃ¡lido: {asset!r}",
                url=url,
            )
        return {**asset, "id": asset_id, "fullUrl": full_url}

    def upload_catalog_image(
        self,
        file_path: str | Path,
        *,
        token: str,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        name = str(file_name or path.name).strip()
        if not name:
            raise ValueError("file_name is required")
        local_token = str(token or "").strip()
        if not local_token:
            raise ValueError("token is required")

        boundary = f"----stech-vtex-{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        safe_header_name = name.replace('"', "_")
        file_bytes = path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name=""; filename="{safe_header_name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        url = (
            "https://app.io.vtex.com/vtex.catalog-images/v0/"
            f"{quote(self.account_name, safe='')}/master/images/save/{quote(name, safe='')}"
        )
        try:
            result = self._request_url(
                operation="upload_catalog_image",
                method="POST",
                url=url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "VtexIdclientAutCookie": local_token,
                },
                include_api_credentials=False,
            )
        except VtexImageApiError as exc:
            if exc.status != 409:
                raise
            parsed_body: Any = exc.body
            try:
                parsed_body = json.loads(exc.body)
            except (json.JSONDecodeError, TypeError):
                pass
            conflict_url = self._first_https_url(parsed_body)
            if not conflict_url:
                raise
            return self._validate_catalog_asset(
                {"id": name, "fullUrl": conflict_url, "conflict": True},
                file_name=name,
                url=url,
            )

        if not isinstance(result, dict):
            raise VtexImageApiError(
                operation="upload_catalog_image",
                status=200,
                body=f"respuesta inesperada: {result!r}",
                url=url,
            )
        return self._validate_catalog_asset(result, file_name=name, url=url)
