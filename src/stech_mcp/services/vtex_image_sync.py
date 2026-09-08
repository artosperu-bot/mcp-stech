from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _remote_name(row: dict[str, Any]) -> str:
    return str(row.get("Name") or row.get("name") or "").strip().lower()


def _remote_id(row: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _remote_position(row: dict[str, Any], partnumber: str) -> int | None:
    name = str(row.get("Name") or row.get("name") or "").strip()
    if not name:
        return None
    match = re.match(
        rf"^{re.escape(partnumber)}_(?P<position>\d{{1,3}})\.(?:jpg|jpeg|png|gif)$",
        name,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    position = int(match.group("position"))
    return position if position > 0 else None


def _remote_maps(
    rows: list[dict[str, Any]],
    partnumber: str,
) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    by_id: dict[int, dict[str, Any]] = {}
    by_position: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        remote_file_id = _remote_id(row, "Id", "id", "FileId", "fileId")
        if remote_file_id is not None:
            by_id[remote_file_id] = row
        position = _remote_position(row, partnumber)
        if position is not None:
            by_position.setdefault(position, []).append(row)
    return by_id, by_position


def _payload(image: dict[str, Any], signed_url: str) -> dict[str, Any]:
    position = int(image["position"])
    is_main = position == 1
    return {
        "IsMain": is_main,
        "Label": "Main" if is_main else f"Image {position:02d}",
        "Name": Path(str(image.get("storage_path") or "")).name,
        "Url": signed_url,
    }


class VtexImageSyncService:
    """Synchronize local images into VTEX using exact Part Number + numeric position."""

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
        self.signer = signer
        self.audit_repository = audit_repository

    def _configuration_error(self, partnumber: str) -> dict[str, Any]:
        return {
            "found": True,
            "partnumber": partnumber,
            "state": "ERROR",
            "reason": "vtex_credentials_not_configured",
            "uploaded_count": 0,
            "replaced_count": 0,
            "verified_count": 0,
            "skipped_count": 0,
        }

    def status(self, partnumber: str, *, account_code: str = "VTEX_STECH") -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        local = self.local_service.sync(normalized)
        result: dict[str, Any] = {
            "found": True,
            "partnumber": normalized,
            "local_state": local.get("state"),
            "local_image_count": int(local.get("image_count") or 0),
            "remote_sku_id": None,
            "remote_image_count": None,
            "state": local.get("state"),
            "reason": local.get("reason"),
        }
        if local.get("state") != "READY":
            return result
        if self.vtex_client is None:
            result.update({"state": "ERROR", "reason": "vtex_credentials_not_configured"})
            return result
        sku_id = int(self.vtex_client.resolve_sku_id(f"{normalized}-S"))
        remote = list(self.vtex_client.list_sku_files(sku_id) or [])
        remote_by_id, _ = _remote_maps(remote, normalized)
        publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=str(account_code or "VTEX_STECH").strip().upper(),
                remote_sku_id=sku_id,
            )
            or []
        )
        local_image_ids = {
            int(row["product_image_id"])
            for row in (local.get("images") or [])
            if row.get("product_image_id") is not None
        }
        verified_image_ids = {
            int(row["product_image_id"])
            for row in publications
            if row.get("product_image_id") is not None
            and str(row.get("status") or "").upper() == "VERIFIED"
        }
        remote_verified_image_ids = {
            int(row["product_image_id"])
            for row in publications
            if row.get("product_image_id") is not None
            and str(row.get("status") or "").upper() == "VERIFIED"
            and _remote_id(row, "remote_file_id") in remote_by_id
        }
        fully_synced = bool(local_image_ids) and local_image_ids <= remote_verified_image_ids
        result.update(
            {
                "state": "SYNCED" if fully_synced else "READY",
                "reason": None,
                "remote_sku_id": sku_id,
                "remote_image_count": len(remote),
                "publication_count": len(publications),
                "verified_publication_count": len(verified_image_ids),
            }
        )
        return result

    def sync(self, partnumber: str, *, account_code: str = "VTEX_STECH") -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        account = str(account_code or "VTEX_STECH").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")

        validation = self.local_service.sync(normalized)
        if validation.get("state") != "READY":
            return {
                "found": True,
                "partnumber": normalized,
                "state": validation.get("state") or "REVIEW",
                "reason": validation.get("reason"),
                "local_image_count": int(validation.get("image_count") or 0),
                "uploaded_count": 0,
                "replaced_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
                "errors": list(validation.get("errors") or []),
            }
        if self.vtex_client is None:
            return self._configuration_error(normalized)

        images = sorted(
            [dict(row) for row in (validation.get("images") or [])],
            key=lambda row: (
                int(row.get("position") or 0),
                int(row.get("product_image_id") or 0),
            ),
        )
        sku_ref_id = f"{normalized}-S"
        sku_id = int(self.vtex_client.resolve_sku_id(sku_ref_id))
        remote_before = list(self.vtex_client.list_sku_files(sku_id) or [])
        remote_by_id_before, remote_by_position_before = _remote_maps(remote_before, normalized)
        publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=account,
                remote_sku_id=sku_id,
            )
            or []
        )
        publication_by_image = {
            int(row["product_image_id"]): row
            for row in publications
            if row.get("product_image_id") is not None
        }
        publications_by_position: dict[int, list[dict[str, Any]]] = {}
        for row in publications:
            try:
                position = int(row.get("position") or 0)
            except (TypeError, ValueError):
                position = 0
            if position > 0:
                publications_by_position.setdefault(position, []).append(row)

        uploaded_count = 0
        replaced_count = 0
        skipped_count = 0
        errors: list[dict[str, Any]] = []
        failed_replacement_ids: set[int] = set()

        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            is_main = position == 1
            file_name = Path(str(image.get("storage_path") or "")).name

            current_publication = publication_by_image.get(image_id)
            current_remote_id = (
                _remote_id(current_publication, "remote_file_id")
                if current_publication is not None
                else None
            )
            if current_remote_id is not None and current_remote_id in remote_by_id_before:
                remote_existing = remote_by_id_before[current_remote_id]
                self.publication_repository.mark_verified(
                    product_image_id=image_id,
                    partnumber=normalized,
                    channel="VTEX",
                    account_code=account,
                    remote_sku_id=sku_id,
                    remote_file_id=current_remote_id,
                    remote_archive_id=_remote_id(remote_existing, "ArchiveId", "archiveId"),
                    remote_url=str(remote_existing.get("Url") or remote_existing.get("url") or "") or None,
                    position=position,
                    is_main=is_main,
                )
                skipped_count += 1
                continue

            historical_target_ids = {
                remote_id
                for row in publications_by_position.get(position, [])
                if row.get("product_image_id") is not None
                and int(row["product_image_id"]) != image_id
                for remote_id in [_remote_id(row, "remote_file_id")]
                if remote_id is not None and remote_id in remote_by_id_before
            }
            if len(historical_target_ids) > 1:
                errors.append(
                    {
                        "product_image_id": image_id,
                        "position": position,
                        "file": file_name,
                        "operation": "replace",
                        "error": "publication_position_ambiguous",
                    }
                )
                failed_replacement_ids.add(image_id)
                continue

            if len(historical_target_ids) == 1:
                target_id = next(iter(historical_target_ids))
                target_remote = remote_by_id_before[target_id]
                signed_url = self.signer.sign(product_image_id=image_id, partnumber=normalized)
                payload = _payload(image, signed_url)
                try:
                    updated = dict(self.vtex_client.update_sku_file(sku_id, target_id, payload) or {})
                    self.publication_repository.upsert_publication(
                        product_image_id=image_id,
                        partnumber=normalized,
                        channel="VTEX",
                        account_code=account,
                        remote_sku_id=sku_id,
                        remote_file_id=_remote_id(updated, "Id", "id", "FileId", "fileId") or target_id,
                        remote_archive_id=(
                            _remote_id(updated, "ArchiveId", "archiveId")
                            or _remote_id(target_remote, "ArchiveId", "archiveId")
                        ),
                        remote_url=str(updated.get("Url") or updated.get("url") or signed_url),
                        position=position,
                        is_main=is_main,
                        status="UPLOADED",
                        last_error=None,
                    )
                    replaced_count += 1
                except Exception as exc:
                    failed_replacement_ids.add(image_id)
                    errors.append(
                        {
                            "product_image_id": image_id,
                            "position": position,
                            "file": file_name,
                            "operation": "replace",
                            "error": str(exc),
                        }
                    )
                    try:
                        self.publication_repository.upsert_publication(
                            product_image_id=image_id,
                            partnumber=normalized,
                            channel="VTEX",
                            account_code=account,
                            remote_sku_id=sku_id,
                            remote_file_id=None,
                            remote_archive_id=None,
                            remote_url=signed_url,
                            position=position,
                            is_main=is_main,
                            status="ERROR",
                            last_error=str(exc)[:4000],
                        )
                    except Exception:
                        pass
                continue

            remote_position_candidates = remote_by_position_before.get(position, [])
            if len(remote_position_candidates) > 1:
                errors.append(
                    {
                        "product_image_id": image_id,
                        "position": position,
                        "file": file_name,
                        "operation": "adopt",
                        "error": "remote_position_ambiguous",
                    }
                )
                continue
            if len(remote_position_candidates) == 1:
                remote_existing = remote_position_candidates[0]
                self.publication_repository.mark_verified(
                    product_image_id=image_id,
                    partnumber=normalized,
                    channel="VTEX",
                    account_code=account,
                    remote_sku_id=sku_id,
                    remote_file_id=_remote_id(remote_existing, "Id", "id", "FileId", "fileId"),
                    remote_archive_id=_remote_id(remote_existing, "ArchiveId", "archiveId"),
                    remote_url=str(remote_existing.get("Url") or remote_existing.get("url") or "") or None,
                    position=position,
                    is_main=is_main,
                )
                skipped_count += 1
                continue

            signed_url = self.signer.sign(product_image_id=image_id, partnumber=normalized)
            payload = _payload(image, signed_url)
            try:
                created = dict(self.vtex_client.create_sku_file(sku_id, payload) or {})
                self.publication_repository.upsert_publication(
                    product_image_id=image_id,
                    partnumber=normalized,
                    channel="VTEX",
                    account_code=account,
                    remote_sku_id=sku_id,
                    remote_file_id=_remote_id(created, "Id", "id", "FileId", "fileId"),
                    remote_archive_id=_remote_id(created, "ArchiveId", "archiveId"),
                    remote_url=str(created.get("Url") or created.get("url") or signed_url),
                    position=position,
                    is_main=is_main,
                    status="UPLOADED",
                    last_error=None,
                )
                uploaded_count += 1
            except Exception as exc:
                errors.append(
                    {
                        "product_image_id": image_id,
                        "position": position,
                        "file": file_name,
                        "operation": "create",
                        "error": str(exc),
                    }
                )
                try:
                    self.publication_repository.upsert_publication(
                        product_image_id=image_id,
                        partnumber=normalized,
                        channel="VTEX",
                        account_code=account,
                        remote_sku_id=sku_id,
                        remote_file_id=None,
                        remote_archive_id=None,
                        remote_url=signed_url,
                        position=position,
                        is_main=is_main,
                        status="ERROR",
                        last_error=str(exc)[:4000],
                    )
                except Exception:
                    pass

        remote_after = list(self.vtex_client.list_sku_files(sku_id) or [])
        remote_by_id_after, remote_by_position_after = _remote_maps(remote_after, normalized)
        fresh_publications = list(
            self.publication_repository.get_publications(
                partnumber=normalized,
                account_code=account,
                remote_sku_id=sku_id,
            )
            or []
        )
        fresh_by_image = {
            int(row["product_image_id"]): row
            for row in fresh_publications
            if row.get("product_image_id") is not None
        }

        verified_count = 0
        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            is_main = position == 1
            publication = fresh_by_image.get(image_id)
            remote_file_id = _remote_id(publication, "remote_file_id") if publication else None
            remote = remote_by_id_after.get(remote_file_id) if remote_file_id is not None else None

            if remote is None and image_id not in failed_replacement_ids:
                candidates = remote_by_position_after.get(position, [])
                if len(candidates) == 1:
                    remote = candidates[0]
                    remote_file_id = _remote_id(remote, "Id", "id", "FileId", "fileId")

            if remote is None or remote_file_id is None:
                continue

            self.publication_repository.mark_verified(
                product_image_id=image_id,
                partnumber=normalized,
                channel="VTEX",
                account_code=account,
                remote_sku_id=sku_id,
                remote_file_id=remote_file_id,
                remote_archive_id=_remote_id(remote, "ArchiveId", "archiveId"),
                remote_url=str(remote.get("Url") or remote.get("url") or "") or None,
                position=position,
                is_main=is_main,
            )
            verified_count += 1

        state = (
            "SYNCED"
            if verified_count == len(images) and not errors
            else ("PARTIAL" if verified_count else "ERROR")
        )
        detail = {
            "remote_sku_id": sku_id,
            "sku_ref_id": sku_ref_id,
            "local_image_count": len(images),
            "remote_before_count": len(remote_before),
            "remote_after_count": len(remote_after),
            "uploaded_count": uploaded_count,
            "replaced_count": replaced_count,
            "verified_count": verified_count,
            "skipped_count": skipped_count,
            "state": state,
            "errors": errors,
        }
        self.audit_repository.add_audit_event(
            partnumber=normalized,
            event_type="VTEX_IMAGES_SYNC",
            actor_source="STECH_MCP",
            channel="VTEX",
            detail=detail,
        )
        return {"found": True, "partnumber": normalized, **detail}
