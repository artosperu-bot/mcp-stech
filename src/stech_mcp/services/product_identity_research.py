from __future__ import annotations

from collections import Counter
from typing import Any


_INVALID_PARTNUMBER_TOKENS = {
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "CERRAR",
    "CERRADO",
    "SIN PARTNUMBER",
    "SIN_PARTNUMBER",
    "SIN PN",
    "SIN_PN",
    "NO APLICA",
    "NO_APLICA",
    "-",
    "--",
    ".",
}

_TERMINAL_STATUSES = {"PROMOTED", "NO_ENCONTRADO", "CONFLICTO", "INVALID_IDENTITY"}
_DEFERRED_STATUSES = {"RESEARCH_REQUIRED"}
_ALLOWED_RECORD_STATUSES = {
    "VERIFIED",
    "NO_ENCONTRADO",
    "RESEARCH_REQUIRED",
    "CONFLICTO",
    "INVALID_IDENTITY",
    "ERROR",
}


def classify_partnumber(partnumber: str | None) -> tuple[bool, str | None]:
    raw = str(partnumber or "").strip()
    token = raw.upper()
    if not raw:
        return False, "EMPTY_PARTNUMBER"
    if token in _INVALID_PARTNUMBER_TOKENS:
        return False, "PLACEHOLDER_PARTNUMBER"
    if len(raw) < 2:
        return False, "PARTNUMBER_TOO_SHORT"
    if not any(character.isalnum() for character in raw):
        return False, "PARTNUMBER_WITHOUT_ALPHANUMERIC_CHARACTERS"
    return True, None


