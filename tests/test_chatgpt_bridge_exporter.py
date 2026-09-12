from __future__ import annotations

from datetime import datetime, timezone

from stech_mcp.chatgpt_bridge.exporter import ResearchRequestExporter, make_request_id
from stech_mcp.chatgpt_bridge.mailbox import Mailbox


class WorkRepository:
    def __init__(self):
        self.rows = [
            {
                "item_id": 1234,
                "job_id": 140,
                "work_type": "RESEARCH_IMAGES",
                "partnumber": "910-006862",
                "category_code": None,
                "context_hash": "a1b2c3d4e5f678901234",
                "input": {"requested_fields": ["images"], "image_target_count": 4},
                "status": "WAITING_EXTERNAL_RESEARCH",
                "created_at": datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc),
            }
        ]
        self.limits = []

    def list_waiting_external(self, limit=10):
        self.limits.append(limit)
        return list(self.rows)[:limit]


class ProductRepository:
    def get_by_partnumber(self, partnumber):
        assert partnumber == "910-006862"
        return {
            "part_number": partnumber,
            "marca": "LOGITECH",
            "modelo": "MOUSE TEST",
            "precio": 999,
            "stock": 200,
        }


def test_request_id_is_deterministic_and_safe():
    assert make_request_id(1234, "a1b2c3d4e5f67890") == "rw_1234_a1b2c3d4e5f6"
    assert make_request_id(1234, "a1b2c3d4e5f67890") == make_request_id(1234, "a1b2c3d4e5f67890")


def test_exporter_writes_only_safe_product_context(tmp_path):
    work_repo = WorkRepository()
    product_repo = ProductRepository()
    mailbox = Mailbox(tmp_path)
    exporter = ResearchRequestExporter(work_repo, product_repo, mailbox)

    rows = exporter.export_waiting(limit=10)

    assert len(rows) == 1
    request = rows[0]
    assert request.request_id == "rw_1234_a1b2c3d4e5f6"
    assert request.brand == "LOGITECH"
    assert request.model == "MOUSE TEST"
    serialized = request.model_dump(mode="json")
    assert "precio" not in serialized
    assert "stock" not in serialized
    assert "price" not in serialized
    assert "cost" not in serialized
    assert work_repo.limits == [10]


def test_exporter_is_idempotent_for_same_waiting_item(tmp_path):
    exporter = ResearchRequestExporter(WorkRepository(), ProductRepository(), Mailbox(tmp_path))
    first = exporter.export_waiting(limit=10)
    second = exporter.export_waiting(limit=10)

    assert first[0].request_id == second[0].request_id
    files = list((tmp_path / "research_bridge" / "requests").glob("*.json"))
    assert len(files) == 1
