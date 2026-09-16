from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time

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


class ConcurrentSyncService:
    def __init__(self):
        self.guard = threading.Lock()
        self.active = 0
        self.max_active = 0

    def sync(self, partnumber, verified_fields):
        del partnumber, verified_fields
        with self.guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.08)
        with self.guard:
            self.active -= 1
        return {"state": "VTEX_EAN_SYNCED", "retryable": False}


def handler(identity_result, sync_result=None):
    sync = SyncService(sync_result or {"state": "VTEX_EAN_SYNCED", "retryable": False})
    h = EnrichTechnicalHandler(object(), vtex_ean_sync_service=sync)
    h.identity_service = IdentityService(identity_result)
    return h, sync


def item(post_actions=None, partnumber="82YU00XYLM"):
    return {
        "work_type": "RESEARCH_IDENTITY",
        "partnumber": partnumber,
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
        "partnumber": "82YU00XYLM",
        "verified_fields": {"ean": "0197528523880"},
        "candidate_fields": {},
        "promoted_fields": ["ean"],
        "decision": "PROMOTED",
        "evidence_summary": {"strong_source_count": 1, "has_primary": True, "has_authorized_distributor": False},
        "conflicts": [],
        "error_code": None,
    }


def test_identity_without_vtex_post_action_never_calls_sync():
    h, sync = handler(verified())
    out = h(item(), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VERIFICADO"
    assert out["result"]["decision"] == "PROMOTED"
    assert out["result"]["vtex_state"] is None
    assert sync.calls == []


def test_verified_identity_runs_vtex_ean_post_action_once_and_returns_persistable_result():
    h, sync = handler(verified())
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VTEX_EAN_SYNCED"
    assert out["result"] == {
        "partnumber": "82YU00XYLM",
        "identity_state": "COMPLETED",
        "identity_result_code": "VERIFICADO",
        "verified_fields": {"ean": "0197528523880"},
        "candidate_fields": {},
        "promoted_fields": ["ean"],
        "decision": "PROMOTED",
        "evidence_summary": {"strong_source_count": 1, "has_primary": True, "has_authorized_distributor": False},
        "vtex_state": "VTEX_EAN_SYNCED",
        "error_code": None,
    }
    assert sync.calls == [("82YU00XYLM", {"ean": "0197528523880"})]


def test_already_verified_identity_can_still_sync_to_vtex():
    h, sync = handler(verified("YA_VERIFICADO"), {"state": "VTEX_EAN_ALREADY_PRESENT", "retryable": False})
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "COMPLETED"
    assert out["current_step"] == "VTEX_EAN_ALREADY_PRESENT"
    assert out["result"]["vtex_state"] == "VTEX_EAN_ALREADY_PRESENT"
    assert len(sync.calls) == 1


def test_review_required_never_calls_vtex_and_keeps_review_result():
    h, sync = handler({
        "state": "REVIEW_REQUIRED",
        "result_code": "REVIEW_REQUIRED",
        "partnumber": "82YU00XYLM",
        "verified_fields": {},
        "candidate_fields": {"ean": ["0197528523880"]},
        "promoted_fields": [],
        "decision": "CONFLICT",
        "evidence_summary": {"strong_source_count": 2, "has_primary": False, "has_authorized_distributor": True},
        "conflicts": [{"field_code": "ean"}],
        "error_code": "IDENTITY_CONFLICT",
    })
    out = h(item(["VTEX_EAN_SYNC"]), lambda *_: None)

    assert out["status"] == "REVIEW_REQUIRED"
    assert out["result"]["decision"] == "CONFLICT"
    assert out["result"]["vtex_state"] is None
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
    assert out["result"]["vtex_state"] == "VTEX_EAN_CONFLICT"
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


def test_vtex_ean_sync_is_serialized_across_concurrent_identity_workers():
    sync = ConcurrentSyncService()
    handlers = []
    for pn in ("PN-A", "PN-B"):
        identity = verified()
        identity["partnumber"] = pn
        h = EnrichTechnicalHandler(object(), vtex_ean_sync_service=sync)
        h.identity_service = IdentityService(identity)
        handlers.append((h, pn))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(h, item(["VTEX_EAN_SYNC"], pn), lambda *_: None) for h, pn in handlers]
        outputs = [future.result(timeout=2) for future in futures]

    assert [out["current_step"] for out in outputs] == ["VTEX_EAN_SYNCED", "VTEX_EAN_SYNCED"]
    assert sync.max_active == 1
