from __future__ import annotations

import pytest

from stech_mcp.domain.product_work_models import ITEM_STATES, TERMINAL_ITEM_STATES, can_transition
from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler
from stech_mcp.services.handlers.research_images import ResearchImagesHandler
from stech_mcp.services.product_work_dispatcher import ProductWorkDispatcher
from stech_mcp.services.research.brave_image_search_provider import BraveImageSearchProvider
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured
from stech_mcp.worker import ProductWorkWorker


class ImageServiceNotConfigured:
    def research(self, partnumber, category_code=None, target_count=None):
        raise SearchProviderNotConfigured("image search provider is not configured")


class TechnicalEngineNeedsExternalResearch:
    def __init__(self):
        self.calls = []

    def enrich(self, partnumber, category_code, requested_fields, progress):
        self.calls.append((partnumber, category_code, requested_fields))
        return {
            "state": "PARTIAL",
            "remaining_fields": ["ip_rating"],
            "conflicts": [],
            "error_code": "SEARCH_PROVIDER_NOT_CONFIGURED",
        }


class WorkerRepository:
    def __init__(self):
        self.item = {
            "item_id": 1,
            "job_id": 9,
            "work_type": "RESEARCH_IMAGES",
            "partnumber": "PN1",
            "status": "QUEUED",
            "attempt_count": 0,
            "max_attempts": 3,
        }
        self.claimed = False
        self.attempt_ends = []

    def claim_next(self, worker_id, lease_seconds):
        if self.claimed:
            return None
        self.claimed = True
        self.item["claimed_by"] = worker_id
        return dict(self.item)

    def transition_item(self, item_id, *, status, current_step=None, progress_pct=None, error_code=None, error_detail=None):
        assert item_id == 1
        self.item["status"] = status
        self.item["current_step"] = current_step
        self.item["last_error_code"] = error_code
        self.item["last_error_detail"] = error_detail
        if progress_pct is not None:
            self.item["progress_pct"] = progress_pct
        if status == "WAITING_EXTERNAL_RESEARCH":
            self.item["claimed_by"] = None
        return dict(self.item)

    def renew_claim(self, item_id, worker_id, lease_seconds):
        return True

    def record_attempt_start(self, item, worker_id):
        self.item["attempt_count"] += 1
        return {"attempt_id": 1, "attempt_number": 1}

    def record_attempt_end(self, attempt_id, *, outcome_status, error_code=None, error_detail=None):
        self.attempt_ends.append((attempt_id, outcome_status, error_code, error_detail))

    def record_event(self, item, event_type, *, status=None, detail=None):
        pass

    def refresh_job_summary(self, job_id):
        return {"job_id": job_id}


def test_waiting_external_research_is_active_product_work_state():
    assert "WAITING_EXTERNAL_RESEARCH" in ITEM_STATES
    assert "WAITING_EXTERNAL_RESEARCH" not in TERMINAL_ITEM_STATES
    assert can_transition("RESEARCHING", "WAITING_EXTERNAL_RESEARCH") is True
    assert can_transition("WAITING_EXTERNAL_RESEARCH", "REVIEW_REQUIRED") is True
    assert can_transition("WAITING_EXTERNAL_RESEARCH", "NO_DATA_FOUND") is True
    assert can_transition("WAITING_EXTERNAL_RESEARCH", "FAILED_RETRYABLE") is True


def test_image_provider_without_key_raises_explicit_not_configured():
    provider = BraveImageSearchProvider(api_key="")
    with pytest.raises(SearchProviderNotConfigured):
        provider.search("PN1")


def test_image_handler_hands_off_when_external_bridge_enabled():
    handler = ResearchImagesHandler(
        ImageServiceNotConfigured(),
        external_research_enabled=True,
    )

    result = handler({"partnumber": "PN1", "input": {}}, lambda *_: None)

    assert result["status"] == "WAITING_EXTERNAL_RESEARCH"
    assert result["error_code"] == "EXTERNAL_RESEARCH_REQUIRED"


def test_technical_handler_hands_off_unconfigured_search_when_bridge_enabled():
    handler = EnrichTechnicalHandler(
        TechnicalEngineNeedsExternalResearch(),
        external_research_enabled=True,
    )

    result = handler({"partnumber": "PN1", "input": {}}, lambda *_: None)

    assert result["status"] == "WAITING_EXTERNAL_RESEARCH"
    assert result["error_code"] == "EXTERNAL_RESEARCH_REQUIRED"


def test_worker_accepts_handoff_as_nonterminal_outcome_and_releases_claim():
    repo = WorkerRepository()
    dispatcher = ProductWorkDispatcher()

    def handler(item, progress):
        progress("RESEARCHING", 30)
        return {
            "status": "WAITING_EXTERNAL_RESEARCH",
            "current_step": "waiting external research",
            "error_code": "EXTERNAL_RESEARCH_REQUIRED",
        }

    dispatcher.register("RESEARCH_IMAGES", handler)
    worker = ProductWorkWorker(repo, dispatcher, worker_id="worker-a", lease_seconds=120)

    assert worker.run_once() is True
    assert repo.item["status"] == "WAITING_EXTERNAL_RESEARCH"
    assert repo.item["claimed_by"] is None
    assert repo.attempt_ends[-1][1] == "WAITING_EXTERNAL_RESEARCH"
