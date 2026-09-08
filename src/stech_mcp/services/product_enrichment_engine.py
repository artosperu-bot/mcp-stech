from __future__ import annotations

from typing import Any, Callable

from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured


ProgressCallback = Callable[[str, int], None]


def _pending_fields(snapshot: dict[str, Any], requested_fields: list[str] | None) -> list[str]:
    pending = [
        normalize_field_code(value)
        for value in [
            *(snapshot.get("missing_required") or []),
            *(snapshot.get("missing_recommended") or []),
        ]
        if normalize_field_code(value)
    ]
    deduped: list[str] = []
    for field_code in pending:
        if field_code not in deduped:
            deduped.append(field_code)
    if requested_fields is None:
        return deduped
    requested = {
        normalize_field_code(value)
        for value in requested_fields
        if normalize_field_code(value)
    }
    return [field_code for field_code in deduped if field_code in requested]


class ProductEnrichmentEngine:
    """Channel-neutral technical enrichment orchestrator.

    Facts are stored through candidate/promotion services only. This engine does
    not call marketplace publishing, ProductPrepare/Coolbox, price or stock writes.
    """

    def __init__(
        self,
        *,
        product_repository: Any,
        technical_status_service: Any,
        deltron_adapter: Any,
        candidate_repository: Any,
        promotion_service: Any,
        research_planner: Any,
        search_provider: Any,
        source_document_service: Any,
        fact_extractor: Any,
        audit_repository: Any | None = None,
    ) -> None:
        self.product_repository = product_repository
        self.technical_status_service = technical_status_service
        self.deltron_adapter = deltron_adapter
        self.candidate_repository = candidate_repository
        self.promotion_service = promotion_service
        self.research_planner = research_planner
        self.search_provider = search_provider
        self.source_document_service = source_document_service
        self.fact_extractor = fact_extractor
        self.audit_repository = audit_repository

    def _persist_candidates(
        self,
        partnumber: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for candidate in candidates:
            field_code = normalize_field_code(candidate.get("field_code"))
            if not field_code or candidate.get("normalized_value") is None:
                continue
            evidence_text = candidate.get("evidence_text")
            if not evidence_text and candidate.get("source_label"):
                evidence_text = f"{candidate.get('source_label')}: {candidate.get('raw_value')}"
            saved = self.candidate_repository.add(
                partnumber=partnumber,
                field_code=field_code,
                raw_value=candidate.get("raw_value"),
                normalized_value=candidate.get("normalized_value"),
                unit=candidate.get("unit"),
                source_type=str(candidate.get("source_type") or "").upper(),
                source_name=candidate.get("source_name"),
                source_url=candidate.get("source_url"),
                source_partnumber=candidate.get("source_partnumber"),
                evidence_text=evidence_text,
                page_number=candidate.get("page_number"),
                confidence_rank=str(candidate.get("confidence_rank") or "").upper(),
                state="PENDING",
            )
            persisted.append({
                **candidate,
                **saved,
                "field_code": field_code,
                "evidence_text": evidence_text,
            })
        return persisted

    @staticmethod
    def _promotable(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Existing verifier requires auditable URL + evidence. Distributor facts
        # without a product-specific URL remain candidates and never get a fake URL.
        return [
            candidate
            for candidate in candidates
            if candidate.get("source_url") and candidate.get("evidence_text")
        ]

    def _audit(self, partnumber: str, detail: dict[str, Any]) -> None:
        if self.audit_repository is None:
            return
        recorder = getattr(self.audit_repository, "add_audit_event", None)
        if callable(recorder):
            recorder(
                partnumber=partnumber,
                event_type="TECHNICAL_ENRICHMENT_V2",
                actor_source="STECH_ENRICHMENT_WORKER",
                channel=None,
                detail=detail,
            )

    def enrich(
        self,
        partnumber: str,
        category_code: str | None,
        requested_fields: list[str] | None,
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        product = self.product_repository.get_by_partnumber(pn)
        if product is None:
            raise LookupError(f"product not found: {pn}")

        before = self.technical_status_service.get(pn)
        category = normalize_category_code(category_code or before.get("category_code"))
        if not category:
            raise LookupError(f"technical category not found: {pn}")

        promoted_fields: dict[str, Any] = {}
        conflicts: list[dict[str, Any]] = []
        sources_consulted: list[str] = []

        # First exploit local distributor data. It is always persisted as
        # candidate evidence; it is promoted only when it already carries a
        # real auditable URL/evidence contract.
        deltron_candidates = self.deltron_adapter.adapt(product, category_code=category)
        local_persisted = self._persist_candidates(pn, deltron_candidates)
        local_promotable = self._promotable(local_persisted)
        if local_promotable:
            local_result = self.promotion_service.evaluate_and_promote(pn, local_promotable)
            promoted_fields.update(local_result.get("promoted") or {})
            conflicts.extend(local_result.get("conflicts") or [])

        progress("ANALYZING_MISSING_FIELDS", 20)
        after_local = self.technical_status_service.get(pn)
        pending = _pending_fields(after_local, requested_fields)

        if conflicts:
            progress("REBUILDING_PRODUCT_MASTER", 95)
            after = self.technical_status_service.get(pn)
            self._audit(pn, {
                "state": "REVIEW_REQUIRED",
                "category_code": category,
                "promoted_fields": list(promoted_fields),
                "remaining_fields": _pending_fields(after, requested_fields),
                "conflicts": conflicts,
            })
            return {
                "state": "REVIEW_REQUIRED",
                "before": before,
                "after": after,
                "promoted_fields": list(promoted_fields),
                "remaining_fields": _pending_fields(after, requested_fields),
                "conflicts": conflicts,
                "sources_consulted": sources_consulted,
                "error_code": "FACT_CONFLICT",
            }

        if not pending:
            progress("REBUILDING_PRODUCT_MASTER", 95)
            after = after_local
            self._audit(pn, {
                "state": "COMPLETED",
                "category_code": category,
                "promoted_fields": list(promoted_fields),
                "remaining_fields": [],
            })
            return {
                "state": "COMPLETED",
                "before": before,
                "after": after,
                "promoted_fields": list(promoted_fields),
                "remaining_fields": [],
                "conflicts": [],
                "sources_consulted": [],
                "error_code": None,
            }

        brand = str(product.get("marca") or product.get("brand") or "").strip()
        research_plan = self.research_planner.plan(pn, brand, category, pending)
        progress("RESEARCHING", 35)
        researched_candidates: list[dict[str, Any]] = []
        seen_urls: set[tuple[str, str]] = set()
        search_error_code: str | None = None

        try:
            for query in research_plan:
                results = self.search_provider.search(query.query, domains=query.domains, limit=5)
                # Avoid repeatedly ingesting the same URL for the same field.
                for result in results[:3]:
                    url_key = (query.field_code, result.url)
                    if url_key in seen_urls:
                        continue
                    seen_urls.add(url_key)
                    progress("READING_DOCUMENTS", 50)
                    document = self.source_document_service.ingest(
                        result.url,
                        pn,
                        query.stage,
                    )
                    if result.url not in sources_consulted:
                        sources_consulted.append(result.url)
                    extracted = self.fact_extractor.extract(
                        document,
                        [query.field_code],
                        pn,
                    )
                    researched_candidates.extend(self._persist_candidates(pn, extracted))
                    progress("RESEARCHING", 60)
        except SearchProviderNotConfigured:
            search_error_code = "SEARCH_PROVIDER_NOT_CONFIGURED"

        progress("VALIDATING", 72)
        promotable_research = self._promotable(researched_candidates)
        if promotable_research:
            promotion = self.promotion_service.evaluate_and_promote(pn, promotable_research)
            promoted_fields.update(promotion.get("promoted") or {})
            conflicts.extend(promotion.get("conflicts") or [])
            progress("PROMOTING_FACTS", 82)

        progress("REBUILDING_PRODUCT_MASTER", 95)
        after = self.technical_status_service.get(pn)
        remaining = _pending_fields(after, requested_fields)
        if conflicts:
            state = "REVIEW_REQUIRED"
            error_code = "FACT_CONFLICT"
        elif not remaining:
            state = "COMPLETED"
            error_code = None
        else:
            state = "PARTIAL"
            error_code = search_error_code

        self._audit(pn, {
            "state": state,
            "category_code": category,
            "promoted_fields": list(promoted_fields),
            "remaining_fields": remaining,
            "conflicts": conflicts,
            "sources_consulted": sources_consulted,
            "error_code": error_code,
        })
        return {
            "state": state,
            "before": before,
            "after": after,
            "promoted_fields": list(promoted_fields),
            "remaining_fields": remaining,
            "conflicts": conflicts,
            "sources_consulted": sources_consulted,
            "error_code": error_code,
        }