class ProductIdentityResearchService:
    """Coordinate bounded, resumable barcode research performed by an external agent.

    The MCP itself does not browse the public web. This service gives ChatGPT or
    another web-enabled agent a durable queue and a one-call way to record an
    outcome. VERIFIED outcomes reuse the existing verification and safe-promotion
    services; negative/ambiguous outcomes are persisted so they are not researched
    repeatedly on every catalog pass.
    """

    def __init__(
        self,
        *,
        identity_repository: Any,
        research_repository: Any,
        verification_service: Any,
        promotion_service: Any,
    ) -> None:
        self.identity_repository = identity_repository
        self.research_repository = research_repository
        self.verification_service = verification_service
        self.promotion_service = promotion_service

    @staticmethod
    def _missing_identifiers(product: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not str(product.get("ean") or "").strip():
            missing.append("EAN")
        if not str(product.get("upc") or "").strip():
            missing.append("UPC")
        return missing

    def queue(
        self,
        *,
        after_id: int = 0,
        limit: int = 100,
        distributor: str | None = None,
        include_deferred: bool = False,
    ) -> dict[str, Any]:
        requested = max(1, min(int(limit or 100), 200))
        cursor_id = max(0, int(after_id or 0))
        output: list[dict[str, Any]] = []
        skipped_terminal_count = 0
        invalid_identity_count = 0
        collision_identity_count = 0
        scanned_count = 0
        source_has_more = False

        while len(output) < requested:
            page = self.identity_repository.list_missing_identifiers(
                after_id=cursor_id,
                limit=500,
                distributor=distributor,
            )
            products = list(page.get("products") or [])
            if not products:
                source_has_more = False
                break

            state_map = self.research_repository.get_for_product_ids(
                [int(row["producto_distribuidor_id"]) for row in products]
            )
            collision_stats_fn = getattr(self.identity_repository, "partnumber_collision_stats", None)
            collision_stats = (
                collision_stats_fn([str(row.get("part_number") or "") for row in products])
                if callable(collision_stats_fn)
                else {}
            )
            page_has_more = bool(page.get("has_more"))

            for position, product in enumerate(products):
                product_id = int(product["producto_distribuidor_id"])
                cursor_id = product_id
                scanned_count += 1
                pn = str(product.get("part_number") or "").strip().upper()
                missing = self._missing_identifiers(product)
                valid_pn, invalid_reason = classify_partnumber(pn)
                stats = collision_stats.get(pn) or {}
                brand_count = int(stats.get("active_brand_count") or 0)
                active_row_count = int(stats.get("active_row_count") or 0)
                if valid_pn and brand_count > 1:
                    valid_pn = False
                    invalid_reason = "PARTNUMBER_USED_BY_MULTIPLE_BRANDS"
                    collision_identity_count += 1

                if not valid_pn:
                    invalid_identity_count += 1
                    for identifier_type in missing:
                        current = state_map.get((product_id, identifier_type)) or {}
                        if str(current.get("status") or "").upper() != "INVALID_IDENTITY":
                            self.research_repository.upsert(
                                producto_distribuidor_id=product_id,
                                partnumber=pn or "<EMPTY>",
                                identifier_type=identifier_type,
                                status="INVALID_IDENTITY",
                                note=invalid_reason,
                                actor_source="STECH_MCP",
                                increment_attempt=False,
                            )
                    continue

                pending: list[str] = []
                research_status: dict[str, str] = {}
                for identifier_type in missing:
                    state = state_map.get((product_id, identifier_type)) or {}
                    status = str(state.get("status") or "PENDING").upper()
                    research_status[identifier_type] = status
                    if status in _TERMINAL_STATUSES:
                        continue
                    if status in _DEFERRED_STATUSES and not include_deferred:
                        continue
                    pending.append(identifier_type)

                if not pending:
                    skipped_terminal_count += 1
                    continue

                output.append(
                    {
                        **product,
                        "part_number": pn,
                        "pending_identifiers": pending,
                        "research_status": research_status,
                        "researchable": True,
                        "identity_guard": "OK",
                        "partnumber_active_row_count": active_row_count,
                        "partnumber_active_brand_count": brand_count,
                    }
                )
                if len(output) >= requested:
                    has_unscanned_in_page = position < (len(products) - 1)
                    source_has_more = has_unscanned_in_page or page_has_more
                    break
            else:
                source_has_more = page_has_more

            if len(output) >= requested:
                break
            if not page_has_more:
                source_has_more = False
                break

        return {
            "after_id": max(0, int(after_id or 0)),
            "count": len(output),
            "products": output,
            "scanned_count": scanned_count,
            "skipped_terminal_count": skipped_terminal_count,
            "invalid_identity_count": invalid_identity_count,
            "collision_identity_count": collision_identity_count,
            "next_after_id": cursor_id,
            "has_more": source_has_more,
            "include_deferred": bool(include_deferred),
            "bounded_search_policy": {
                "max_query_variants_per_identifier": 2,
                "max_strong_sources_per_identifier": 3,
                "on_no_strong_evidence": "NO_ENCONTRADO",
                "on_ambiguous_evidence": "RESEARCH_REQUIRED",
                "continue_on_failure": True,
            },
        }

    def record(
        self,
        *,
        producto_distribuidor_id: int,
        partnumber: str,
        identifier_type: str,
        status: str,
        note: str | None = None,
        value_text: str | None = None,
        confidence_grade: str | None = None,
        source_url: str | None = None,
        source_type: str | None = None,
        source_partnumber: str | None = None,
        evidence_text: str | None = None,
        approved_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        product_id = int(producto_distribuidor_id)
        pn = str(partnumber or "").strip().upper()
        kind = str(identifier_type or "").strip().upper()
        requested_status = str(status or "").strip().upper()
        actor = str(approved_by or "").strip() or "CHATGPT"
        if product_id <= 0:
            raise ValueError("producto_distribuidor_id must be positive")
        valid_pn, invalid_reason = classify_partnumber(pn)
        if not valid_pn and requested_status != "INVALID_IDENTITY":
            requested_status = "INVALID_IDENTITY"
            note = note or invalid_reason
        if kind not in {"EAN", "UPC", "GTIN"}:
            raise ValueError("identifier_type must be EAN, UPC or GTIN")
        if requested_status not in _ALLOWED_RECORD_STATUSES:
            raise ValueError(
                "status must be VERIFIED, NO_ENCONTRADO, RESEARCH_REQUIRED, CONFLICTO, INVALID_IDENTITY or ERROR"
            )

        if requested_status != "VERIFIED":
            saved = self.research_repository.upsert(
                producto_distribuidor_id=product_id,
                partnumber=pn or "<EMPTY>",
                identifier_type=kind,
                status=requested_status,
                value_text=value_text,
                confidence_grade=confidence_grade,
                source_type=source_type,
                source_url=source_url,
                source_partnumber=source_partnumber,
                evidence_text=evidence_text,
                note=note,
                last_error=note if requested_status == "ERROR" else None,
                actor_source=actor,
            )
            return {
                "recorded": True,
                "partnumber": pn,
                "producto_distribuidor_id": product_id,
                "identifier_type": kind,
                "status": requested_status,
                "research": saved,
            }

        if not value_text:
            raise ValueError("VERIFIED research outcome requires value_text")
        if not confidence_grade:
            raise ValueError("VERIFIED research outcome requires confidence_grade")
        if not source_url or not source_type or not source_partnumber or not evidence_text:
            raise ValueError("VERIFIED research outcome requires complete source evidence")

        verified = self.verification_service.verify(
            partnumber=pn,
            field_code=kind.lower(),
            value_text=value_text,
            confidence_grade=confidence_grade,
            source_url=source_url,
            source_type=source_type,
            source_partnumber=source_partnumber,
            evidence_text=evidence_text,
        )
        promotion = self.promotion_service.promote(
            pn,
            kind,
            approved_by=actor,
        )
        promotion_status = str(promotion.get("status") or "").upper()
        if promotion_status in {"PROMOTED", "ALREADY_PRESENT"}:
            final_status = "PROMOTED"
        elif promotion_status == "OPERATIONAL_CONFLICT":
            final_status = "CONFLICTO"
        elif promotion_status == "UNSUPPORTED_OPERATIONAL_GTIN":
            final_status = "VERIFIED"
        else:
            final_status = "ERROR"

        saved = self.research_repository.upsert(
            producto_distribuidor_id=product_id,
            partnumber=pn,
            identifier_type=kind,
            status=final_status,
            value_text=str(promotion.get("value") or value_text),
            confidence_grade=str(verified.get("confidence_grade") or confidence_grade),
            source_type=str(verified.get("source_type") or source_type),
            source_url=source_url,
            source_partnumber=str(source_partnumber).strip().upper(),
            evidence_text=evidence_text,
            note=note,
            last_error=None if final_status != "ERROR" else f"promotion_status={promotion_status or 'UNKNOWN'}",
            actor_source=actor,
        )
        return {
            "recorded": True,
            "partnumber": pn,
            "producto_distribuidor_id": product_id,
            "identifier_type": kind,
            "status": final_status,
            "verified": verified,
            "promotion": promotion,
            "research": saved,
        }

    def record_batch(
        self,
        items: list[dict[str, Any]],
        *,
        approved_by: str = "CHATGPT",
    ) -> dict[str, Any]:
        rows = list(items or [])
        if not rows:
            raise ValueError("items is required")
        if len(rows) > 100:
            raise ValueError("record_batch accepts at most 100 outcomes")

        results: list[dict[str, Any]] = []
        status_counter: Counter[str] = Counter()
        for position, item in enumerate(rows, start=1):
            try:
                result = self.record(
                    producto_distribuidor_id=int(item.get("producto_distribuidor_id") or 0),
                    partnumber=str(item.get("partnumber") or item.get("part_number") or ""),
                    identifier_type=str(item.get("identifier_type") or ""),
                    status=str(item.get("status") or ""),
                    note=item.get("note"),
                    value_text=item.get("value_text"),
                    confidence_grade=item.get("confidence_grade"),
                    source_url=item.get("source_url"),
                    source_type=item.get("source_type"),
                    source_partnumber=item.get("source_partnumber"),
                    evidence_text=item.get("evidence_text"),
                    approved_by=str(item.get("approved_by") or approved_by),
                )
            except (TypeError, ValueError) as exc:
                result = {
                    "recorded": False,
                    "status": "VALIDATION_ERROR",
                    "position": position,
                    "partnumber": str(item.get("partnumber") or item.get("part_number") or "").strip().upper(),
                    "identifier_type": str(item.get("identifier_type") or "").strip().upper(),
                    "error": str(exc),
                    "retryable": True,
                }
            status_counter[str(result.get("status") or "UNKNOWN").upper()] += 1
            results.append(result)

        return {
            "count": len(results),
            "recorded_count": sum(1 for row in results if bool(row.get("recorded"))),
            "error_count": sum(1 for row in results if not bool(row.get("recorded"))),
            "by_status": dict(status_counter),
            "results": results,
        }

    def status(self, partnumber: str | None = None) -> dict[str, Any]:
        return self.research_repository.summary(partnumber=partnumber)
