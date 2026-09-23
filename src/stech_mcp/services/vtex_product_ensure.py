from __future__ import annotations

import re
from typing import Any

from stech_mcp.domain.product_loader_models import normalize_partnumber
from stech_mcp.services.vtex_image_client import VtexImageApiError


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _remote_id(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if payload.get(key) is None:
            continue
        parsed = _positive_int(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _slug(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return token[:150]


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class VtexProductEnsureService:
    """Create only missing VTEX Product/SKU identities and verify them by read-back.

    This service deliberately does not publish price or inventory and creates new
    catalog records inactive/invisible. Images remain the responsibility of the
    already validated VtexImageSyncService.
    """

    def __init__(self, client: Any):
        self.client = client

    @staticmethod
    def _not_found(exc: Exception) -> bool:
        return isinstance(exc, VtexImageApiError) and exc.status == 404

    @staticmethod
    def _product_name(master: dict[str, Any], partnumber: str) -> str:
        return str(
            master.get("product_name")
            or master.get("name")
            or master.get("model")
            or partnumber
        ).strip()

    def _lookup_seller_product(self, partnumber: str) -> dict[str, Any] | None:
        try:
            product = self.client.get_seller_product_by_external_id(partnumber)
        except Exception as exc:
            if self._not_found(exc):
                return None
            raise
        if not isinstance(product, dict):
            return None
        return product

    @staticmethod
    def _seller_identity(product: dict[str, Any], partnumber: str, sku_ref: str) -> tuple[int | None, int | None]:
        external_id = str(product.get("externalId") or "").strip().upper()
        if external_id and external_id != partnumber:
            return None, None
        product_id = _remote_id(product, "id", "Id", "ProductId")
        sku_id = None
        for sku in product.get("skus") or []:
            if not isinstance(sku, dict):
                continue
            candidate = str(sku.get("externalId") or sku.get("RefId") or "").strip().upper()
            if candidate != sku_ref:
                continue
            sku_id = _remote_id(sku, "id", "Id", "SkuId")
            if sku_id is not None:
                break
        return product_id, sku_id

    def _build_product_payload(
        self,
        partnumber: str,
        master: dict[str, Any],
        category_id: int,
        brand_id: int,
    ) -> dict[str, Any]:
        name = self._product_name(master, partnumber)
        description = str(master.get("description") or master.get("description_text") or name).strip()
        short_description = str(master.get("short_description") or name).strip()
        department_id = _positive_int(master.get("vtex_department_id") or master.get("department_id")) or category_id
        return {
            "Name": name,
            "DepartmentId": department_id,
            "CategoryId": category_id,
            "BrandId": brand_id,
            "LinkId": _slug(f"{name}-{partnumber}"),
            "RefId": partnumber,
            "IsVisible": False,
            "IsActive": False,
            "Description": description,
            "DescriptionShort": short_description,
            "Title": name,
        }

    def _build_sku_payload(
        self,
        partnumber: str,
        master: dict[str, Any],
        product_id: int,
    ) -> dict[str, Any]:
        name = self._product_name(master, partnumber)
        height = _positive_float(master.get("package_height_cm"), 1.0)
        length = _positive_float(master.get("package_length_cm"), 1.0)
        width = _positive_float(master.get("package_width_cm"), 1.0)
        weight_kg = _positive_float(master.get("package_weight_g"), 100.0) / 1000.0
        return {
            "ProductId": product_id,
            "Name": name,
            "RefId": f"{partnumber}-S",
            "IsActive": False,
            "ActivateIfPossible": False,
            "PackagedHeight": height,
            "PackagedLength": length,
            "PackagedWidth": width,
            "PackagedWeightKg": weight_kg,
            "Height": height,
            "Length": length,
            "Width": width,
            "WeightKg": weight_kg,
            "CubicWeight": 0,
            "IsKit": False,
            "CommercialConditionId": 1,
            "MeasurementUnit": "un",
            "UnitMultiplier": 1,
        }

    def _verify_product(self, product_id: int, partnumber: str) -> dict[str, Any]:
        product = self.client.get_product(product_id)
        ref_id = str(product.get("RefId") or product.get("refId") or "").strip().upper()
        if ref_id != partnumber:
            raise RuntimeError(
                f"VTEX Product read-back mismatch: expected RefId={partnumber}, got {ref_id or '<empty>'}"
            )
        return product

    def _verify_sku(self, sku_id: int, sku_ref: str, product_id: int) -> dict[str, Any]:
        sku = self.client.get_sku(sku_id)
        ref_id = str(sku.get("RefId") or sku.get("refId") or "").strip().upper()
        read_product_id = _remote_id(sku, "ProductId", "productId")
        if ref_id != sku_ref or read_product_id != product_id:
            raise RuntimeError(
                "VTEX SKU read-back mismatch: "
                f"expected RefId={sku_ref}, ProductId={product_id}; "
                f"got RefId={ref_id or '<empty>'}, ProductId={read_product_id}"
            )
        return sku

    def _create_sku_for_product(
        self,
        partnumber: str,
        master: dict[str, Any],
        product_id: int,
        *,
        product_created: bool,
    ) -> dict[str, Any]:
        sku_ref = f"{partnumber}-S"
        try:
            created_sku = self.client.create_sku(self._build_sku_payload(partnumber, master, product_id))
        except Exception:
            if product_created:
                return {
                    "status": "PARTIAL_CREATED",
                    "product_created": True,
                    "sku_created": False,
                    "product_id": product_id,
                    "product_ref_id": partnumber,
                    "sku_ref_id": sku_ref,
                    "read_back_verified": False,
                    "blocking_reasons": ["VTEX_SKU_CREATE_FAILED"],
                }
            raise
        sku_id = _remote_id(created_sku, "Id", "id", "SkuId")
        if sku_id is None:
            raise RuntimeError("VTEX SKU create did not return a valid id")
        self._verify_sku(sku_id, sku_ref, product_id)
        return {
            "status": "CREATED",
            "product_created": product_created,
            "sku_created": True,
            "product_id": product_id,
            "sku_id": sku_id,
            "product_ref_id": partnumber,
            "sku_ref_id": sku_ref,
            "read_back_verified": True,
        }

    def ensure(
        self,
        partnumber: str,
        master: dict[str, Any],
        *,
        category_id: int,
        brand_id: int,
        known_product_id: int | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        sku_ref = f"{normalized}-S"

        persisted_product_id = _positive_int(known_product_id)
        if persisted_product_id is not None:
            self._verify_product(persisted_product_id, normalized)
            if hasattr(self.client, "resolve_sku_id"):
                try:
                    existing_sku_id = self.client.resolve_sku_id(sku_ref)
                except Exception as exc:
                    if not self._not_found(exc):
                        raise
                else:
                    parsed_sku_id = _positive_int(existing_sku_id)
                    if parsed_sku_id is not None:
                        self._verify_sku(parsed_sku_id, sku_ref, persisted_product_id)
                        return {
                            "status": "EXISTS",
                            "product_created": False,
                            "sku_created": False,
                            "product_id": persisted_product_id,
                            "sku_id": parsed_sku_id,
                            "product_ref_id": normalized,
                            "sku_ref_id": sku_ref,
                            "read_back_verified": True,
                        }
            return self._create_sku_for_product(
                normalized,
                master,
                persisted_product_id,
                product_created=False,
            )

        seller_product = self._lookup_seller_product(normalized)
        if seller_product is not None:
            external_id = str(seller_product.get("externalId") or "").strip().upper()
            if external_id and external_id != normalized:
                return {
                    "status": "VERIFY_FAILED",
                    "product_created": False,
                    "sku_created": False,
                    "read_back_verified": False,
                    "blocking_reasons": ["VTEX_PRODUCT_REFID_MISMATCH"],
                }
            product_id, sku_id = self._seller_identity(seller_product, normalized, sku_ref)
            if product_id is None:
                return {
                    "status": "VERIFY_FAILED",
                    "product_created": False,
                    "sku_created": False,
                    "read_back_verified": False,
                    "blocking_reasons": ["VTEX_PRODUCT_ID_MISSING"],
                }
            if sku_id is not None:
                return {
                    "status": "EXISTS",
                    "product_created": False,
                    "sku_created": False,
                    "product_id": product_id,
                    "sku_id": sku_id,
                    "product_ref_id": normalized,
                    "sku_ref_id": sku_ref,
                    "read_back_verified": True,
                }
            return self._create_sku_for_product(normalized, master, product_id, product_created=False)

        parsed_category = _positive_int(category_id)
        parsed_brand = _positive_int(brand_id)
        blocking: list[str] = []
        if parsed_category is None:
            blocking.append("VTEX_CATEGORY_ID_REQUIRED")
        if parsed_brand is None:
            blocking.append("VTEX_BRAND_ID_REQUIRED")
        if blocking:
            return {
                "status": "REVIEW_REQUIRED",
                "product_created": False,
                "sku_created": False,
                "read_back_verified": False,
                "blocking_reasons": blocking,
            }

        created_product = self.client.create_product(
            self._build_product_payload(normalized, master, parsed_category, parsed_brand)
        )
        product_id = _remote_id(created_product, "Id", "id", "ProductId")
        if product_id is None:
            raise RuntimeError("VTEX Product create did not return a valid id")
        self._verify_product(product_id, normalized)
        return self._create_sku_for_product(normalized, master, product_id, product_created=True)
