from types import SimpleNamespace

from stech_mcp.services.budgeted_worker_factory import (
    allowed_types_for_worker,
    effective_background_worker_count,
)
from stech_mcp.services.work_type_limited_repository import WorkTypeLimitedRepository
from stech_mcp.worker import ProductWorkWorker


class Repo:
    def __init__(self):
        self.claim_args = None

    def claim_next(self, worker_id, lease_seconds, allowed_work_types=None):
        self.claim_args = (worker_id, lease_seconds, tuple(allowed_work_types or ()))
        return None


class Dispatcher:
    pass


def test_limited_repository_passes_allowed_work_types_to_claim():
    inner = Repo()
    limited = WorkTypeLimitedRepository(inner, ("RESEARCH_IMAGES",))
    worker = ProductWorkWorker(limited, Dispatcher(), worker_id="img-1")
    assert worker.run_once() is False
    assert inner.claim_args[2] == ("RESEARCH_IMAGES",)


def test_unrestricted_worker_keeps_legacy_claim_signature():
    class LegacyRepo:
        def __init__(self): self.called = False
        def claim_next(self, worker_id, lease_seconds):
            self.called = True
            return None
    repo = LegacyRepo()
    worker = ProductWorkWorker(repo, Dispatcher(), worker_id="legacy")
    assert worker.run_once() is False
    assert repo.called is True


def test_default_budget_assigns_two_technical_and_one_image_worker():
    cfg = SimpleNamespace(max_workers=3, max_research_jobs=2, max_image_jobs=1)
    assert effective_background_worker_count(cfg) == 3
    assert allowed_types_for_worker(1, cfg) == ("ENRICH_TECHNICAL",)
    assert allowed_types_for_worker(2, cfg) == ("ENRICH_TECHNICAL",)
    assert allowed_types_for_worker(3, cfg) == ("RESEARCH_IMAGES",)


def test_single_worker_remains_general_but_total_concurrency_is_one():
    cfg = SimpleNamespace(max_workers=1, max_research_jobs=2, max_image_jobs=1)
    assert effective_background_worker_count(cfg) == 1
    assert allowed_types_for_worker(1, cfg) is None
