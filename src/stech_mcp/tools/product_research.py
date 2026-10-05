from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from stech_mcp.domain.product_schema import normalize_field_code


def _pending_fields(status: dict[str, Any], requested_fields: list[str] | None = None) -> list[str]:
    pending: list[str] = []
    for raw in [
        *(status.get("missing_required") or []),
        *(status.get("missing_recommended") or []),
    ]:
        code = normalize_field_code(raw)
        if code and code not in pending:
            pending.append(code)
    if requested_fields is None:
        return pending
    requested = {
        normalize_field_code(value)
        for value in requested_fields
        if normalize_field_code(value)
    }
    return [field for field in pending if field in requested]


def _query_to_dict(query: Any) -> dict[str, Any]:
    if is_dataclass(query):
        return asdict(query)
    return {
        "partnumber": getattr(query, "partnumber", None),
        "field_code": getattr(query, "field_code", None),
        "category_code": getattr(query, "category_code", None),
        "query": getattr(query, "query", None),
        "domains": list(getattr(query, "domains", ()) or ()),
        "stage": getattr(query, "stage", None),
    }


def register_product_research_tools(
    mcp: Any,
    *,
    product_repository: Any,
    technical_status_service: Any,
    research_planner: Any,
    source_document_service: Any,
    fact_extractor: Any,
    candidate_repository: Any,
    promotion_service: Any,
    multichannel_readiness_service: Any,
    namespace: Any | None = None,
) -> dict[str, Any]:
    """Register research/audit controls without exposing direct enrichment writes."""

    def persist_candidate(partnumber: str, candidate: dict[str, Any]) -> dict[str, Any]:
        saved = candidate_repository.add(
            partnumber=partnumber,
            field_code=candidate.get("field_code"),
            raw_value=candidate.get("raw_value"),
            normalized_value=candidate.get("normalized_value"),
            unit=candidate.get("unit"),
            source_type=candidate.get("source_type"),
            source_name=candidate.get("source_name"),
            source_url=candidate.get("source_url"),
            source_partnumber=candidate.get("source_partnumber"),
            evidence_text=candidate.get("evidence_text"),
            page_number=candidate.get("page_number"),
            confidence_rank=candidate.get("confidence_rank"),
            state="PENDING",
        )
        return {**candidate, **saved}

    @mcp.tool()
    def product_technical_missing_list(partnumbers: list[str]) -> dict[str, Any]:
        """Return missing canonical technical fields for a batch of products."""
        rows: list[dict[str, Any]] = []
        for raw in list(partnumbers or [])[:1000]:
            pn = str(raw or "").strip().upper()
            if not pn:
                continue
            try:
                status = technical_status_service.get(pn)
            except LookupError as exc:
                rows.append({"partnumber": pn, "found": False, "error": str(exc)})
                continue
            rows.append({
                "partnumber": pn,
                "found": True,
                "category_code": status.get("category_code"),
                "missing_required": list(status.get("missing_required") or []),
                "missing_recommended": list(status.get("missing_recommended") or []),
                "completion_pct": status.get("completion_pct"),
            })
        return {"count": len(rows), "products": rows}

    @mcp.tool()
    def product_research_plan(
        partnumber: str,
        requested_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build directed research queries only for fields still missing."""
        pn = str(partnumber or "").strip().upper()
        try:
            status = technical_status_service.get(pn)
        except LookupError as exc:
            return {"found": False, "partnumber": pn, "error": str(exc), "queries": []}
        product = product_repository.get_by_partnumber(pn) or {}
        pending = _pending_fields(status, requested_fields)
        queries = research_planner.plan(
            pn,
            str(product.get("marca") or product.get("brand") or ""),
            str(status.get("category_code") or ""),
            pending,
        )
        return {
            "found": True,
            "partnumber": pn,
            "category_code": status.get("category_code"),
            "pending_fields": pending,
            "query_count": len(queries),
            "queries": [_query_to_dict(query) for query in queries],
        }

    @mcp.tool()
    def product_source_ingest(
        partnumber: str,
        url: str,
        source_type: str = "OFFICIAL_DOCUMENT",
        target_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Ingest one public source and create evidence candidates, never approved facts."""
        pn = str(partnumber or "").strip().upper()
        status = technical_status_service.get(pn)
        fields = _pending_fields(status, target_fields)
        document = source_document_service.ingest(url, pn, source_type)
        extracted = fact_extractor.extract(document, fields, pn)
        candidates = [persist_candidate(pn, candidate) for candidate in extracted]
        return {
            "partnumber": pn,
            "document_id": document.get("document_id"),
            "sha256": document.get("sha256"),
            "match_type": document.get("match_type"),
            "target_fields": fields,
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    @mcp.tool()
    def product_fact_candidates(partnumber: str) -> dict[str, Any]:
        """List persisted evidence candidates for one product."""
        pn = str(partnumber or "").strip().upper()
        rows = candidate_repository.list_for_product(pn)
        return {"partnumber": pn, "count": len(rows), "candidates": rows}

    @mcp.tool()
    def product_fact_promote(
        partnumber: str,
        field_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate candidates through FactPromotionService and the existing verifier."""
        pn = str(partnumber or "").strip().upper()
        requested = None
        if field_codes is not None:
            requested = {
                normalize_field_code(value)
                for value in field_codes
                if normalize_field_code(value)
            }
        rows = candidate_repository.list_for_product(pn)
        eligible = [
            row
            for row in rows
            if str(row.get("state") or "PENDING").upper() in {"PENDING", "VERIFIED", "CONFLICT"}
            and (requested is None or normalize_field_code(row.get("field_code")) in requested)
        ]
        if not eligible:
            return {
                "state": "COMPLETED",
                "partnumber": pn,
                "promoted": {},
                "preserved": {},
                "rejected": [],
                "conflicts": [],
                "candidate_count": 0,
            }
        result = promotion_service.evaluate_and_promote(pn, eligible)
        return {"partnumber": pn, "candidate_count": len(eligible), **result}

    @mcp.tool()
    def product_fact_promote_batch(partnumbers: list[str]) -> dict[str, Any]:
        """Promote eligible candidates for a bounded product batch."""
        results = [product_fact_promote(pn) for pn in list(partnumbers or [])[:100]]
        return {"count": len(results), "results": results}

    @mcp.tool()
    def product_channel_readiness(partnumber: str) -> dict[str, Any]:
        """Return independent readiness for Coolbox, Falabella and VTEX."""
        pn = str(partnumber or "").strip().upper()
        try:
            result = multichannel_readiness_service.get(pn)
        except LookupError as exc:
            return {"found": False, "partnumber": pn, "error": str(exc)}
        return {"found": True, **result}

    registered = {
        "product_technical_missing_list": product_technical_missing_list,
        "product_research_plan": product_research_plan,
        "product_source_ingest": product_source_ingest,
        "product_fact_candidates": product_fact_candidates,
        "product_fact_promote": product_fact_promote,
        "product_fact_promote_batch": product_fact_promote_batch,
        "product_channel_readiness": product_channel_readiness,
    }
    if namespace is not None:
        for name, func in registered.items():
            setattr(namespace, name, func)
    return registered
