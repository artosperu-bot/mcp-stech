from __future__ import annotations

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
        return parsed
    return None


class VtexImageSyncService:
    """Synchronize approved local Product Workspace images into one VTEX SKU."""

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
            "verified_count": 0,
            "skipped_count": 0,
        }

    def status(self, partnumber: str, *, account_code: str = "VTEX_STECH") -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        local = self.local_service.validate(normalized)
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
        remote = self.vtex_client.list_sku_files(sku_id)
        publications = self.publication_repository.get_publications(
            partnumber=normalized,
            account_code=str(account_code or "VTEX_STECH").strip().upper(),
            remote_sku_id=sku_id,
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
        fully_synced = bool(local_image_ids) and local_image_ids <= verified_image_ids
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

        local_sync = self.local_service.sync(normalized)
        validation = self.local_service.validate(normalized)
        if validation.get("state") != "READY":
            return {
                "found": True,
                "partnumber": normalized,
                "state": validation.get("state") or local_sync.get("state") or "REVIEW",
                "reason": validation.get("reason") or local_sync.get("reason"),
                "local_image_count": int(validation.get("image_count") or 0),
                "uploaded_count": 0,
                "verified_count": 0,
                "skipped_count": 0,
            }
        if self.vtex_client is None:
            return self._configuration_error(normalized)

        images = sorted(
            [dict(row) for row in (validation.get("images") or [])],
            key=lambda row: (int(row.get("position") or 0), int(row.get("product_image_id") or 0)),
        )
        sku_ref_id = f"{normalized}-S"
        sku_id = int(self.vtex_client.resolve_sku_id(sku_ref_id))
        remote_before = list(self.vtex_client.list_sku_files(sku_id) or [])
        remote_by_name_before = {_remote_name(row): row for row in remote_before if _remote_name(row)}
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

        uploaded_count = 0
        skipped_count = 0
        errors: list[dict[str, Any]] = []

        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            is_main = position == 1
            file_name = Path(str(image.get("storage_path") or "")).name
            existing_publication = publication_by_image.get(image_id)
            if existing_publication and str(existing_publication.get("status") or "").upper() == "VERIFIED":
                skipped_count += 1
                continue

            remote_existing = remote_by_name_before.get(file_name.lower())
            if remote_existing is not None:
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
            payload = {
                "IsMain": is_main,
                "Label": "Main" if is_main else f"Image {position:02d}",
                "Name": file_name,
                "Url": signed_url,
            }
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
                errors.append({"product_image_id": image_id, "file": file_name, "error": str(exc)})
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

        # Always read back after the attempted synchronization, including a fully
        # idempotent run, so status reflects VTEX rather than only local history.
        remote_after = list(self.vtex_client.list_sku_files(sku_id) or [])
        remote_by_name_after = {_remote_name(row): row for row in remote_after if _remote_name(row)}
        verified_count = 0
        for image in images:
            image_id = int(image["product_image_id"])
            position = int(image["position"])
            is_main = position == 1
            file_name = Path(str(image.get("storage_path") or "")).name
            remote = remote_by_name_after.get(file_name.lower())
            if remote is not None:
                self.publication_repository.mark_verified(
                    product_image_id=image_id,
                    partnumber=normalized,
                    channel="VTEX",
                    account_code=account,
                    remote_sku_id=sku_id,
                    remote_file_id=_remote_id(remote, "Id", "id", "FileId", "fileId"),
                    remote_archive_id=_remote_id(remote, "ArchiveId", "archiveId"),
                    remote_url=str(remote.get("Url") or remote.get("url") or "") or None,
                    position=position,
                    is_main=is_main,
                )
                verified_count += 1
                continue
            existing = publication_by_image.get(image_id)
            if existing and str(existing.get("status") or "").upper() == "VERIFIED":
                # A prior verified publication can survive APIs that omit Name in
                # read-back; we still performed the required GET above.
                verified_count += 1

        state = "SYNCED" if verified_count == len(images) and not errors else ("PARTIAL" if verified_count else "ERROR")
        detail = {
            "remote_sku_id": sku_id,
            "sku_ref_id": sku_ref_id,
            "local_image_count": len(images),
            "remote_before_count": len(remote_before),
            "remote_after_count": len(remote_after),
            "uploaded_count": uploaded_count,
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
