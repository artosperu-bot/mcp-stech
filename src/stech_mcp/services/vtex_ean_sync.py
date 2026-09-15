from __future__ import annotations

from typing import Any

from .identity_barcode_extractor import canonical_gtin, validate_gtin
from .vtex_image_client import VtexImageApiError


class VtexEanSyncService:
    """Create a verified barcode on a VTEX SKU without overwriting anything.

    VTEX's Create SKU EAN endpoint is create-only. This service therefore reads
    the current remote values first, blocks on conflicts, performs at most one
    POST, and reads the values again before reporting success.
    """

    def __init__(self, client: Any) -> None:
        self.client = client

    @staticmethod
    def _normalize_partnumber(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _clean_values(values: Any) -> list[str]:
        if values is None:
            return []
        rows = values if isinstance(values, list) else [values]
        out: list[str] = []
        for raw in rows:
            token = str(raw or "").strip()
            if token and token not in out:
                out.append(token)
        return out

    @staticmethod
    def _select_verified_value(fields: dict[str, Any] | None) -> tuple[str | None, str | None]:
        payload = fields if isinstance(fields, dict) else {}
        first_invalid: str | None = None
        for key in ("ean", "upc", "gtin"):
            token = str(payload.get(key) or "").strip()
            if not token:
                continue
            if validate_gtin(token):
                return key, token
            if first_invalid is None:
                first_invalid = token
        return None, first_invalid

    @staticmethod
    def _error_result(exc: VtexImageApiError, *, partnumber: str, ean: str | None) -> dict[str, Any]:
        status = exc.status
        if status == 401:
            state, retryable = "VTEX_EAN_AUTH_FAILED", False
        elif status == 403:
            state, retryable = "VTEX_EAN_FORBIDDEN", False
        elif status == 404:
            state, retryable = "VTEX_SKU_NOT_FOUND", False
        elif status is None or status == 429 or (isinstance(status, int) and status >= 500):
            state, retryable = "VTEX_EAN_TEMPORARY_ERROR", True
        else:
            state, retryable = "VTEX_EAN_ERROR", False
        return {
            "state": state,
            "partnumber": partnumber,
            "ean": ean,
            "sku_id": None,
            "remote_eans": [],
            "retryable": retryable,
            "status_http": status,
            "error": str(exc),
        }

    def sync(self, partnumber: str, verified_fields: dict[str, Any] | None) -> dict[str, Any]:
        pn = self._normalize_partnumber(partnumber)
        if not pn:
            raise ValueError("partnumber is required")

        source_field, local_value = self._select_verified_value(verified_fields)
        if not source_field or not local_value:
            return {
                "state": "VTEX_EAN_INVALID_LOCAL_VALUE",
                "partnumber": pn,
                "ean": local_value,
                "source_field": source_field,
                "sku_id": None,
                "remote_eans": [],
                "retryable": False,
            }

        local_identity = canonical_gtin(local_value)
        if not local_identity:
            return {
                "state": "VTEX_EAN_INVALID_LOCAL_VALUE",
                "partnumber": pn,
                "ean": local_value,
                "source_field": source_field,
                "sku_id": None,
                "remote_eans": [],
                "retryable": False,
            }

        sku_id: int | None = None
        try:
            sku_id = int(self.client.resolve_sku_id(f"{pn}-S"))
            context = self.client.get_sku_context(sku_id)
            if not isinstance(context, dict):
                return {
                    "state": "VTEX_SKU_MISMATCH",
                    "partnumber": pn,
                    "ean": local_value,
                    "source_field": source_field,
                    "sku_id": sku_id,
                    "remote_eans": [],
                    "retryable": False,
                }

            remote_product_ref = str(
                context.get("ProductRefId")
                or context.get("productRefId")
                or context.get("ProductRefID")
                or ""
            ).strip().upper()
            if remote_product_ref and remote_product_ref != pn:
                return {
                    "state": "VTEX_SKU_MISMATCH",
                    "partnumber": pn,
                    "ean": local_value,
                    "source_field": source_field,
                    "sku_id": sku_id,
                    "remote_product_ref": remote_product_ref,
                    "remote_eans": [],
                    "retryable": False,
                }

            remote_eans = self._clean_values(self.client.get_sku_eans(sku_id))
            if any(canonical_gtin(value) == local_identity for value in remote_eans):
                return {
                    "state": "VTEX_EAN_ALREADY_PRESENT",
                    "partnumber": pn,
                    "ean": local_value,
                    "source_field": source_field,
                    "sku_id": sku_id,
                    "remote_eans": remote_eans,
                    "retryable": False,
                }

            if remote_eans:
                return {
                    "state": "VTEX_EAN_CONFLICT",
                    "partnumber": pn,
                    "ean": local_value,
                    "source_field": source_field,
                    "sku_id": sku_id,
                    "remote_eans": remote_eans,
                    "retryable": False,
                }

            self.client.create_sku_ean(sku_id, local_value)
            verified_remote = self._clean_values(self.client.get_sku_eans(sku_id))
            if any(canonical_gtin(value) == local_identity for value in verified_remote):
                return {
                    "state": "VTEX_EAN_SYNCED",
                    "partnumber": pn,
                    "ean": local_value,
                    "source_field": source_field,
                    "sku_id": sku_id,
                    "remote_eans": verified_remote,
                    "retryable": False,
                }

            return {
                "state": "VTEX_EAN_VERIFY_FAILED",
                "partnumber": pn,
                "ean": local_value,
                "source_field": source_field,
                "sku_id": sku_id,
                "remote_eans": verified_remote,
                "retryable": True,
            }

        except VtexImageApiError as exc:
            result = self._error_result(exc, partnumber=pn, ean=local_value)
            if sku_id is not None:
                result["sku_id"] = sku_id
            return result
