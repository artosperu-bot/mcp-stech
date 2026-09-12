from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1
from stech_mcp.chatgpt_bridge.mailbox import Mailbox
from stech_mcp.chatgpt_bridge.runner import BridgeRunner, start_bridge_thread


class Transport:
    def __init__(self):
        self.calls = []

    def pull(self):
        self.calls.append("pull")

    def commit_and_push(self):
        self.calls.append("push")
        return True


class Exporter:
    def __init__(self):
        self.calls = []

    def export_waiting(self, *, limit):
        self.calls.append(limit)
        return []


class Importer:
    def __init__(self):
        self.calls = []

    def import_result(self, request, result):
        self.calls.append((request, result))
        return {"status": "REVIEW_REQUIRED", "imported": 1}


class FakeConfig:
    def __init__(self, enabled):
        self.enabled = enabled


class FakeThread:
    created = []

    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True


class FakeRunner:
    def run_forever(self):
        raise AssertionError("test thread factory must not execute target")


def request_payload():
    return ResearchRequestV1.model_validate(
        {
            "request_id": "rw_1234_a1b2c3d4e5f6",
            "created_at": datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc),
            "product_work_item_id": 1234,
            "product_work_job_id": 140,
            "work_type": "RESEARCH_IMAGES",
            "partnumber": "PN1",
            "requested_fields": ["images"],
            "research_policy": {},
        }
    )


def test_run_once_pulls_imports_receipts_exports_then_pushes(tmp_path):
    mailbox = Mailbox(tmp_path)
    request = request_payload()
    mailbox.write_request(request)
    result_path = tmp_path / "research_bridge" / "results" / f"{request.request_id}.json"
    result_path.write_text(
        """{
          "schema_version": 1,
          "request_id": "rw_1234_a1b2c3d4e5f6",
          "partnumber": "PN1",
          "work_type": "RESEARCH_IMAGES",
          "researched_at": "2026-09-11T22:40:00Z",
          "status": "EVIDENCE_FOUND",
          "sources": [],
          "image_candidates": [{
            "image_url": "https://brand.example/pn1.jpg",
            "page_url": "https://brand.example/pn1",
            "exact_partnumber_match": true
          }],
          "identity_candidates": [],
          "technical_candidates": [],
          "notes": ""
        }""",
        encoding="utf-8",
    )
    transport = Transport()
    exporter = Exporter()
    importer = Importer()
    runner = BridgeRunner(
        mailbox=mailbox,
        transport=transport,
        exporter=exporter,
        importer=importer,
        max_export_per_cycle=10,
        max_import_per_cycle=20,
    )

    summary = runner.run_once()

    assert transport.calls == ["pull", "push"]
    assert exporter.calls == [10]
    assert len(importer.calls) == 1
    assert summary == {"imported": 1, "exported": 0, "pushed": True}
    receipt = tmp_path / "research_bridge" / "receipts" / f"{request.request_id}.json"
    assert receipt.exists()


def test_run_once_does_not_create_receipt_when_import_fails(tmp_path):
    mailbox = Mailbox(tmp_path)
    request = request_payload()
    mailbox.write_request(request)
    result_path = tmp_path / "research_bridge" / "results" / f"{request.request_id}.json"
    result_path.write_text('{"bad":"payload"}', encoding="utf-8")
    runner = BridgeRunner(
        mailbox=mailbox,
        transport=Transport(),
        exporter=Exporter(),
        importer=Importer(),
        max_export_per_cycle=10,
        max_import_per_cycle=20,
    )

    try:
        runner.run_once()
    except Exception:
        pass

    receipt = tmp_path / "research_bridge" / "receipts" / f"{request.request_id}.json"
    assert not receipt.exists()


def test_run_forever_survives_one_transient_cycle_error(tmp_path):
    sleeps = []
    runner = BridgeRunner(
        mailbox=Mailbox(tmp_path),
        transport=Transport(),
        exporter=Exporter(),
        importer=Importer(),
        max_export_per_cycle=10,
        max_import_per_cycle=20,
        poll_seconds=1,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )
    calls = []

    def flaky_cycle():
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise RuntimeError("temporary git failure")
        raise StopIteration("stop test after retry")

    runner.run_once = flaky_cycle

    with pytest.raises(StopIteration, match="stop test"):
        runner.run_forever()

    assert calls == [1, 2]
    assert sleeps == [1]
    assert runner.last_error == "RuntimeError: temporary git failure"


def test_start_bridge_thread_runs_bridge_inside_stech_mcp_when_enabled():
    FakeThread.created = []
    runner = FakeRunner()

    thread = start_bridge_thread(FakeConfig(True), runner, thread_factory=FakeThread)

    assert thread is FakeThread.created[0]
    assert thread.started is True
    assert thread.daemon is True
    assert thread.name == "stech-chatgpt-bridge"
    assert thread.target == runner.run_forever


def test_start_bridge_thread_is_noop_when_disabled():
    FakeThread.created = []

    thread = start_bridge_thread(FakeConfig(False), FakeRunner(), thread_factory=FakeThread)

    assert thread is None
    assert FakeThread.created == []
