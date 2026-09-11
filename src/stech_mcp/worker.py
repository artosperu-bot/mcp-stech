from __future__ import annotations

import os
import signal
import socket
import threading
import time
from typing import Any, Callable

from stech_mcp.config import Settings
from stech_mcp.db.connection import make_mcp_connection_factory, make_source_connection_factory
from stech_mcp.db.deltron_image_repository import DeltronImageRepository
from stech_mcp.db.enrichment_repository import EnrichmentRepository
from stech_mcp.db.fact_candidate_repository import FactCandidateRepository
from stech_mcp.db.product_image_candidate_repository import ProductImageCandidateRepository
from stech_mcp.db.product_image_repository import ProductImageRepository
from stech_mcp.db.product_master_repository import ProductMasterRepository
from stech_mcp.db.product_repository import ProductRepository
from stech_mcp.db.product_schema_repository import ProductSchemaRepository
from stech_mcp.db.product_work_execution_repository import ProductWorkExecutionRepository
from stech_mcp.db.source_document_repository import SourceDocumentRepository
from stech_mcp.services.deltron_fact_adapter import DeltronFactAdapter
from stech_mcp.services.fact_extractor import FactExtractor
from stech_mcp.services.fact_promotion import FactPromotionService
from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler
from stech_mcp.services.handlers.research_images import ResearchImagesHandler
from stech_mcp.services.local_image_sync import LocalImageSyncService
from stech_mcp.services.product_enrichment_engine import ProductEnrichmentEngine
from stech_mcp.services.product_field_verification import ProductFieldVerificationService
from stech_mcp.services.product_image_readiness import ProductImageReadinessService
from stech_mcp.services.product_image_research import ProductImageResearchService
from stech_mcp.services.product_technical_status import ProductTechnicalStatusService
from stech_mcp.services.product_work_dispatcher import (
    PermanentWorkError,
    ProductWorkDispatcher,
    RetryableWorkError,
    UnsupportedWorkTypeError,
)
from stech_mcp.services.research.brave_image_search_provider import BraveImageSearchProvider
from stech_mcp.services.research.brave_search_provider import BraveSearchProvider
from stech_mcp.services.research.research_planner import ResearchPlanner
from stech_mcp.services.source_document_service import SourceDocumentService


_TERMINAL_RESULTS = {
    "COMPLETED",
    "PARTIAL",
    "REVIEW_REQUIRED",
    "NO_DATA_FOUND",
    "FAILED",
    "CANCELLED",
}


def retry_delay_seconds(failed_attempt_count: int) -> int:
    attempt = max(int(failed_attempt_count), 1)
    return min(60 * (2 ** (attempt - 1)), 3600)


