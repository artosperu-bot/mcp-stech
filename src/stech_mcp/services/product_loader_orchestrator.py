from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from stech_mcp.domain.product_loader_models import TERMINAL_ITEM_STATES


class ProductLoaderOrchestrator:
    """Persistent, item-isolated Product Loader orchestration for Product Workbench."""

    def __init__(
        self,
        *,
        repository: Any,
        prepare_service: Any,
        local_image_sync_service: Any,
        vtex_ensure_service: Any,
        vtex_image_sync_service: Any,
        default_account_code: str = "VTEX_STECH",
    ) -> None:
        self.repository = repository
        self.prepare_service = prepare_service
        self.local_image_sync_service = local_image_sync_service
        self.vtex_ensure_service = vtex_ensure_service
        self.vtex_image_sync_service = vtex_image_sync_service
        self.default_account_code = str(default_account_code or "VTEX_STECH").strip().upper()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return str(exc or type(exc).__name__)[:1800]

    def _transition(
        self,
        item: dict[str, Any],
        status: str,
        *,
        current_step: str | None = None,
        product_id_vtex: int | None = None,
        sku_id_vtex: int | None = None,
        product_ref_id_vtex: str | None = None,
        sku_ref_id_vtex: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        completed: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        updated = self.repository.update_item(
            int(item["item_id"]),
            status=status,
            current_step=current_step or status,
            product_id_vtex=product_id_vtex,
            sku_id_vtex=sku_id_vtex,
            product_ref_id_vtex=product_ref_id_vtex,
            sku_ref_id_vtex=sku_ref_id_vtex,
            last_error_code=error_code,
            last_error_detail=error_detail,
            completed=completed,
        )
        self.repository.append_event(
            job_id=int(item["product_loader_job_id"]),
            item_id=int(item["item_id"]),
            partnumber=str(item.get("partnumber") or ""),
            event_type=f"ITEM_{status}",
            status=status,
            detail=detail or {},
            actor_source="MCP",
        )
        return updated

    def _process_item(self, item_id: int) -> None:
        item = self.repository.get_item(int(item_id))
        if item is None:
            return
        if str(item.get("status") or "").upper() == "COMPLETED":
            return
        if not self.repository.claim_item(int(item_id), {"PENDING"}):
            return

        try:
            item = self._transition(item, "VALIDATING")
            row = dict(item.get("input") or {})
            partnumber = str(item.get("partnumber") or row.get("partnumber") or "").strip().upper()
            if not partnumber:
                self._transition(
                    item,
                    "BLOCKED",
                    error_code="PARTNUMBER_REQUIRED",
                    error_detail="Part Number requerido",
                    completed=True,
                )
                return

            item = self._transition(item, "PREPARING")
            prepared = self.prepare_service.prepare(
                partnumber,
                category=str(row.get("category") or row.get("category_code") or "LAPTOP").strip().upper(),
            )
            if not prepared or not prepared.get("found"):
                self._transition(
                    item,
                    "BLOCKED",
                    error_code="SOURCE_PRODUCT_NOT_FOUND",
                    error_detail="El Part Number no existe en la fuente de producto V8",
                    completed=True,
                )
                return
            master = dict(prepared.get("product_master") or {})

            item = self._transition(item, "IMAGES_LOCAL")
            local_images = self.local_image_sync_service.sync(partnumber)
            if str(local_images.get("state") or "").upper() != "READY":
                self._transition(
                    item,
                    "RESEARCH_REQUIRED",
                    error_code="IMAGES_NOT_READY",
                    error_detail=str(local_images.get("reason") or "no_local_images")[:1800],
                    completed=True,
                    detail={
                        "image_state": local_images.get("state"),
                        "image_count": local_images.get("image_count"),
                        "reason": local_images.get("reason"),
                    },
                )
                return

            item = self._transition(item, "VTEX_CHECK")
            ensure = self.vtex_ensure_service.ensure(
                partnumber,
                master,
                category_id=row.get("vtex_category_id") or 0,
                brand_id=row.get("vtex_brand_id") or 0,
            )
            ensure_status = str(ensure.get("status") or "").upper()
            if ensure_status == "REVIEW_REQUIRED":
                self._transition(
                    item,
                    "REVIEW_REQUIRED",
                    error_code="VTEX_DATA_REQUIRED",
                    error_detail=", ".join(ensure.get("blocking_reasons") or [])[:1800],
                    completed=True,
                    detail={"ensure": ensure},
                )
                return
            if ensure_status == "VERIFY_FAILED":
                self._transition(
                    item,
                    "BLOCKED",
                    error_code="VTEX_IDENTITY_VERIFY_FAILED",
                    error_detail=", ".join(ensure.get("blocking_reasons") or [])[:1800],
                    completed=True,
                    detail={"ensure": ensure},
                )
                return
            if ensure_status not in {"EXISTS", "CREATED"} or not ensure.get("read_back_verified"):
                self._transition(
                    item,
                    "BLOCKED",
                    error_code="VTEX_ENSURE_INCOMPLETE",
                    error_detail=f"Estado VTEX inesperado: {ensure_status or 'EMPTY'}",
                    completed=True,
                    detail={"ensure": ensure},
                )
                return

            item = self._transition(
                item,
                "VTEX_IMAGES",
                product_id_vtex=ensure.get("product_id"),
                sku_id_vtex=ensure.get("sku_id"),
                product_ref_id_vtex=ensure.get("product_ref_id"),
                sku_ref_id_vtex=ensure.get("sku_ref_id"),
                detail={
                    "product_created": bool(ensure.get("product_created")),
                    "sku_created": bool(ensure.get("sku_created")),
                },
            )
            account_code = str(row.get("vtex_account_code") or self.default_account_code).strip().upper()
            image_sync = self.vtex_image_sync_service.sync(partnumber, account_code=account_code)
            image_state = str(image_sync.get("state") or "").upper()
            if image_state != "SYNCED":
                terminal = "BLOCKED" if image_state in {"BLOCKED", "REVIEW", "NO_IMAGES"} else "FAILED"
                self._transition(
                    item,
                    terminal,
                    error_code="VTEX_IMAGES_NOT_SYNCED",
                    error_detail=str(image_sync.get("reason") or image_state or "unknown")[:1800],
                    completed=True,
                    detail={"image_sync": image_sync},
                )
                return

            item = self._transition(item, "VERIFYING", detail={"image_sync": image_sync})
            self._transition(
                item,
                "COMPLETED",
                completed=True,
                detail={
                    "ready": True,
                    "product_id": ensure.get("product_id"),
                    "sku_id": ensure.get("sku_id"),
                    "images_state": image_state,
                    "activation_changed": False,
                    "price_changed": False,
                    "stock_changed": False,
                },
            )
        except Exception as exc:
            latest = self.repository.get_item(int(item_id)) or item
            try:
                self._transition(
                    latest,
                    "FAILED",
                    error_code=type(exc).__name__[:80],
                    error_detail=self._safe_error(exc),
                    completed=True,
                )
            except Exception:
                # The original exception remains isolated to this item; the next
                # item in the job must still be attempted.
                pass

    def _finish_job(self, job_id: int) -> str:
        self.repository.refresh_job_summary(int(job_id))
        job = self.repository.get_job(int(job_id)) or {"items": []}
        states = [str(item.get("status") or "").upper() for item in job.get("items") or []]
        if states and all(state == "COMPLETED" for state in states):
            final = "COMPLETED"
        elif any(state in {"RESEARCH_REQUIRED", "REVIEW_REQUIRED"} for state in states):
            final = "WAITING_REVIEW"
        elif states and all(state in {"FAILED", "BLOCKED"} for state in states):
            final = "FAILED"
        elif all(state in TERMINAL_ITEM_STATES for state in states):
            final = "PARTIAL"
        else:
            final = "RUNNING"
        self.repository.set_job_status(int(job_id), final)
        return final

    def _run_job(self, job_id: int, item_ids: list[int]) -> None:
        self.repository.set_job_status(int(job_id), "RUNNING")
        for item_id in item_ids:
            self._process_item(int(item_id))
        self._finish_job(int(job_id))

    def start(
        self,
        rows: list[dict[str, Any]],
        source_name: str,
        actor_source: str = "SCR_UI",
        channel: str = "VTEX",
        *,
        background: bool = True,
    ) -> dict[str, Any]:
        job = self.repository.create_job(
            source_name=source_name,
            rows=rows,
            actor_source=actor_source,
            channel=channel,
        )
        job_id = int(job["job_id"])
        item_ids = [int(item["item_id"]) for item in job.get("items") or []]
        if background:
            self.repository.set_job_status(job_id, "RUNNING")
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id, item_ids),
                name=f"product-loader-{job_id}",
                daemon=True,
            )
            thread.start()
            return self.repository.get_job(job_id) or job
        self._run_job(job_id, item_ids)
        return self.repository.get_job(job_id) or job

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        return self.repository.get_job(int(job_id))

    def retry_item(self, job_id: int, item_id: int, *, background: bool = True) -> dict[str, Any]:
        item = self.repository.get_item(int(item_id))
        if item is None or int(item.get("product_loader_job_id") or 0) != int(job_id):
            raise ValueError("job item not found")
        self.repository.reset_item_for_retry(int(item_id))
        self.repository.set_job_status(int(job_id), "RUNNING")
        if background:
            thread = threading.Thread(
                target=self._retry_worker,
                args=(int(job_id), int(item_id)),
                name=f"product-loader-retry-{item_id}",
                daemon=True,
            )
            thread.start()
        else:
            self._retry_worker(int(job_id), int(item_id))
        return self.repository.get_job(int(job_id)) or {"job_id": int(job_id), "status": "RUNNING"}

    def _retry_worker(self, job_id: int, item_id: int) -> None:
        self._process_item(int(item_id))
        self._finish_job(int(job_id))

    def resume_pending(self) -> int:
        rows = list(self.repository.list_resumable_items() or [])
        if not rows:
            return 0
        by_job: dict[int, list[int]] = defaultdict(list)
        for item in rows:
            item_id = int(item.get("item_id") or item.get("product_loader_job_item_id"))
            job_id = int(item["product_loader_job_id"])
            if str(item.get("status") or "").upper() != "PENDING":
                self.repository.reset_item_for_retry(item_id)
            by_job[job_id].append(item_id)
        for job_id, item_ids in by_job.items():
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id, item_ids),
                name=f"product-loader-resume-{job_id}",
                daemon=True,
            )
            thread.start()
        return len(rows)
