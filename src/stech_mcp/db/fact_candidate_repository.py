from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from stech_mcp.domain.product_schema import normalize_field_code


CANDIDATE_STATES = frozenset({"PENDING", "VERIFIED", "REJECTED", "CONFLICT", "PROMOTED"})


class FactCandidateRepository:
    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @staticmethod
    def _decode_row(cursor: Any, row: Any) -> dict[str, Any]:
        columns = [str(column[0]) for column in cursor.description]
        result = dict(zip(columns, row, strict=False))
        raw = result.get("normalized_value_json")
        if isinstance(raw, str):
            try:
                result["normalized_value"] = json.loads(raw)
            except json.JSONDecodeError:
                result["normalized_value"] = raw
        else:
            result["normalized_value"] = raw
        return result

    def add(
        self,
        *,
        partnumber: str,
        field_code: str,
        raw_value: Any,
        normalized_value: Any,
        source_type: str,
        source_name: str | None,
        source_url: str | None,
        source_partnumber: str | None,
        evidence_text: str | None,
        page_number: int | None,
        confidence_rank: str,
        unit: str | None = None,
        state: str = "PENDING",
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        code = normalize_field_code(field_code)
        candidate_state = str(state or "").strip().upper()
        source = str(source_type or "").strip().upper()
        grade = str(confidence_rank or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        if not code:
            raise ValueError("field_code is required")
        if candidate_state not in CANDIDATE_STATES:
            raise ValueError(f"invalid candidate state: {state}")
        if not source:
            raise ValueError("source_type is required")
        if not grade:
            raise ValueError("confidence_rank is required")

        raw_text = raw_value if isinstance(raw_value, str) else json.dumps(raw_value, ensure_ascii=False, separators=(",", ":"))
        normalized_json = json.dumps(normalized_value, ensure_ascii=False, separators=(",", ":"))
        source_pn = str(source_partnumber or "").strip().upper() or None

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
INSERT INTO dbo.product_fact_candidate(
    partnumber, field_code, raw_value_text, normalized_value_json, unit,
    source_type, source_name, source_url, source_partnumber, evidence_text,
    page_number, confidence_rank, state
)
OUTPUT INSERTED.product_fact_candidate_id
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                pn,
                code,
                raw_text,
                normalized_json,
                unit,
                source,
                source_name,
                source_url,
                source_pn,
                evidence_text,
                int(page_number) if page_number is not None else None,
                grade,
                candidate_state,
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("fact candidate insert did not return id")
            connection.commit()
            return {
                "product_fact_candidate_id": int(row[0]),
                "partnumber": pn,
                "field_code": code,
                "state": candidate_state,
            }
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def list_for_product(self, partnumber: str) -> list[dict[str, Any]]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
SELECT product_fact_candidate_id, partnumber, field_code, raw_value_text,
       normalized_value_json, unit, source_type, source_name, source_url,
       source_partnumber, evidence_text, page_number, confidence_rank, state
FROM dbo.product_fact_candidate
WHERE partnumber = ?
ORDER BY product_fact_candidate_id;
""",
                pn,
            )
            return [self._decode_row(cursor, row) for row in cursor.fetchall()]
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
