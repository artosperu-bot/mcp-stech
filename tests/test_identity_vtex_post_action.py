from __future__ import annotations

import pytest

from stech_mcp.services.handlers.enrich_technical import EnrichTechnicalHandler
from stech_mcp.services.product_work_dispatcher import RetryableWorkError


class IdentityService:
    def __init__(self, result):
        self.result = dict(result)
        self.calls = []

    def research(self, partnumber, requested_fields, progress):
        self.calls.append((partnumber, list(requested_fields or [])))
        return dict(self.result)


class SyncService:
    def __init__(self, result):
        self.result = dict(result)
        self.calls = []

    def sync(self, partnumber, verified_fields):
        self.calls.append((partnumber, dict(verified_fields or {})))
        return dict(self.result)


def handler(identity_result, sync_result=None):
    sync = SyncService(sync_result or {"state": "VTEX_EAN_SYNCED", "retryable": False})
    h = EnrichTechnicalHandler(object(), vtex_ean_sync_service=sync)
    h.identity_service = IdentityService(identity_result)
    return h, sync


def item(post_actions=None):
    return {
        "work_type": "RESEARCH_IDENTITY",
        "partnumber": "82YU00XYLM",
        "input": {
            "requested_fields": ["ean", "upc", "gtin"],
            "post_actions": list(post_actions or []),
            "vtex_account_code": "VTEX_STECH",
        },
    }


def verified(result_code="VERIFICADO"):
    return {
        "state": "COMPLETED",
        "result_code": result_code,
        "verified_fields": {"ean": "0197528523880"},
        "promoted_fields": ["ean"],
        "conflicts": [],
    }


def test_identity_without_vtex_post_action_never_calls_sync():
    h, sync = handler(verified())
    out = h(item(), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VERIFICADO"
    assert sync.calls == []


def test_verified_identity_runs_vtex_ean_post_action_once():
    h, sync = handler(verified())
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VTEX_EAN_SYNCED"
    assert sync.calls == [("82YU00XYLM", {"ean": "0197528523880"})]


def test_already_verified_identity_can_still_sync_to_vtex():
    h, sync = handler(verified("YA_VERIFICADO"), {"state": "VTEX_EAN_ALREADY_PRESENT", "retryable": False})
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VTEX_EAN_ALREADY_PRESENT"
    assert len(sync.calls) == 1


def test_review_required_never_calls_vtex():
    h, sync = handler({
        "state": "REVIEW_REQUIRED",
        "result_code": "REVIEW_REQUIRED",
        "verified_fields": {},
        "conflicts": [{"field_code": "ean"}],
        "error_code": "IDENTITY_CONFLICT",
    })
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "REVIEW_REQUIRED"
    assert sync.calls == []


def test_vtex_conflict_preserves_verified_local_identity_without_retry():
    h, sync = handler(verified(), {
        "state": "VTEX_EAN_CONFLICT",
        "retryable": False,
        "remote_eans": ["4006381333931"],
    })
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VTEX_EAN_CONFLICT"
    assert sync.calls


def test_vtex_temporary_error_uses_existing_worker_retry_mechanism():
    h, _ = handler(verified(), {
        "state": "VTEX_EAN_TEMPORARY_ERROR",
        "retryable": True,
        "error": "HTTP 503",
    })

    with pytest.raises(RetryableWorkError) as exc:
        h(item(["VTEX_EAN_SYNC"]), lambda *_: None)
    assert exc.value.code == "VTEX_EAN_TEMPORARY_ERROR"
