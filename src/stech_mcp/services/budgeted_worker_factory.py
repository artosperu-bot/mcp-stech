from __future__ import annotations

from typing import Any

from stech_mcp.services.work_type_limited_repository import WorkTypeLimitedRepository
from stech_mcp.worker import build_worker_from_environment


def effective_background_worker_count(config: Any) -> int:
    total_budget = max(int(config.max_research_jobs), 0) + max(int(config.max_image_jobs), 0)
    return max(1, min(int(config.max_workers), total_budget or 1))


def allowed_types_for_worker(index: int, config: Any) -> tuple[str, ...] | None:
    total = effective_background_worker_count(config)
    if total <= 1:
        # One worker cannot violate either per-type concurrency budget.
        return None

    image_slots = min(max(int(config.max_image_jobs), 0), total)
    research_slots = min(max(int(config.max_research_jobs), 0), total - image_slots)
    position = max(int(index), 1)
    if position <= research_slots:
        return ("ENRICH_TECHNICAL",)
    if position <= research_slots + image_slots:
        return ("RESEARCH_IMAGES",)
    return None


def build_budgeted_background_worker(index: int, config: Any):
    worker = build_worker_from_environment(worker_suffix=f"bg{int(index)}")
    allowed = allowed_types_for_worker(index, config)
    if allowed:
        worker.repository = WorkTypeLimitedRepository(worker.repository, allowed)
    return worker
