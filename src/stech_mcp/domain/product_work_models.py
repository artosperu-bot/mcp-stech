from __future__ import annotations

import hashlib
import json
from typing import Any


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
    "WAITING_EXTERNAL_RESEARCH",
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
_EXTERNAL_HANDOFF_TARGET = "WAITING_EXTERNAL_RESEARCH"

_TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"LOADING_SOURCE_DATA", *_ACTIVE_FAILURE_TARGETS},
    "LOADING_SOURCE_DATA": {"ANALYZING_MISSING_FIELDS", *_ACTIVE_FAILURE_TARGETS},
    "ANALYZING_MISSING_FIELDS": {
        "RESEARCHING",
        "VALIDATING",
        "REBUILDING_PRODUCT_MASTER",
        _EXTERNAL_HANDOFF_TARGET,
        "COMPLETED",
        "PARTIAL",
        "REVIEW_REQUIRED",
        "NO_DATA_FOUND",
        *_ACTIVE_FAILURE_TARGETS,
    },
    "RESEARCHING": {
        "READING_DOCUMENTS",
        "VALIDATING",
        _EXTERNAL_HANDOFF_TARGET,
        *_ACTIVE_FAILURE_TARGETS,
    },
    "READING_DOCUMENTS": {
        "VALIDATING",
        "RESEARCHING",
        _EXTERNAL_HANDOFF_TARGET,
        *_ACTIVE_FAILURE_TARGETS,
    },
    "VALIDATING": {
        "PROMOTING_FACTS",
        "RESEARCHING",
        "REBUILDING_PRODUCT_MASTER",
        _EXTERNAL_HANDOFF_TARGET,
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
    "WAITING_EXTERNAL_RESEARCH": {
        "VALIDATING",
        "COMPLETED",
        "PARTIAL",
        "REVIEW_REQUIRED",
        "NO_DATA_FOUND",
        *_ACTIVE_FAILURE_TARGETS,
    },
    "FAILED_RETRYABLE": {"QUEUED", "FAILED", "CANCELLED"},
}


def normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_context_value(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_extra_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    output: dict[str, Any] = {}
    for key in ("scope", "requirements_version", "template_code"):
        value = _normalize_context_value(context.get(key))
        if value:
            output[key] = value

    fields = context.get("requested_fields")
    if isinstance(fields, list):
        normalized_fields = sorted(
            {
                _normalize_context_value(value)
                for value in fields
                if _normalize_context_value(value)
            }
        )
        if normalized_fields:
            output["requested_fields"] = normalized_fields

    image_target_count = context.get("image_target_count")
    if image_target_count not in (None, ""):
        output["image_target_count"] = int(image_target_count)
    return output


def make_context_hash(
    work_type: str,
    partnumber: str,
    category_code: str | None,
    channel_code: str | None,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "work_type": _normalize_context_value(work_type),
        "partnumber": normalize_partnumber(partnumber),
        "category_code": _normalize_context_value(category_code),
        "channel_code": _normalize_context_value(channel_code),
    }
    extra = _normalize_extra_context(context)
    if extra:
        payload["context"] = extra
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
