from __future__ import annotations

import hashlib
import json


WORK_TYPES = {
    "ENRICH_TECHNICAL",
    "RESEARCH_IDENTITY",
    "RESEARCH_IMAGES",
    "PREPARE_CHANNEL",
    "PUBLISH_CHANNEL",
}

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
    "QUEUED",
    "LOADING_SOURCE_DATA",
    "ANALYZING_MISSING_FIELDS",
    "RESEARCHING",
    "READING_DOCUMENTS",
    "VALIDATING",
    "PROMOTING_FACTS",
    "REBUILDING_PRODUCT_MASTER",
    "COMPLETED",
    "PARTIAL",
    "REVIEW_REQUIRED",
    "NO_DATA_FOUND",
    "FAILED_RETRYABLE",
    "FAILED",
    "CANCELLED",
}

TERMINAL_ITEM_STATES = {
    "COMPLETED",
    "PARTIAL",
    "REVIEW_REQUIRED",
    "NO_DATA_FOUND",
    "FAILED",
    "CANCELLED",
}

_ACTIVE_FAILURE_TARGETS = {"FAILED_RETRYABLE", "FAILED", "CANCELLED"}

_TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"LOADING_SOURCE_DATA", *_ACTIVE_FAILURE_TARGETS},
    "LOADING_SOURCE_DATA": {"ANALYZING_MISSING_FIELDS", *_ACTIVE_FAILURE_TARGETS},
    "ANALYZING_MISSING_FIELDS": {
        "RESEARCHING",
        "VALIDATING",
        "REBUILDING_PRODUCT_MASTER",
        "COMPLETED",
        "PARTIAL",
        "REVIEW_REQUIRED",
        "NO_DATA_FOUND",
        *_ACTIVE_FAILURE_TARGETS,
    },
    "RESEARCHING": {"READING_DOCUMENTS", "VALIDATING", *_ACTIVE_FAILURE_TARGETS},
    "READING_DOCUMENTS": {"VALIDATING", "RESEARCHING", *_ACTIVE_FAILURE_TARGETS},
    "VALIDATING": {
        "PROMOTING_FACTS",
        "RESEARCHING",
        "REBUILDING_PRODUCT_MASTER",
        "PARTIAL",
        "REVIEW_REQUIRED",
        "NO_DATA_FOUND",
        *_ACTIVE_FAILURE_TARGETS,
    },
    "PROMOTING_FACTS": {"REBUILDING_PRODUCT_MASTER", *_ACTIVE_FAILURE_TARGETS},
    "REBUILDING_PRODUCT_MASTER": {
        "COMPLETED",
        "PARTIAL",
        "REVIEW_REQUIRED",
        *_ACTIVE_FAILURE_TARGETS,
    },
    "FAILED_RETRYABLE": {"QUEUED", "FAILED", "CANCELLED"},
}


def normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_context_value(value: str | None) -> str:
    return str(value or "").strip().upper()


def make_context_hash(
    work_type: str,
    partnumber: str,
    category_code: str | None,
    channel_code: str | None,
) -> str:
    payload = {
        "work_type": _normalize_context_value(work_type),
        "partnumber": normalize_partnumber(partnumber),
        "category_code": _normalize_context_value(category_code),
        "channel_code": _normalize_context_value(channel_code),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def can_transition(current_status: str, target_status: str) -> bool:
    current = str(current_status or "").strip().upper()
    target = str(target_status or "").strip().upper()
    if current not in ITEM_STATES or target not in ITEM_STATES:
        return False
    if current in TERMINAL_ITEM_STATES:
        return False
    return target in _TRANSITIONS.get(current, set())
