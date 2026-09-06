from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from stech_mcp.services.vtex_image_client import VtexImageApiError


_PRODUCT_UPDATE_FIELDS = (
    "id",
    "externalId",
    "status",
    "name",
    "brandId",
    "description",
    "categoryIds",
    "specs",
    "attributes",
    "slug",
    "transportModal",
    "taxCode",
    "images",
    "skus",
    "origin",
)
_PRODUCT_REQUIRED_FIELDS = (
    "status",
    "name",
    "brandId",
    "categoryIds",
    "specs",
    "attributes",
    "slug",
    "images",
    "skus",
    "origin",
)
_SKU_UPDATE_FIELDS = (
    "id",
    "name",
    "externalId",
    "description",
    "ean",
    "manufacturerCode",
    "isActive",
    "weight",
    "dimensions",
    "RealWeight",
    "RealDimensions",
    "specs",
    "images",
)
_SKU_REQUIRED_FIELDS = ("isActive", "weight", "dimensions", "specs", "images")


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _copy_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    copied: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        item: dict[str, Any] = {}
        if "name" in row:
            item["name"] = deepcopy(row.get("name"))
        if "values" in row:
            item["values"] = deepcopy(row.get("values"))
        if "value" in row:
            item["value"] = deepcopy(row.get("value"))
        copied.append(item)
    return copied


def _copy_attributes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    copied: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        if "name" not in row or "value" not in row:
            continue
        copied.append({"name": deepcopy(row.get("name")), "value": deepcopy(row.get("value"))})
    return copied


def _copy_product_image(row: dict[str, Any]) -> dict[str, Any]:
    copied = {
        "id": str(row.get("id") or "").strip(),
        "url": str(row.get("url") or "").strip(),
    }
    if row.get("alt") is not None:
        copied["alt"] = deepcopy(row.get("alt"))
    return copied


def _product_images(product: dict[str, Any]) -> list[dict[str, Any]]:
    rows = product.get("images")
    if not isinstance(rows, list):
        return []
    return [
        _copy_product_image(row)
        for row in rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    ]


def _sku_images(sku: dict[str, Any]) -> list[str]:
    rows = sku.get("images")
    if not isinstance(rows, list):
        return []
    return [str(value).strip() for value in rows if str(value or "").strip()]


def _seller_skus(product: dict[str, Any]) -> list[dict[str, Any]]:
    rows = product.get("skus")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _find_target_sku(product: dict[str, Any], partnumber: str) -> dict[str, Any] | None:
    normalized = _normalize_partnumber(partnumber)
    requested_ref = f"{normalized}-S"
    skus = _seller_skus(product)

    exact_ref = [row for row in skus if _normalize_partnumber(row.get("externalId")) == requested_ref]
    if len(exact_ref) == 1:
        return exact_ref[0]

    exact_manufacturer = [
        row for row in skus if _normalize_partnumber(row.get("manufacturerCode")) == normalized
    ]
    if len(exact_manufacturer) == 1:
        return exact_manufacturer[0]

    product_ref = _normalize_partnumber(product.get("externalId"))
    if product_ref == normalized and len(skus) == 1:
        return skus[0]
    return None


def _seller_remote_files(product: dict[str, Any], sku: dict[str, Any]) -> list[dict[str, Any]]:
    product_by_id = {
        _normalize_key(row.get("id")): row
        for row in _product_images(product)
        if _normalize_key(row.get("id"))
    }
    result: list[dict[str, Any]] = []
    for index, image_id in enumerate(_sku_images(sku)):
        product_image = product_by_id.get(_normalize_key(image_id), {})
        result.append(
            {
                "id": image_id,
                "archive_id": None,
                "name": image_id,
                "url": str(product_image.get("url") or "").strip() or None,
                "label": product_image.get("alt"),
                "is_main": index == 0,
            }
        )
    return result


def _expected_local_image_ids(images: list[dict[str, Any]]) -> list[str]:
    return [Path(str(row.get("storage_path") or "")).name for row in images]


def _remote_has_local_images(
    product: dict[str, Any],
    sku: dict[str, Any],
    expected_ids: list[str],
) -> bool:
    if not expected_ids:
        return False
    sku_ids = _sku_images(sku)
    if not sku_ids:
        return False
    sku_keys = [_normalize_key(value) for value in sku_ids]
    expected_keys = [_normalize_key(value) for value in expected_ids]
    if sku_keys[0] != expected_keys[0]:
        return False
    if not set(expected_keys).issubset(set(sku_keys)):
        return False

    product_by_id = {
        _normalize_key(row.get("id")): row
        for row in _product_images(product)
        if _normalize_key(row.get("id"))
    }
    for key in expected_keys:
        row = product_by_id.get(key)
        if not row or not str(row.get("url") or "").strip():
            return False
    return True


