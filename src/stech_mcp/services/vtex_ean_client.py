from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .vtex_image_client import VtexImageApiError, VtexImageClient


class VtexEanClient(VtexImageClient):
    """Narrow Catalog client for SKU EAN operations.

    It deliberately reuses the already proven VTEX transport/authentication
    from ``VtexImageClient`` while keeping barcode writes isolated from image
    synchronization behavior.
    """

    def get_sku_eans(self, sku_id: int) -> list[str]:
        parsed = int(sku_id)
        path = f"/api/catalog/pvt/stockkeepingunit/{parsed}/ean"
        result = self._request(
            operation="get_sku_eans",
            method="GET",
            path=path,
        )
        if result is None:
            return []
        if isinstance(result, str):
            token = result.strip()
            return [token] if token else []
        if isinstance(result, list):
            values: list[str] = []
            for item in result:
                token = str(item or "").strip()
                if token and token not in values:
                    values.append(token)
            return values
        if isinstance(result, dict):
            raw = result.get("Ean")
            if raw is None:
                raw = result.get("ean")
            if raw is None:
                raw = result.get("EAN")
            if raw is None:
                raw = result.get("eans")
            if isinstance(raw, list):
                values = []
                for item in raw:
                    token = str(item or "").strip()
                    if token and token not in values:
                        values.append(token)
                return values
            token = str(raw or "").strip()
            return [token] if token else []
        raise VtexImageApiError(
            operation="get_sku_eans",
            status=200,
            body=f"respuesta inesperada: {result!r}",
            url=f"{self.base_url}{path}",
        )

    def create_sku_ean(self, sku_id: int, ean: str) -> dict[str, Any]:
        parsed = int(sku_id)
        token = str(ean or "").strip()
        if not token:
            raise ValueError("ean is required")
        path = (
            f"/api/catalog/pvt/stockkeepingunit/{parsed}/ean/"
            f"{quote(token, safe='')}"
        )
        result = self._request(
            operation="create_sku_ean",
            method="POST",
            path=path,
        )
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        raise VtexImageApiError(
            operation="create_sku_ean",
            status=200,
            body=f"respuesta inesperada: {result!r}",
            url=f"{self.base_url}{path}",
        )
