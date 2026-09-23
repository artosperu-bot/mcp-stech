from __future__ import annotations

JOB_STATES = {
    "PENDING",
    "RUNNING",
    "WAITING_REVIEW",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
}

ITEM_STATES = {
    "PENDING",
    "VALIDATING",
    "PREPARING",
    "IMAGES_LOCAL",
    "RESEARCH_REQUIRED",
    "VTEX_CHECK",
    "VTEX_CREATE_PRODUCT",
    "VTEX_CREATE_SKU",
    "VTEX_IMAGES",
    "VERIFYING",
    "COMPLETED",
    "REVIEW_REQUIRED",
    "BLOCKED",
    "FAILED",
}

TERMINAL_ITEM_STATES = {
    "COMPLETED",
    "RESEARCH_REQUIRED",
    "REVIEW_REQUIRED",
    "BLOCKED",
    "FAILED",
}


def normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()