def _merge_product_images(
    local_assets: list[dict[str, Any]],
    existing_images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in [*local_assets, *existing_images]:
        key = _normalize_key(source.get("id"))
        if not key or key in seen:
            continue
        copied = _copy_product_image(source)
        if not copied["url"]:
            continue
        merged.append(copied)
        seen.add(key)
    return merged


def _merge_sku_image_ids(local_ids: list[str], existing_ids: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*local_ids, *existing_ids]:
        key = _normalize_key(value)
        if not key or key in seen:
            continue
        merged.append(str(value).strip())
        seen.add(key)
    return merged


def _copy_sku_for_update(sku: dict[str, Any], *, images: list[str] | None = None) -> dict[str, Any]:
    missing = [key for key in _SKU_REQUIRED_FIELDS if key not in sku]
    if missing:
        raise ValueError(f"SKU Seller Portal incompleto; faltan campos requeridos: {', '.join(missing)}")

    copied: dict[str, Any] = {}
    for key in _SKU_UPDATE_FIELDS:
        if key not in sku:
            continue
        if key == "specs":
            copied[key] = _copy_specs(sku.get(key))
        elif key == "images":
            copied[key] = list(images if images is not None else _sku_images(sku))
        else:
            copied[key] = deepcopy(sku.get(key))
    return copied


def _build_seller_product_payload(
    product: dict[str, Any],
    *,
    target_sku_id: str,
    product_images: list[dict[str, Any]],
    target_sku_images: list[str],
) -> dict[str, Any]:
    missing = [key for key in _PRODUCT_REQUIRED_FIELDS if key not in product]
    if missing:
        raise ValueError(
            "Producto Seller Portal incompleto; faltan campos requeridos: " + ", ".join(missing)
        )

    payload: dict[str, Any] = {}
    for key in _PRODUCT_UPDATE_FIELDS:
        if key not in product:
            continue
        if key == "attributes":
            payload[key] = _copy_attributes(product.get(key))
        elif key == "specs":
            payload[key] = _copy_specs(product.get(key))
        elif key == "images":
            payload[key] = [_copy_product_image(row) for row in product_images]
        elif key == "skus":
            copied_skus: list[dict[str, Any]] = []
            for sku in _seller_skus(product):
                sku_id = str(sku.get("id") or "").strip()
                copied_skus.append(
                    _copy_sku_for_update(
                        sku,
                        images=target_sku_images if sku_id == str(target_sku_id) else None,
                    )
                )
            payload[key] = copied_skus
        else:
            payload[key] = deepcopy(product.get(key))
    return payload


def _protected_snapshot(product: dict[str, Any]) -> dict[str, Any]:
    """Canonical non-image state used to prove that an update is image-only."""
    snapshot: dict[str, Any] = {}
    for key in _PRODUCT_UPDATE_FIELDS:
        if key in {"images", "skus"} or key not in product:
            continue
        if key == "attributes":
            snapshot[key] = _copy_attributes(product.get(key))
        elif key == "specs":
            snapshot[key] = _copy_specs(product.get(key))
        else:
            snapshot[key] = deepcopy(product.get(key))

    sku_snapshots: list[dict[str, Any]] = []
    for sku in _seller_skus(product):
        row: dict[str, Any] = {}
        for key in _SKU_UPDATE_FIELDS:
            if key == "images" or key not in sku:
                continue
            if key == "specs":
                row[key] = _copy_specs(sku.get(key))
            else:
                row[key] = deepcopy(sku.get(key))
        sku_snapshots.append(row)
    snapshot["skus"] = sku_snapshots
    return snapshot


class VtexImageSyncService:
    """Synchronize approved local images through CatalogV2 / Seller Portal."""

    def __init__(
        self,
        *,
        local_service: Any,
        vtex_client: Any | None,
        publication_repository: Any,
        signer: Any,
        audit_repository: Any,
    ):
        self.local_service = local_service
        self.vtex_client = vtex_client
        self.publication_repository = publication_repository
        # Kept for constructor compatibility. CatalogV2 uploads local bytes to
        # vtex.catalog-images and therefore does not use signed public URLs.
        self.signer = signer
        self.audit_repository = audit_repository

    def _configuration_error(self, partnumber: str) -> dict[str, Any]:
        return {
            "found": True,
            "partnumber": partnumber,
            "state": "ERROR",
            "reason": "vtex_credentials_not_configured",
            "uploaded_count": 0,
            "asset_reused_count": 0,
            "verified_count": 0,
            "skipped_count": 0,
            "write_blocked": True,
            "transport": "catalog_seller_portal",
        }

    def _error_reason(self, exc: VtexImageApiError) -> str:
        if exc.status == 401:
            return "vtex_credentials_rejected"
        operation = str(exc.operation or "")
        is_catalog_images = operation in {"get_local_token", "upload_catalog_image"}
        if exc.status == 403:
            return "vtex_catalog_images_forbidden" if is_catalog_images else "vtex_seller_portal_forbidden"
        if exc.status is not None and exc.status >= 500:
            return (
                "vtex_catalog_images_unavailable"
                if is_catalog_images
                else "vtex_seller_portal_unavailable"
            )
        if exc.status is None:
            return "vtex_network_error"
        return "vtex_catalog_images_error" if is_catalog_images else "vtex_seller_portal_error"

    def _error_detail(self, exc: VtexImageApiError) -> dict[str, Any]:
        detail = exc.as_dict()
        detail.update(
            {
                "account_name": getattr(self.vtex_client, "account_name", None),
                "environment": getattr(self.vtex_client, "environment", None),
                "credentials_configured": self.vtex_client is not None,
                "stage": exc.operation,
            }
        )
        return detail

    def _publication_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "product_image_id": row.get("product_image_id"),
                "status": row.get("status"),
                "remote_file_id": row.get("remote_file_id"),
                "remote_archive_id": row.get("remote_archive_id"),
                "remote_url": row.get("remote_url"),
                "position": row.get("position"),
                "is_main": row.get("is_main"),
            }
            for row in rows
        ]

    def _audit(self, *, partnumber: str, detail: dict[str, Any]) -> None:
        self.audit_repository.add_audit_event(
            partnumber=partnumber,
            event_type="VTEX_IMAGES_SYNC",
            actor_source="STECH_MCP",
            channel="VTEX",
            detail=detail,
        )

    def _read_seller_product(self, partnumber: str) -> tuple[dict[str, Any], dict[str, Any], int]:
        product = dict(self.vtex_client.get_seller_product_by_external_id(partnumber) or {})
        target_sku = _find_target_sku(product, partnumber)
        if target_sku is None:
            raise LookupError("seller_portal_sku_not_found")
        try:
            sku_id = int(target_sku.get("id"))
        except (TypeError, ValueError) as exc:
            raise LookupError("seller_portal_sku_id_invalid") from exc
        if sku_id <= 0:
            raise LookupError("seller_portal_sku_id_invalid")
        return product, target_sku, sku_id

    def _mark_verified_publications(
        self,
        *,
        partnumber: str,
        account_code: str,
        sku_id: int,
        images: list[dict[str, Any]],
        product: dict[str, Any],
    ) -> int:
        product_by_id = {
            _normalize_key(row.get("id")): row
            for row in _product_images(product)
            if _normalize_key(row.get("id"))
        }
        verified = 0
        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            file_name = Path(str(image.get("storage_path") or "")).name
            remote = product_by_id.get(_normalize_key(file_name))
            if not remote or not str(remote.get("url") or "").strip():
                continue
            self.publication_repository.mark_verified(
                product_image_id=image_id,
                partnumber=partnumber,
                channel="VTEX",
                account_code=account_code,
                remote_sku_id=sku_id,
                remote_file_id=None,
                remote_archive_id=None,
                remote_url=str(remote.get("url") or "") or None,
                position=position,
                is_main=position == 1,
            )
            verified += 1
        return verified

    def status(self, partnumber: str, *, account_code: str = "VTEX_STECH") -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        account = str(account_code or "VTEX_STECH").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")

        local = self.local_service.validate(normalized)
        result: dict[str, Any] = {
            "found": True,
            "partnumber": normalized,
            "transport": "catalog_seller_portal",
            "local_state": local.get("state"),
            "local_image_count": int(local.get("image_count") or 0),
            "product_id": None,
            "remote_sku_id": None,
            "sku_ref_id": None,
            "product_ref_id": None,
            "manufacturer_code": None,
            "remote_image_count": None,
            "seller_portal_image_count": None,
            "catalog_system_image_count": None,
            "remote_files": [],
            "remote_main_file": None,
            "publication_count": 0,
            "verified_publication_count": 0,
            "publications": [],
            "state": local.get("state"),
            "reason": local.get("reason"),
            "write_blocked": False,
        }
        if local.get("state") != "READY":
            return result
        if self.vtex_client is None:
            result.update(
                {
                    "state": "ERROR",
                    "reason": "vtex_credentials_not_configured",
                    "write_blocked": True,
                }
            )
            return result

        try:
            product, target_sku, sku_id = self._read_seller_product(normalized)
        except VtexImageApiError as exc:
            result.update(
                {
                    "state": "BLOCKED",
                    "reason": self._error_reason(exc),
                    "write_blocked": True,
                    "vtex_error": self._error_detail(exc),
                }
            )
            return result
        except LookupError as exc:
            result.update({"state": "BLOCKED", "reason": str(exc), "write_blocked": True})
            return result

        product_id = str(product.get("id") or "").strip()
        sku_ref_id = str(target_sku.get("externalId") or f"{normalized}-S").strip()
        origin = str(product.get("origin") or "").strip()
        if origin and _normalize_key(origin) != _normalize_key(getattr(self.vtex_client, "account_name", "")):
            result.update(
                {
                    "product_id": product_id or None,
                    "remote_sku_id": sku_id,
                    "sku_ref_id": sku_ref_id,
                    "state": "BLOCKED",
                    "reason": "seller_portal_origin_mismatch",
                    "write_blocked": True,
                }
            )
            return result

        publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=account,
                remote_sku_id=sku_id,
            )
            or []
        )
        verified_image_ids = {
            int(row["product_image_id"])
            for row in publications
            if row.get("product_image_id") is not None
            and str(row.get("status") or "").upper() == "VERIFIED"
        }
        remote_files = _seller_remote_files(product, target_sku)
        expected_ids = _expected_local_image_ids(
            sorted(
                [dict(row) for row in (local.get("images") or [])],
                key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
            )
        )
        fully_synced = _remote_has_local_images(product, target_sku, expected_ids)
        all_present = set(map(_normalize_key, expected_ids)).issubset(
            set(map(_normalize_key, _sku_images(target_sku)))
        )
        main_ok = bool(expected_ids) and bool(_sku_images(target_sku)) and (
            _normalize_key(_sku_images(target_sku)[0]) == _normalize_key(expected_ids[0])
        )

        result.update(
            {
                "product_id": product_id or None,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "product_ref_id": product.get("externalId"),
                "manufacturer_code": target_sku.get("manufacturerCode"),
                "remote_image_count": len(_sku_images(target_sku)),
                "seller_portal_image_count": len(_product_images(product)),
                "remote_files": remote_files,
                "remote_main_file": remote_files[0] if remote_files else None,
                "publication_count": len(publications),
                "verified_publication_count": len(verified_image_ids),
                "publications": self._publication_summary(publications),
                "state": "SYNCED" if fully_synced else "READY",
                "reason": None if fully_synced else ("main_image_not_first" if all_present and not main_ok else None),
                "write_blocked": False,
            }
        )
        return result

    def sync(self, partnumber: str, *, account_code: str = "VTEX_STECH") -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        account = str(account_code or "VTEX_STECH").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")

        local_sync = self.local_service.sync(normalized)
        validation = self.local_service.validate(normalized)
        if validation.get("state") != "READY":
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": validation.get("state") or local_sync.get("state") or "REVIEW",
                "reason": validation.get("reason") or local_sync.get("reason"),
                "local_image_count": int(validation.get("image_count") or 0),
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }
        if self.vtex_client is None:
            return self._configuration_error(normalized)

        images = sorted(
            [dict(row) for row in (validation.get("images") or [])],
            key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
        )
        expected_ids = _expected_local_image_ids(images)

        try:
            product, target_sku, sku_id = self._read_seller_product(normalized)
        except VtexImageApiError as exc:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": self._error_reason(exc),
                "local_image_count": len(images),
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
                "vtex_error": self._error_detail(exc),
            }
        except LookupError as exc:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": str(exc),
                "local_image_count": len(images),
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }

        product_id = str(product.get("id") or "").strip()
        sku_ref_id = str(target_sku.get("externalId") or f"{normalized}-S").strip()
        origin = str(product.get("origin") or "").strip()
        account_name = str(getattr(self.vtex_client, "account_name", "") or "").strip()
        if not product_id:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": "seller_portal_product_id_missing",
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }
        if origin and _normalize_key(origin) != _normalize_key(account_name):
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": "seller_portal_origin_mismatch",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }

        remote_before = _seller_remote_files(product, target_sku)
        before_count = len(_sku_images(target_sku))
        before_protected = _protected_snapshot(product)

        # Fully idempotent fast path: do not request a local token, upload, or PUT.
        if _remote_has_local_images(product, target_sku, expected_ids):
            verified_count = self._mark_verified_publications(
                partnumber=normalized,
                account_code=account,
                sku_id=sku_id,
                images=images,
                product=product,
            )
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": 0,
                "asset_reused_count": 0,
                "verified_count": verified_count,
                "skipped_count": len(images),
                "product_update_performed": False,
                "state": "SYNCED",
                "reason": None,
                "write_blocked": False,
                "errors": [],
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        existing_product_images = _product_images(product)
        existing_by_id = {
            _normalize_key(row.get("id")): row
            for row in existing_product_images
            if _normalize_key(row.get("id"))
        }
        local_assets: list[dict[str, Any]] = []
        uploaded_count = 0
        reused_count = 0
        token: str | None = None

        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            file_path = str(image.get("storage_path") or "")
            file_name = Path(file_path).name
            existing_asset = existing_by_id.get(_normalize_key(file_name))
            if existing_asset and str(existing_asset.get("url") or "").strip():
                local_assets.append(_copy_product_image(existing_asset))
                reused_count += 1
                continue

            try:
                if token is None:
                    token = self.vtex_client.get_local_token()
                asset = dict(self.vtex_client.upload_catalog_image(file_path, token=token) or {})
                remote_id = str(asset.get("id") or "").strip()
                remote_url = str(asset.get("fullUrl") or asset.get("url") or "").strip()
                if _normalize_key(remote_id) != _normalize_key(file_name):
                    raise VtexImageApiError(
                        operation="upload_catalog_image",
                        status=200,
                        body=f"asset id inesperado: esperado={file_name!r}; recibido={remote_id!r}",
                        url=remote_url or "https://app.io.vtex.com/vtex.catalog-images",
                    )
                local_assets.append({"id": remote_id, "url": remote_url})
                if bool(asset.get("conflict")):
                    reused_count += 1
                else:
                    uploaded_count += 1
            except VtexImageApiError as exc:
                reason = self._error_reason(exc)
                try:
                    self.publication_repository.upsert_publication(
                        product_image_id=image_id,
                        partnumber=normalized,
                        channel="VTEX",
                        account_code=account,
                        remote_sku_id=sku_id,
                        remote_file_id=None,
                        remote_archive_id=None,
                        remote_url=None,
                        position=position,
                        is_main=position == 1,
                        status="ERROR",
                        last_error=str(exc)[:4000],
                    )
                except Exception:
                    pass
                detail = {
                    "transport": "catalog_seller_portal",
                    "product_id": product_id,
                    "remote_sku_id": sku_id,
                    "sku_ref_id": sku_ref_id,
                    "local_image_count": len(images),
                    "remote_before_count": before_count,
                    "remote_after_count": before_count,
                    "uploaded_count": uploaded_count,
                    "asset_reused_count": reused_count,
                    "verified_count": 0,
                    "skipped_count": 0,
                    "product_update_performed": False,
                    "state": "ERROR",
                    "reason": reason,
                    "write_blocked": True,
                    "errors": [
                        {
                            "product_image_id": image_id,
                            "file": file_name,
                            "error": str(exc),
                        }
                    ],
                    "vtex_error": self._error_detail(exc),
                }
                self._audit(partnumber=normalized, detail=detail)
                return {"found": True, "partnumber": normalized, **detail}
            except Exception as exc:
                detail = {
                    "transport": "catalog_seller_portal",
                    "product_id": product_id,
                    "remote_sku_id": sku_id,
                    "sku_ref_id": sku_ref_id,
                    "local_image_count": len(images),
                    "remote_before_count": before_count,
                    "remote_after_count": before_count,
                    "uploaded_count": uploaded_count,
                    "asset_reused_count": reused_count,
                    "verified_count": 0,
                    "skipped_count": 0,
                    "product_update_performed": False,
                    "state": "ERROR",
                    "reason": "local_image_upload_error",
                    "write_blocked": True,
                    "errors": [
                        {
                            "product_image_id": image_id,
                            "file": file_name,
                            "error": str(exc),
                        }
                    ],
                }
                self._audit(partnumber=normalized, detail=detail)
                return {"found": True, "partnumber": normalized, **detail}

        local_ids = [str(row.get("id") or "").strip() for row in local_assets]
        merged_product_images = _merge_product_images(local_assets, existing_product_images)
        merged_target_sku_images = _merge_sku_image_ids(local_ids, _sku_images(target_sku))

        try:
            payload = _build_seller_product_payload(
                product,
                target_sku_id=str(sku_id),
                product_images=merged_product_images,
                target_sku_images=merged_target_sku_images,
            )
        except ValueError as exc:
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": uploaded_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "state": "BLOCKED",
                "reason": "seller_portal_payload_invalid",
                "write_blocked": True,
                "errors": [{"error": str(exc)}],
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        # Hard guardrail before the PUT: only image fields may differ.
        if _protected_snapshot(payload) != before_protected:
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": uploaded_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": False,
                "state": "BLOCKED",
                "reason": "non_image_payload_change_detected",
                "write_blocked": True,
                "errors": [],
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        current_product_images = [_copy_product_image(row) for row in existing_product_images]
        current_target_ids = _sku_images(target_sku)
        update_needed = (
            current_product_images != merged_product_images
            or current_target_ids != merged_target_sku_images
        )

        if update_needed:
            try:
                self.vtex_client.update_seller_product(product_id, payload)
            except VtexImageApiError as exc:
                reason = self._error_reason(exc)
                detail = {
                    "transport": "catalog_seller_portal",
                    "product_id": product_id,
                    "remote_sku_id": sku_id,
                    "sku_ref_id": sku_ref_id,
                    "local_image_count": len(images),
                    "remote_before_count": before_count,
                    "remote_after_count": None,
                    "uploaded_count": uploaded_count,
                    "asset_reused_count": reused_count,
                    "verified_count": 0,
                    "skipped_count": 0,
                    "product_update_performed": False,
                    "state": "ERROR",
                    "reason": reason,
                    "write_blocked": True,
                    "errors": [{"error": str(exc)}],
                    "vtex_error": self._error_detail(exc),
                }
                self._audit(partnumber=normalized, detail=detail)
                return {"found": True, "partnumber": normalized, **detail}

        try:
            product_after = dict(self.vtex_client.get_seller_product(product_id) or {})
        except VtexImageApiError as exc:
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": None,
                "uploaded_count": uploaded_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": bool(update_needed),
                "state": "PARTIAL" if update_needed else "ERROR",
                "reason": "vtex_readback_failed",
                "write_blocked": True,
                "errors": [{"error": str(exc)}],
                "vtex_error": self._error_detail(exc),
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        target_after = _find_target_sku(product_after, normalized)
        if target_after is None:
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": None,
                "uploaded_count": uploaded_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": bool(update_needed),
                "state": "ERROR",
                "reason": "seller_portal_sku_not_found_after_update",
                "write_blocked": True,
                "errors": [],
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        if _protected_snapshot(product_after) != before_protected:
            detail = {
                "transport": "catalog_seller_portal",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": len(_sku_images(target_after)),
                "uploaded_count": uploaded_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": 0,
                "product_update_performed": bool(update_needed),
                "state": "ERROR",
                "reason": "non_image_fields_changed",
                "write_blocked": True,
                "errors": [],
            }
            self._audit(partnumber=normalized, detail=detail)
            return {"found": True, "partnumber": normalized, **detail}

        verified_remote = _remote_has_local_images(product_after, target_after, expected_ids)
        verified_count = self._mark_verified_publications(
            partnumber=normalized,
            account_code=account,
            sku_id=sku_id,
            images=images,
            product=product_after,
        )
        remote_after = _seller_remote_files(product_after, target_after)
        state = "SYNCED" if verified_remote and verified_count == len(images) else "ERROR"
        detail = {
            "transport": "catalog_seller_portal",
            "product_id": product_id,
            "remote_sku_id": sku_id,
            "sku_ref_id": sku_ref_id,
            "local_image_count": len(images),
            "remote_before_count": before_count,
            "remote_after_count": len(_sku_images(target_after)),
            "remote_files": remote_after,
            "remote_main_file": remote_after[0] if remote_after else None,
            "uploaded_count": uploaded_count,
            "asset_reused_count": reused_count,
            "verified_count": verified_count,
            "skipped_count": 0,
            "product_update_performed": bool(update_needed),
            "state": state,
            "reason": None if state == "SYNCED" else "seller_portal_readback_mismatch",
            "write_blocked": state != "SYNCED",
            "errors": [],
        }
        self._audit(partnumber=normalized, detail=detail)
        return {"found": True, "partnumber": normalized, **detail}
