from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1
from stech_mcp.chatgpt_bridge.mailbox import Mailbox, MailboxConflictError


def request() -> ResearchRequestV1:
    return ResearchRequestV1.model_validate(
        {
            "schema_version": 1,
            "request_id": "rw_1234_a1b2c3d4e5f6",
            "created_at": datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc),
            "product_work_item_id": 1234,
            "product_work_job_id": 140,
            "work_type": "RESEARCH_IMAGES",
            "partnumber": "910-006862",
            "brand": "LOGITECH",
            "model": None,
            "category_code": None,
            "requested_fields": ["images"],
            "research_policy": {},
        }
    )


def test_mailbox_creates_append_only_directories_and_request(tmp_path):
    mailbox = Mailbox(tmp_path)
    path = mailbox.write_request(request())

    assert path == tmp_path / "research_bridge" / "requests" / "rw_1234_a1b2c3d4e5f6.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["partnumber"] == "910-006862"
    assert (tmp_path / "research_bridge" / "results").is_dir()
    assert (tmp_path / "research_bridge" / "receipts").is_dir()


def test_writing_identical_request_twice_is_idempotent(tmp_path):
    mailbox = Mailbox(tmp_path)
    first = mailbox.write_request(request())
    second = mailbox.write_request(request())
    assert first == second
    assert len(list((tmp_path / "research_bridge" / "requests").glob("*.json"))) == 1


def test_conflicting_existing_request_is_rejected(tmp_path):
    mailbox = Mailbox(tmp_path)
    path = mailbox.write_request(request())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["partnumber"] = "DIFFERENT"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MailboxConflictError):
        mailbox.write_request(request())


def test_receipt_is_create_once_and_result_paths_ignore_receipted_requests(tmp_path):
    mailbox = Mailbox(tmp_path)
    mailbox.ensure_layout()
    result = tmp_path / "research_bridge" / "results" / "rw_1234_a1b2c3d4e5f6.json"
    result.write_text('{"request_id":"rw_1234_a1b2c3d4e5f6"}', encoding="utf-8")

    assert mailbox.pending_result_paths() == [result]

    mailbox.write_receipt("rw_1234_a1b2c3d4e5f6", {"status": "IMPORTED"})
    assert mailbox.pending_result_paths() == []
