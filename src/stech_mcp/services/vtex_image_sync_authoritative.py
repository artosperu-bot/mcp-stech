from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from stech_mcp.services.vtex_image_client import VtexImageApiError
from stech_mcp.services.vtex_image_sync import (
    VtexImageSyncService as _LegacyVtexImageSyncService,
    _build_seller_product_payload,
    _copy_product_image,
    _find_target_sku,
    _normalize_key,
    _normalize_partnumber,
    _product_images,
    _protected_snapshot,
    _seller_remote_files,
    _seller_skus,
    _sku_images,
)


_IMAGE_EXTENSIONS = "jpg|jpeg|png|gif"


def _managed_position(asset_id: Any, partnumber: str) -> int | None:
    value = str(asset_id or "").strip()
    if not value:
        return None
    match = re.match(
        rf"^{re.escape(partnumber)}_(?P<position>\d{{1,3}})(?:__[0-9a-f]{{8,64}})?\.(?:{_IMAGE_EXTENSIONS})$",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    position = int(match.group("position"))
    return position if position > 0 else None


def _versioned_asset_name(image: dict[str, Any]) -> str:
    path = Path(str(image.get("storage_path") or ""))
    digest = str(image.get("sha256_hash") or "").strip().lower()
    if len(digest) < 8:
        raise ValueError("sha256_hash is required to replace an existing VTEX position")
    return f"{path.stem}__{digest[:12]}{path.suffix.lower()}"


def _verified_publication_for_image(
    publications: list[dict[str, Any]],
    *,
    product_image_id: int,
    position: int,
) -> dict[str, Any] | None:
    rows = [
        row
        for row in publications
        if row.get("product_image_id") is not None
        and int(row["product_image_id"]) == int(product_image_id)
        and int(row.get("position") or 0) == int(position)
        and str(row.get("status") or "").upper() == "VERIFIED"
    ]
    return rows[-1] if rows else None


def _managed_target_by_position(target_ids: list[str], partnumber: str) -> tuple[dict[int, str], set[int]]:
    by_position: dict[int, str] = {}
    duplicates: set[int] = set()
    for asset_id in target_ids:
        position = _managed_position(asset_id, partnumber)
        if position is None:
            continue
        if position in by_position and _normalize_key(by_position[position]) != _normalize_key(asset_id):
            duplicates.add(position)
            continue
        by_position[position] = asset_id
    return by_position, duplicates


def _product_asset_map(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _normalize_key(row.get("id")): row
        for row in _product_images(product)
        if _normalize_key(row.get("id")) and str(row.get("url") or "").strip()
    }


def _other_sku_image_ids(product: dict[str, Any], target_sku_id: int) -> set[str]:
    result: set[str] = set()
    for sku in _seller_skus(product):
        if str(sku.get("id") or "").strip() == str(target_sku_id):
            continue
        result.update(_normalize_key(value) for value in _sku_images(sku))
    return result


class VtexImageSyncService(_LegacyVtexImageSyncService):
    """Seller Portal sync where the local PN+position gallery is authoritative.

    The physical catalog-image asset is never explicitly deleted. The target SKU
    association is rebuilt from the current local positions, while images used by
    other SKUs remain attached at product level.
    """

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
            "remote_sku_id": None,
            "remote_image_count": None,
            "remote_files": [],
            "remote_main_file": None,
            "publication_count": 0,
            "verified_publication_count": 0,
            "state": local.get("state"),
            "reason": local.get("reason"),
            "write_blocked": False,
        }
        if local.get("state") != "READY":
            return result
        if self.vtex_client is None:
            result.update({"state": "ERROR", "reason": "vtex_credentials_not_configured", "write_blocked": True})
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

        images = sorted(
            [dict(row) for row in (local.get("images") or [])],
            key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
        )
        target_ids = _sku_images(target_sku)
        managed_by_position, duplicates = _managed_target_by_position(target_ids, normalized)
        publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=account,
                remote_sku_id=sku_id,
            )
            or []
        )
        product_assets = _product_asset_map(product)

        positions_ok = not duplicates and len(target_ids) == len(images)
        verified_current = 0
        if positions_ok:
            for index, image in enumerate(images):
                position = int(image["position"])
                asset_id = target_ids[index]
                if _managed_position(asset_id, normalized) != position:
                    positions_ok = False
                    break
                if _normalize_key(asset_id) not in product_assets:
                    positions_ok = False
                    break
                publication = _verified_publication_for_image(
                    publications,
                    product_image_id=int(image["product_image_id"]),
                    position=position,
                )
                if publication is not None:
                    verified_current += 1

        fully_synced = positions_ok and verified_current == len(images)
        remote_files = _seller_remote_files(product, target_sku)
        result.update(
            {
                "product_id": str(product.get("id") or "").strip() or None,
                "remote_sku_id": sku_id,
                "sku_ref_id": target_sku.get("externalId"),
                "product_ref_id": product.get("externalId"),
                "manufacturer_code": target_sku.get("manufacturerCode"),
                "remote_image_count": len(target_ids),
                "seller_portal_image_count": len(_product_images(product)),
                "remote_files": remote_files,
                "remote_main_file": remote_files[0] if remote_files else None,
                "publication_count": len(publications),
                "verified_publication_count": verified_current,
                "publications": self._publication_summary(publications),
                "state": "SYNCED" if fully_synced else "READY",
                "reason": None if fully_synced else ("remote_position_ambiguous" if duplicates else None),
                "write_blocked": bool(duplicates),
                "managed_positions": sorted(managed_by_position),
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
                "replaced_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
                "errors": list(validation.get("errors") or []),
            }
        if self.vtex_client is None:
            result = self._configuration_error(normalized)
            result.update({"replaced_count": 0, "removed_extra_count": 0})
            return result

        images = sorted(
            [dict(row) for row in (validation.get("images") or [])],
            key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
        )
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
                "replaced_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "removed_extra_count": 0,
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
                "replaced_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }

        product_id = str(product.get("id") or "").strip()
        sku_ref_id = str(target_sku.get("externalId") or f"{normalized}-S").strip()
        account_name = str(getattr(self.vtex_client, "account_name", "") or "").strip()
        origin = str(product.get("origin") or "").strip()
        if not product_id or (origin and _normalize_key(origin) != _normalize_key(account_name)):
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": "seller_portal_product_id_missing" if not product_id else "seller_portal_origin_mismatch",
                "product_id": product_id or None,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "uploaded_count": 0,
                "replaced_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
            }

        before_protected = _protected_snapshot(product)
        target_before = _sku_images(target_sku)
        before_count = len(target_before)
        product_assets_before = _product_asset_map(product)
        managed_before, duplicate_positions = _managed_target_by_position(target_before, normalized)
        if duplicate_positions:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "REVIEW",
                "reason": "remote_position_ambiguous",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": 0,
                "replaced_count": 0,
                "asset_reused_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
                "errors": [{"positions": sorted(duplicate_positions)}],
            }

        publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=account,
                remote_sku_id=sku_id,
            )
            or []
        )
        publication_positions = {
            int(row.get("position") or 0)
            for row in publications
            if int(row.get("position") or 0) > 0
        }
        local_positions = {int(row["position"]) for row in images}
        removed_extra_count = sum(
            1
            for asset_id in target_before
            if (_managed_position(asset_id, normalized) not in local_positions)
        )

        desired_assets: list[dict[str, Any]] = []
        desired_ids: list[str] = []
        uploaded_count = 0
        replaced_count = 0
        reused_count = 0
        skipped_count = 0
        token: str | None = None

        for index, image in enumerate(images):
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            file_path = str(image.get("storage_path") or "")
            canonical_name = Path(file_path).name
            current_asset_id = managed_before.get(position)
            current_publication = _verified_publication_for_image(
                publications,
                product_image_id=image_id,
                position=position,
            )
            existing_position_asset = (
                product_assets_before.get(_normalize_key(current_asset_id))
                if current_asset_id is not None
                else None
            )

            if current_publication is not None and existing_position_asset is not None:
                desired_assets.append(_copy_product_image(existing_position_asset))
                desired_ids.append(str(existing_position_asset["id"]))
                skipped_count += 1
                continue

            # When the product already has a correctly named positional image but
            # the local publication table has never seen it (migration / first run),
            # adopt it instead of manufacturing a replacement. If there is history
            # for this position and the current product_image_id differs, the local
            # binary changed and the replacement path below is intentional.
            if (
                current_publication is None
                and position not in publication_positions
                and existing_position_asset is not None
            ):
                desired_assets.append(_copy_product_image(existing_position_asset))
                desired_ids.append(str(existing_position_asset["id"]))
                skipped_count += 1
                continue

            ordinal_slot_exists = index < len(target_before)
            replacing = current_asset_id is not None or ordinal_slot_exists
            remote_name = canonical_name
            if _normalize_key(canonical_name) in product_assets_before:
                remote_name = _versioned_asset_name(image)

            candidate = product_assets_before.get(_normalize_key(remote_name))
            if candidate is not None:
                asset = _copy_product_image(candidate)
                reused_count += 1
            else:
                try:
                    if token is None:
                        token = self.vtex_client.get_local_token()
                    uploaded = dict(
                        self.vtex_client.upload_catalog_image(
                            file_path,
                            token=token,
                            file_name=remote_name,
                        )
                        or {}
                    )
                    returned_id = str(uploaded.get("id") or "").strip()
                    returned_url = str(uploaded.get("fullUrl") or uploaded.get("url") or "").strip()
                    if _normalize_key(returned_id) != _normalize_key(remote_name) or not returned_url:
                        raise VtexImageApiError(
                            operation="upload_catalog_image",
                            status=200,
                            body=f"asset inesperado: esperado={remote_name!r}; recibido={returned_id!r}",
                            url=returned_url or "https://app.io.vtex.com/vtex.catalog-images",
                        )
                    asset = {"id": returned_id, "url": returned_url}
                    if bool(uploaded.get("conflict")):
                        reused_count += 1
                except VtexImageApiError as exc:
                    detail = {
                        "transport": "catalog_seller_portal",
                        "product_id": product_id,
                        "remote_sku_id": sku_id,
                        "sku_ref_id": sku_ref_id,
                        "local_image_count": len(images),
                        "remote_before_count": before_count,
                        "remote_after_count": before_count,
                        "uploaded_count": uploaded_count,
                        "replaced_count": replaced_count,
                        "asset_reused_count": reused_count,
                        "verified_count": 0,
                        "skipped_count": skipped_count,
                        "removed_extra_count": 0,
                        "product_update_performed": False,
                        "state": "ERROR",
                        "reason": self._error_reason(exc),
                        "write_blocked": True,
                        "errors": [{"position": position, "file": canonical_name, "error": str(exc)}],
                        "vtex_error": self._error_detail(exc),
                    }
                    self._audit(partnumber=normalized, detail=detail)
                    return {"found": True, "partnumber": normalized, **detail}

            desired_assets.append(asset)
            desired_ids.append(str(asset["id"]))
            if replacing:
                replaced_count += 1
            else:
                uploaded_count += 1

        # The local folder is authoritative for the target SKU gallery. Product-level
        # images still referenced by a different SKU are preserved.
        other_sku_keys = _other_sku_image_ids(product, sku_id)
        desired_product_images = [_copy_product_image(row) for row in desired_assets]
        seen_product_keys = {_normalize_key(row.get("id")) for row in desired_product_images}
        for row in _product_images(product):
            key = _normalize_key(row.get("id"))
            if key in other_sku_keys and key not in seen_product_keys and str(row.get("url") or "").strip():
                desired_product_images.append(_copy_product_image(row))
                seen_product_keys.add(key)

        try:
            payload = _build_seller_product_payload(
                product,
                target_sku_id=str(sku_id),
                product_images=desired_product_images,
                target_sku_images=desired_ids,
            )
        except ValueError as exc:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": "seller_portal_payload_invalid",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": uploaded_count,
                "replaced_count": replaced_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": skipped_count,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
                "errors": [{"error": str(exc)}],
            }

        if _protected_snapshot(payload) != before_protected:
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "BLOCKED",
                "reason": "non_image_payload_change_detected",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": before_count,
                "uploaded_count": uploaded_count,
                "replaced_count": replaced_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": skipped_count,
                "removed_extra_count": 0,
                "product_update_performed": False,
                "write_blocked": True,
                "errors": [],
            }

        current_product_images = [_copy_product_image(row) for row in _product_images(product)]
        update_needed = current_product_images != desired_product_images or target_before != desired_ids
        if update_needed:
            try:
                self.vtex_client.update_seller_product(product_id, payload)
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
                    "replaced_count": replaced_count,
                    "asset_reused_count": reused_count,
                    "verified_count": 0,
                    "skipped_count": skipped_count,
                    "removed_extra_count": 0,
                    "product_update_performed": False,
                    "state": "ERROR",
                    "reason": self._error_reason(exc),
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
                "replaced_count": replaced_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": skipped_count,
                "removed_extra_count": 0,
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
            return {
                "found": True,
                "partnumber": normalized,
                "transport": "catalog_seller_portal",
                "state": "ERROR",
                "reason": "seller_portal_sku_not_found_after_update",
                "product_id": product_id,
                "remote_sku_id": sku_id,
                "sku_ref_id": sku_ref_id,
                "local_image_count": len(images),
                "remote_before_count": before_count,
                "remote_after_count": None,
                "uploaded_count": uploaded_count,
                "replaced_count": replaced_count,
                "asset_reused_count": reused_count,
                "verified_count": 0,
                "skipped_count": skipped_count,
                "removed_extra_count": 0,
                "product_update_performed": bool(update_needed),
                "write_blocked": True,
                "errors": [],
            }

        target_after_ids = _sku_images(target_after)
        product_after_assets = _product_asset_map(product_after)
        exact_readback = (
            [_normalize_key(value) for value in target_after_ids]
            == [_normalize_key(value) for value in desired_ids]
            and all(_normalize_key(value) in product_after_assets for value in desired_ids)
            and _protected_snapshot(product_after) == before_protected
        )

        verified_count = 0
        if exact_readback:
            for image, asset_id in zip(images, desired_ids):
                asset = product_after_assets.get(_normalize_key(asset_id))
                if asset is None:
                    continue
                self.publication_repository.mark_verified(
                    product_image_id=int(image["product_image_id"]),
                    partnumber=normalized,
                    channel="VTEX",
                    account_code=account,
                    remote_sku_id=sku_id,
                    remote_file_id=None,
                    remote_archive_id=None,
                    remote_url=str(asset.get("url") or "") or None,
                    position=int(image["position"]),
                    is_main=int(image["position"]) == 1,
                )
                verified_count += 1

        remote_after = _seller_remote_files(product_after, target_after)
        state = "SYNCED" if exact_readback and verified_count == len(images) else "ERROR"
        detail = {
            "transport": "catalog_seller_portal",
            "product_id": product_id,
            "remote_sku_id": sku_id,
            "sku_ref_id": sku_ref_id,
            "local_image_count": len(images),
            "remote_before_count": before_count,
            "remote_after_count": len(target_after_ids),
            "remote_files": remote_after,
            "remote_main_file": remote_after[0] if remote_after else None,
            "uploaded_count": uploaded_count,
            "replaced_count": replaced_count,
            "asset_reused_count": reused_count,
            "verified_count": verified_count,
            "skipped_count": skipped_count,
            "removed_extra_count": removed_extra_count if update_needed else 0,
            "product_update_performed": bool(update_needed),
            "state": state,
            "reason": None if state == "SYNCED" else "seller_portal_readback_mismatch",
            "write_blocked": state != "SYNCED",
            "errors": [],
        }
        self._audit(partnumber=normalized, detail=detail)
        return {"found": True, "partnumber": normalized, **detail}