def worker_enabled() -> bool:
    return os.getenv("STECH_WORKER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _search_language() -> str:
    return os.getenv("STECH_SEARCH_LANGUAGE", os.getenv("STECH_SEARCH_LANG", "es"))


class ProductWorkWorker:
    def __init__(
        self,
        repository: Any,
        dispatcher: ProductWorkDispatcher,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        poll_seconds: float = 5.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.dispatcher = dispatcher
        self.worker_id = str(worker_id or "worker").strip()
        self.lease_seconds = max(int(lease_seconds), 30)
        self.poll_seconds = max(float(poll_seconds), 0.1)
        self.sleep_fn = sleep_fn

    @staticmethod
    def _item_id(item: dict[str, Any]) -> int:
        return int(item.get("item_id") or item.get("product_work_item_id"))

    @staticmethod
    def _job_id(item: dict[str, Any]) -> int:
        return int(item.get("job_id") or item.get("product_work_job_id"))

    def _record_event(
        self,
        item: dict[str, Any],
        event_type: str,
        *,
        status: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        recorder = getattr(self.repository, "record_event", None)
        if callable(recorder):
            recorder(item, event_type, status=status, detail=detail)

    def _record_attempt_start(self, item: dict[str, Any]) -> dict[str, Any] | None:
        recorder = getattr(self.repository, "record_attempt_start", None)
        if callable(recorder):
            return recorder(item, self.worker_id)
        return None

    def _record_attempt_end(
        self,
        attempt: dict[str, Any] | None,
        *,
        outcome_status: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        if not attempt:
            return
        recorder = getattr(self.repository, "record_attempt_end", None)
        if callable(recorder):
            recorder(
                int(attempt["attempt_id"]),
                outcome_status=outcome_status,
                error_code=error_code,
                error_detail=error_detail,
            )

    def _refresh_summary(self, item: dict[str, Any]) -> None:
        refresher = getattr(self.repository, "refresh_job_summary", None)
        if callable(refresher):
            refresher(self._job_id(item))

    def run_once(self) -> bool:
        item = self.repository.claim_next(self.worker_id, self.lease_seconds)
        if item is None:
            return False

        item_id = self._item_id(item)
        attempt = self._record_attempt_start(item)
        if attempt is not None:
            item["attempt_count"] = int(attempt["attempt_number"])
        self._record_event(
            item,
            "CLAIMED",
            status=str(item.get("status") or "QUEUED"),
            detail={"attempt_number": item.get("attempt_count")},
        )
        current_status = str(item.get("status") or "QUEUED").strip().upper()

        try:
            if current_status == "FAILED_RETRYABLE":
                item = self.repository.transition_item(
                    item_id,
                    status="QUEUED",
                    current_step="retry claimed",
                    progress_pct=0,
                )
                current_status = "QUEUED"

            item = self.repository.transition_item(
                item_id,
                status="LOADING_SOURCE_DATA",
                current_step="loading source data",
                progress_pct=1,
            )
            current_status = "LOADING_SOURCE_DATA"

            def progress(state: str, percent: int) -> None:
                nonlocal item, current_status
                target = str(state or "").strip().upper()
                pct = max(0, min(int(percent), 100))
                if not self.repository.renew_claim(item_id, self.worker_id, self.lease_seconds):
                    raise RetryableWorkError("LEASE_LOST", "worker lease could not be renewed")
                if target and target != current_status:
                    item = self.repository.transition_item(
                        item_id,
                        status=target,
                        current_step=target.lower().replace("_", " "),
                        progress_pct=pct,
                    )
                    current_status = target
                self._record_event(item, "PROGRESS", status=current_status, detail={"progress_pct": pct})

            result = self.dispatcher.dispatch(item, progress)
            target = str(result.get("status") or "").strip().upper()
            if target not in _TERMINAL_RESULTS:
                raise PermanentWorkError("INVALID_HANDLER_STATUS", f"unsupported handler status: {target}")

            error_code = result.get("error_code")
            error_detail = result.get("error_detail")
            final_progress = 100 if target == "COMPLETED" else None
            item = self.repository.transition_item(
                item_id,
                status=target,
                current_step=str(result.get("current_step") or target.lower().replace("_", " ")),
                progress_pct=final_progress,
                error_code=str(error_code) if error_code else None,
                error_detail=str(error_detail) if error_detail else None,
            )
            self._record_attempt_end(
                attempt,
                outcome_status=target,
                error_code=str(error_code) if error_code else None,
                error_detail=str(error_detail) if error_detail else None,
            )
            self._record_event(item, "FINISHED", status=target, detail={"result": target})
            self._refresh_summary(item)
            return True

        except RetryableWorkError as exc:
            attempt_number = int((attempt or {}).get("attempt_number") or item.get("attempt_count") or 1)
            delay = retry_delay_seconds(attempt_number)
            item = self.repository.schedule_retry(
                item_id,
                error_code=exc.code,
                error_detail=exc.detail,
                delay_seconds=delay,
            )
            outcome = str(item.get("status") or "FAILED_RETRYABLE").strip().upper()
            self._record_attempt_end(
                attempt,
                outcome_status=outcome,
                error_code=exc.code,
                error_detail=exc.detail,
            )
            if outcome == "FAILED":
                self._record_event(
                    item,
                    "FAILED",
                    status="FAILED",
                    detail={"error_code": exc.code, "reason": "MAX_ATTEMPTS_REACHED"},
                )
            else:
                self._record_event(
                    item,
                    "RETRY_SCHEDULED",
                    status="FAILED_RETRYABLE",
                    detail={"delay_seconds": delay, "attempt_number": attempt_number},
                )
            self._refresh_summary(item)
            return True

        except (UnsupportedWorkTypeError, PermanentWorkError) as exc:
            item = self.repository.transition_item(
                item_id,
                status="FAILED",
                current_step="failed",
                error_code=exc.code,
                error_detail=exc.detail,
            )
            self._record_attempt_end(
                attempt,
                outcome_status="FAILED",
                error_code=exc.code,
                error_detail=exc.detail,
            )
            self._record_event(item, "FAILED", status="FAILED", detail={"error_code": exc.code})
            self._refresh_summary(item)
            return True

        except Exception as exc:
            code = "UNHANDLED_WORK_ERROR"
            detail = f"{type(exc).__name__}: {exc}"
            item = self.repository.transition_item(
                item_id,
                status="FAILED",
                current_step="failed",
                error_code=code,
                error_detail=detail,
            )
            self._record_attempt_end(attempt, outcome_status="FAILED", error_code=code, error_detail=detail)
            self._record_event(item, "FAILED", status="FAILED", detail={"error_code": code})
            self._refresh_summary(item)
            return True

    def run_forever(self, stop_event: Any) -> None:
        self.repository.release_expired_claims()
        while not stop_event.is_set():
            did_work = self.run_once()
            if not did_work:
                self.sleep_fn(self.poll_seconds)


def build_worker_from_environment(worker_suffix: str | None = None) -> ProductWorkWorker:
    concurrency = int(os.getenv("STECH_WORKER_CONCURRENCY", "1"))
    if concurrency != 1:
        raise ValueError("Each Product Work V2 worker supports STECH_WORKER_CONCURRENCY=1 only")

    settings = Settings()
    mcp_connection_factory = make_mcp_connection_factory(settings)
    source_connection_factory = make_source_connection_factory(settings)

    repository = ProductWorkExecutionRepository(mcp_connection_factory)
    product_repository = ProductRepository(source_connection_factory)
    enrichment_repository = EnrichmentRepository(mcp_connection_factory)
    schema_repository = ProductSchemaRepository(mcp_connection_factory)
    candidate_repository = FactCandidateRepository(mcp_connection_factory)
    image_candidate_repository = ProductImageCandidateRepository(mcp_connection_factory)
    source_document_repository = SourceDocumentRepository(mcp_connection_factory)
    audit_repository = ProductMasterRepository(mcp_connection_factory)
    deltron_image_repository = DeltronImageRepository(source_connection_factory)
    product_image_repository = ProductImageRepository(mcp_connection_factory)
    local_image_sync_service = LocalImageSyncService(
        root=settings.stech_image_root,
        repository=product_image_repository,
    )

    technical_status_service = ProductTechnicalStatusService(
        product_repository=product_repository,
        enrichment_repository=enrichment_repository,
        schema_repository=schema_repository,
    )
    verification_service = ProductFieldVerificationService(enrichment_repository)
    promotion_service = FactPromotionService(
        verification_service=verification_service,
        enrichment_repository=enrichment_repository,
        candidate_repository=candidate_repository,
    )
    search_provider = BraveSearchProvider(
        api_key=os.getenv("STECH_BRAVE_SEARCH_API_KEY", ""),
        country=os.getenv("STECH_SEARCH_COUNTRY", "PE"),
        search_lang=_search_language(),
    )
    source_document_service = SourceDocumentService(
        document_repository=source_document_repository,
    )
    enrichment_engine = ProductEnrichmentEngine(
        product_repository=product_repository,
        technical_status_service=technical_status_service,
        deltron_adapter=DeltronFactAdapter(),
        candidate_repository=candidate_repository,
        promotion_service=promotion_service,
        research_planner=ResearchPlanner(),
        search_provider=search_provider,
        source_document_service=source_document_service,
        fact_extractor=FactExtractor(),
        audit_repository=audit_repository,
    )
    enrichment_handler = EnrichTechnicalHandler(enrichment_engine)

    image_readiness_service = ProductImageReadinessService(
        product_repository=product_repository,
        source_image_repository=deltron_image_repository,
        workspace_image_repository=product_image_repository,
        policy_repository=image_candidate_repository,
    )
    image_search_provider = BraveImageSearchProvider(
        api_key=os.getenv("STECH_BRAVE_SEARCH_API_KEY", ""),
        country=os.getenv("STECH_SEARCH_COUNTRY", "PE"),
        search_lang=_search_language(),
    )
    image_research_service = ProductImageResearchService(
        product_repository=product_repository,
        local_image_sync_service=local_image_sync_service,
        readiness_service=image_readiness_service,
        candidate_repository=image_candidate_repository,
        search_provider=image_search_provider,
    )
    image_handler = ResearchImagesHandler(image_research_service)

    dispatcher = ProductWorkDispatcher()
    dispatcher.register("ENRICH_TECHNICAL", enrichment_handler)
    dispatcher.register("RESEARCH_IMAGES", image_handler)
    suffix = str(worker_suffix or "").strip()
    worker_id = f"{socket.gethostname()}:{os.getpid()}" + (f":{suffix}" if suffix else "")
    return ProductWorkWorker(
        repository,
        dispatcher,
        worker_id=worker_id,
        lease_seconds=int(os.getenv("STECH_WORKER_LEASE_SECONDS", "300")),
        poll_seconds=float(os.getenv("STECH_WORKER_POLL_SECONDS", "5")),
    )


def main() -> None:
    if not worker_enabled():
        return

    worker = build_worker_from_environment()
    stop_event = threading.Event()

    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_stop)
        except (ValueError, OSError):
            pass

    worker.run_forever(stop_event)


if __name__ == "__main__":
    main()
