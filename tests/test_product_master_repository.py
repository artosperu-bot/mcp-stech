from __future__ import annotations

import json

from stech_mcp.db.product_master_repository import ProductMasterRepository


class FakeCursor:
    def __init__(self, fetchone_values=None, fetchall_values=None, rowcount=1):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.rowcount = rowcount
        self.description = []
        self.last_sql = ""
        self.last_params = ()
        self.executions = []

    def execute(self, sql, *params):
        self.last_sql = sql
        self.last_params = params
        self.executions.append((sql, params))
        if "SELECT TOP (1)" in sql and "V_PRODUCT_WORKSPACE_V1" in sql:
            self.description = [("partnumber",), ("brand",)]
        elif "FROM dbo.product_image" in sql:
            self.description = [("product_image_id",), ("partnumber",), ("is_approved",)]
        elif "FROM dbo.channel_draft" in sql and "payload_json" in sql:
            self.description = [("channel_draft_id",), ("partnumber",), ("marketplace",), ("payload_json",)]
        return self

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None

    def fetchall(self):
        return self.fetchall_values.pop(0) if self.fetchall_values else []


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_upsert_master_is_parameterized_normalized_and_serialized_per_partnumber():
    cursor = FakeCursor(rowcount=1)
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)

    result = repo.upsert_master({"partnumber": " 82yu00xylm ", "brand": "LENOVO"})

    joined_sql = "\n".join(sql for sql, _ in cursor.executions)
    assert "82YU00XYLM" not in joined_sql
    assert "UPDLOCK" in joined_sql
    assert "HOLDLOCK" in joined_sql
    assert cursor.executions[0][1][0] == "82YU00XYLM"
    assert result["partnumber"] == "82YU00XYLM"
    assert conn.committed is True
    assert conn.closed is True


def test_replace_draft_persists_exactly_81_coolbox_fields_with_parameters():
    cursor = FakeCursor(
        fetchone_values=[
            (55, 3, "LISTO_PARA_REVISAR", 0, 0, 0, '{"fields":[]}'),
            (99,),
        ]
    )
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)
    fields = [
        {"field": f"F{i}", "value": i, "status": "DISTRIBUTOR", "source": "DELTRON", "method": "DISTRIBUTOR"}
        for i in range(81)
    ]

    result = repo.replace_draft(
        partnumber="82YU00XYLM",
        marketplace="COOLBOX",
        template_name="Laptops-All in one",
        payload={"fields": fields},
    )

    assert result["channel_draft_id"] == 99
    assert result["draft_version"] == 4
    assert result["field_count"] == 81
    assert result["reused"] is False
    assert "UPDLOCK" in cursor.executions[0][0]
    assert "HOLDLOCK" in cursor.executions[0][0]
    field_inserts = [(sql, params) for sql, params in cursor.executions if "INSERT dbo.channel_draft_field" in sql]
    assert len(field_inserts) == 81
    assert field_inserts[0][1][2] == "F0"
    assert "F0" not in field_inserts[0][0]
    assert conn.committed is True
    assert conn.closed is True


def test_replace_draft_counts_missing_and_estimated_fields():
    cursor = FakeCursor(fetchone_values=[None, (7,)])
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)
    fields = [
        {"field": "SSD", "value": None, "status": "RESEARCH_REQUIRED"},
        {"field": "Peso (g)", "value": 2500, "status": "ESTIMATED"},
        {"field": "Marca", "value": "Lenovo", "status": "DISTRIBUTOR"},
    ]

    result = repo.replace_draft(
        partnumber="82YU00XYLM",
        marketplace="COOLBOX",
        template_name="Laptops-All in one",
        payload={"fields": fields},
    )

    assert result["required_missing_count"] == 1
    assert result["estimated_count"] == 1
    assert result["draft_version"] == 1
    assert result["reused"] is False


def test_replace_draft_reuses_identical_latest_payload_instead_of_creating_version():
    fields = [
        {"field": "Marca", "value": "Lenovo", "status": "DISTRIBUTOR"},
        {"field": "Precio Lista", "value": None, "status": "MARKETPLACE_INPUT"},
    ]
    payload = {"fields": fields}
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    cursor = FakeCursor(
        fetchone_values=[
            (55, 8, "LISTO_PARA_REVISAR", 2, 0, 0, payload_json),
        ]
    )
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)

    result = repo.replace_draft(
        partnumber="82YU00XYLM",
        marketplace="COOLBOX",
        template_name="Laptops-All in one",
        payload=payload,
    )

    assert result == {
        "channel_draft_id": 55,
        "partnumber": "82YU00XYLM",
        "marketplace": "COOLBOX",
        "template_name": "Laptops-All in one",
        "draft_version": 8,
        "status": "LISTO_PARA_REVISAR",
        "field_count": 2,
        "required_missing_count": 0,
        "estimated_count": 0,
        "reused": True,
    }
    assert not any("INSERT dbo.channel_draft (" in sql for sql, _ in cursor.executions)
    assert not any("INSERT dbo.channel_draft_field" in sql for sql, _ in cursor.executions)
    assert conn.closed is True


def test_approve_latest_draft_marks_specific_latest_version_and_audits_actor():
    cursor = FakeCursor(
        fetchone_values=[
            (55, 8, "LISTO_PARA_REVISAR", 0, 0),
        ]
    )
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)

    result = repo.approve_latest_draft(
        partnumber="82yu00xylm",
        marketplace="coolbox",
        approved_by="SCR_UI",
        note="Revisado visualmente",
    )

    assert result["found"] is True
    assert result["partnumber"] == "82YU00XYLM"
    assert result["marketplace"] == "COOLBOX"
    assert result["channel_draft_id"] == 55
    assert result["draft_version"] == 8
    assert result["approval_status"] == "APROBADO"
    update_calls = [(sql, params) for sql, params in cursor.executions if "approval_status" in sql and "UPDATE dbo.channel_draft" in sql]
    assert len(update_calls) == 1
    assert update_calls[0][1] == ("SCR_UI", "Revisado visualmente", 55)
    assert conn.committed is True
    assert conn.closed is True


def test_add_audit_event_is_parameterized():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    repo = ProductMasterRepository(lambda: conn)

    repo.add_audit_event(
        partnumber="82YU00XYLM",
        event_type="PRODUCT_PREPARED",
        actor_source="STECH_MCP",
        channel="COOLBOX",
        detail={"draft_version": 1},
    )

    assert "82YU00XYLM" not in cursor.last_sql
    assert cursor.last_params[0] == "82YU00XYLM"
    assert conn.committed is True
    assert conn.closed is True
