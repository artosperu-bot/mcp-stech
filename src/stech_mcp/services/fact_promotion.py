from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from stech_mcp.domain.product_schema import normalize_field_code
from stech_mcp.domain.source_policy import is_variant_sensitive


_RANK_SCORE = {"A1": 100, "A2": 90, "B": 80, "C": 60, "D": 40, "E": 20}
_STRONG_EXACT_SOURCE_TYPES = {"MANUFACTURER", "OFFICIAL_DOCUMENT", "AUTHORIZED_DISTRIBUTOR"}


def _candidate_id(candidate: dict[str, Any]) -> int | None:
    raw = candidate.get("product_fact_candidate_id") or candidate.get("candidate_id")
    return int(raw) if raw is not None else None


def _value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _approved_value(row: dict[str, Any]) -> Any:
    if row.get("value_number") is not None:
        return row.get("value_number")
    return row.get("value_text")


def _verification_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"value_text": "true" if value else "false", "value_number": None}
    if isinstance(value, (int, float)):
        return {"value_text": None, "value_number": value}
    if isinstance(value, (list, tuple, dict)):
        return {
            "value_text": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            "value_number": None,
        }
    return {"value_text": str(value), "value_number": None}


class FactPromotionService:
    """Choose evidence winners and persist only through the existing verifier."""

    def __init__(
        self,
        *,
        verification_service: Any,
        enrichment_repository: Any,
        candidate_repository: Any,
    ) -> None:
        self.verification_service = verification_service
        self.enrichment_repository = enrichment_repository
        self.candidate_repository = candidate_repository

    def _mark(self, candidate: dict[str, Any], state: str) -> None:
        candidate_id = _candidate_id(candidate)
        if candidate_id is None:
            return
        updater = getattr(self.candidate_repository, "update_state", None)
        if callable(updater):
            updater(candidate_id, state)

    @staticmethod
    def _reject_reason(partnumber: str, candidate: dict[str, Any]) -> str | None:
        field_code = normalize_field_code(candidate.get("field_code"))
        if not is_variant_sensitive(field_code):
            return None
        source_pn = str(candidate.get("source_partnumber") or "").strip().upper() or None
        if source_pn != partnumber:
            return "SOURCE_PARTNUMBER_MISMATCH"
        grade = str(candidate.get("confidence_rank") or "").strip().upper()
        if grade not in {"A1", "A2", "B"}:
            return "VARIANT_SOURCE_TOO_WEAK"
        source_type = str(candidate.get("source_type") or "").strip().upper()
        if source_type not in _STRONG_EXACT_SOURCE_TYPES:
            return "VARIANT_SOURCE_TYPE_TOO_WEAK"
        return None

    def evaluate_and_promote(
        self,
        partnumber: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        rejected: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        promoted: dict[str, Any] = {}
        preserved: dict[str, Any] = {}

        for raw_candidate in candidates:
            candidate = dict(raw_candidate or {})
            field_code = normalize_field_code(candidate.get("field_code"))
            if not field_code:
                rejected.append({"candidate": candidate, "reason": "FIELD_CODE_REQUIRED"})
                self._mark(candidate, "REJECTED")
                continue
            candidate["field_code"] = field_code
            grade = str(candidate.get("confidence_rank") or "").strip().upper()
            if grade not in _RANK_SCORE:
                rejected.append({"candidate": candidate, "reason": "INVALID_CONFIDENCE_RANK"})
                self._mark(candidate, "REJECTED")
                continue
            if candidate.get("normalized_value") is None:
                rejected.append({"candidate": candidate, "reason": "NORMALIZED_VALUE_REQUIRED"})
                self._mark(candidate, "REJECTED")
                continue
            reason = self._reject_reason(pn, candidate)
            if reason:
                rejected.append({"candidate": candidate, "reason": reason})
                self._mark(candidate, "REJECTED")
                continue
            grouped[field_code].append(candidate)

        approved_rows = self.enrichment_repository.get_approved(pn)
        approved_by_field = {
            normalize_field_code(row.get("field_code")): row
            for row in approved_rows
            if normalize_field_code(row.get("field_code"))
        }

        for field_code, field_candidates in grouped.items():
            existing = approved_by_field.get(field_code)
            existing_grade = str((existing or {}).get("confidence_grade") or "").strip().upper()
            existing_rank = _RANK_SCORE.get(existing_grade, -1)
            existing_method = str((existing or {}).get("method") or "").strip().upper()
            existing_value = _approved_value(existing) if existing else None

            if existing and existing_method == "MANUAL":
                preserved[field_code] = existing_value
                for candidate in field_candidates:
                    rejected.append({"candidate": candidate, "reason": "PRESERVED_MANUAL"})
                    self._mark(candidate, "REJECTED")
                continue

            highest_rank = max(_RANK_SCORE[str(candidate["confidence_rank"]).upper()] for candidate in field_candidates)
            top = [
                candidate
                for candidate in field_candidates
                if _RANK_SCORE[str(candidate["confidence_rank"]).upper()] == highest_rank
            ]
            top_values = {_value_key(candidate["normalized_value"]) for candidate in top}

            if existing and existing_rank > highest_rank:
                preserved[field_code] = existing_value
                for candidate in field_candidates:
                    rejected.append({"candidate": candidate, "reason": "EXISTING_STRONGER_APPROVED"})
                    self._mark(candidate, "REJECTED")
                continue

            if existing and existing_rank == highest_rank:
                existing_key = _value_key(existing_value)
                if any(key != existing_key for key in top_values):
                    conflict = {
                        "field_code": field_code,
                        "reason": "EQUAL_STRENGTH_CONFLICT_WITH_APPROVED",
                        "existing_value": existing_value,
                        "candidate_values": [candidate["normalized_value"] for candidate in top],
                    }
                    conflicts.append(conflict)
                    for candidate in top:
                        self._mark(candidate, "CONFLICT")
                    for candidate in field_candidates:
                        if candidate not in top:
                            rejected.append({"candidate": candidate, "reason": "LOWER_RANK_THAN_CONFLICT"})
                            self._mark(candidate, "REJECTED")
                    continue
                preserved[field_code] = existing_value
                for candidate in field_candidates:
                    rejected.append({"candidate": candidate, "reason": "SAME_AS_EXISTING_APPROVED"})
                    self._mark(candidate, "REJECTED")
                continue

            if len(top_values) > 1:
                conflicts.append({
                    "field_code": field_code,
                    "reason": "EQUAL_STRENGTH_CONFLICT",
                    "candidate_values": [candidate["normalized_value"] for candidate in top],
                })
                for candidate in top:
                    self._mark(candidate, "CONFLICT")
                for candidate in field_candidates:
                    if candidate not in top:
                        rejected.append({"candidate": candidate, "reason": "LOWER_RANK_THAN_CONFLICT"})
                        self._mark(candidate, "REJECTED")
                continue

            winner = top[0]
            verification_value = _verification_value(winner["normalized_value"])
            verification = self.verification_service.verify(
                partnumber=pn,
                field_code=field_code,
                value_text=verification_value["value_text"],
                value_number=verification_value["value_number"],
                unit=winner.get("unit"),
                confidence_grade=str(winner.get("confidence_rank") or "").upper(),
                source_url=winner.get("source_url"),
                source_type=str(winner.get("source_type") or "").upper(),
                source_partnumber=winner.get("source_partnumber"),
                evidence_text=winner.get("evidence_text"),
            )
            if verification.get("preserved_manual"):
                preserved[field_code] = existing_value
                self._mark(winner, "REJECTED")
                rejected.append({"candidate": winner, "reason": "PRESERVED_MANUAL"})
                continue

            promoted[field_code] = winner["normalized_value"]
            self._mark(winner, "PROMOTED")
            for candidate in field_candidates:
                if candidate is winner:
                    continue
                rejected.append({"candidate": candidate, "reason": "LOWER_RANK_THAN_WINNER"})
                self._mark(candidate, "REJECTED")

        return {
            "state": "REVIEW_REQUIRED" if conflicts else "COMPLETED",
            "promoted": promoted,
            "preserved": preserved,
            "rejected": rejected,
            "conflicts": conflicts,
        }
