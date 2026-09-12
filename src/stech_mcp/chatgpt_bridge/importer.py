from __future__ import annotations

from typing import Any

from stech_mcp.chatgpt_bridge.contracts import ResearchRequestV1, ResearchResultV1
from stech_mcp.domain.product_schema import normalize_field_code
from stech_mcp.services.identity_barcode_extractor import normalize_gtin, validate_gtin


class BridgeResultImporter:
    def __init__(
        self,
        *,
        image_candidate_repository: Any,
        fact_candidate_repository: Any,
        work_repository: Any,
        schema_repository: Any | None = None,
        promotion_service: Any | None = None,
    ) -> None:
        self.image_candidate_repository = image_candidate_repository
        self.fact_candidate_repository = fact_candidate_repository
        self.work_repository = work_repository
        self.schema_repository = schema_repository
        self.promotion_service = promotion_service

    @staticmethod
    def _validate_match(request: ResearchRequestV1, result: ResearchResultV1) -> None:
        if request.request_id != result.request_id:
            raise ValueError("request_id mismatch")
        if request.partnumber != result.partnumber:
            raise ValueError("partnumber mismatch")
        if request.work_type != result.work_type:
            raise ValueError("work_type mismatch")

    def _transition(self, request: ResearchRequestV1, status: str, *, code: str, detail: str) -> dict[str, Any]:
        return self.work_repository.transition_item(
            request.product_work_item_id,
            status=status,
            current_step=status.lower().replace("_", " "),
            error_code=code,
            error_detail=detail,
        )

    def _import_images(self, request: ResearchRequestV1, result: ResearchResultV1) -> int:
        count = 0
        for candidate in result.image_candidates:
            exact = bool(candidate.exact_partnumber_match)
            page_url = str(candidate.page_url)
            image_url = str(candidate.image_url)
            host = candidate.page_url.host
            self.image_candidate_repository.add_candidate(
                partnumber=request.partnumber,
                source_type="CHATGPT_WEB_IMAGE",
                source_url=image_url,
                source_domain=str(host or "") or None,
                source_page_url=page_url,
                title=candidate.title,
                thumbnail_url=None,
                image_width_px=candidate.width,
                image_height_px=candidate.height,
                exactness_policy="EXACT_PN_REQUIRED" if exact else "MANUAL_REVIEW",
                partnumber_match="EXACT" if exact else "UNKNOWN",
                variant_match="UNKNOWN",
                confidence_score=95 if exact else 60,
                evidence={
                    "request_id": request.request_id,
                    "page_url": page_url,
                    "researched_at": result.researched_at.isoformat(),
                    "source": "SCHEDULED_CHATGPT",
                },
            )
            count += 1
        return count

    @staticmethod
    def _same_fact(row: dict[str, Any], *, field_code: str, value: Any, source_url: str, source_partnumber: str | None) -> bool:
        return (
            normalize_field_code(row.get("field_code")) == normalize_field_code(field_code)
            and row.get("normalized_value") == value
            and str(row.get("source_url") or "") == str(source_url or "")
            and (str(row.get("source_partnumber") or "").strip().upper() or None) == source_partnumber
        )

    def _add_fact_once(self, request: ResearchRequestV1, **kwargs: Any) -> bool:
        field_code = normalize_field_code(kwargs["field_code"])
        source_url = str(kwargs.get("source_url") or "")
        source_partnumber = str(kwargs.get("source_partnumber") or "").strip().upper() or None
        value = kwargs["normalized_value"]
        for row in self.fact_candidate_repository.list_for_product(request.partnumber):
            if self._same_fact(
                row,
                field_code=field_code,
                value=value,
                source_url=source_url,
                source_partnumber=source_partnumber,
            ):
                return False
        self.fact_candidate_repository.add(**kwargs)
        return True

    def _import_identity(self, request: ResearchRequestV1, result: ResearchResultV1) -> int:
        count = 0
        for candidate in result.identity_candidates:
            normalized = normalize_gtin(candidate.value)
            if not normalized or not validate_gtin(normalized):
                raise ValueError(f"invalid GTIN checksum: {candidate.value}")
            field_code = candidate.identifier_type.lower()
            if field_code == "upc" and len(normalized) != 12:
                raise ValueError("UPC must contain 12 digits")
            if field_code == "ean" and len(normalized) not in {8, 13}:
                raise ValueError("EAN must contain 8 or 13 digits")
            exact = bool(candidate.exact_partnumber_match)
            added = self._add_fact_once(
                request,
                partnumber=request.partnumber,
                field_code=field_code,
                raw_value=normalized,
                normalized_value=normalized,
                unit=None,
                source_type=str(candidate.source_type).strip().upper(),
                source_name=candidate.source_domain,
                source_url=str(candidate.page_url),
                source_partnumber=request.partnumber if exact else None,
                evidence_text=candidate.evidence_text or f"{candidate.label}: {normalized}",
                page_number=None,
                confidence_rank="A1" if exact and candidate.source_type.upper() == "OFFICIAL" else "B",
                state="PENDING",
            )
            count += int(added)
        return count

    def _technical_fields(self, request: ResearchRequestV1) -> tuple[set[str], str]:
        requested = {
            normalize_field_code(value)
            for value in request.requested_fields
            if normalize_field_code(value)
        }
        schema_fields: set[str] = set()
        if self.schema_repository is not None and request.category_code:
            schema_fields = {
                normalize_field_code(getattr(field, "field_code", None))
                for field in self.schema_repository.get_category_schema(request.category_code)
                if normalize_field_code(getattr(field, "field_code", None))
            }

        if schema_fields and requested:
            return schema_fields & requested, "SCHEMA_AND_REQUEST"
        if schema_fields:
            return schema_fields, "SCHEMA"
        if requested:
            return requested, "REQUESTED_FIELDS"
        return set(), "NONE"

    def _import_technical(self, request: ResearchRequestV1, result: ResearchResultV1) -> int:
        allowed, scope_source = self._technical_fields(request)
        if not allowed:
            raise ValueError("technical field scope could not be resolved")
        count = 0
        for candidate in result.technical_candidates:
            field_code = normalize_field_code(candidate.field_name)
            if field_code not in allowed:
                if scope_source == "REQUESTED_FIELDS":
                    raise ValueError(f"field is outside requested technical fields: {field_code}")
                raise ValueError(f"field is outside technical schema/request scope: {field_code}")
            exact = bool(candidate.exact_partnumber_match)
            added = self._add_fact_once(
                request,
                partnumber=request.partnumber,
                field_code=field_code,
                raw_value=candidate.value,
                normalized_value=candidate.value,
                unit=None,
                source_type=str(candidate.source_type).strip().upper(),
                source_name=candidate.source_domain,
                source_url=str(candidate.page_url),
                source_partnumber=request.partnumber if exact else None,
                evidence_text=candidate.evidence_text,
                page_number=None,
                confidence_rank="A1" if exact and candidate.source_type.upper() == "OFFICIAL" else "B",
                state="PENDING",
            )
            count += int(added)
        return count

    def import_result(self, request: ResearchRequestV1, result: ResearchResultV1) -> dict[str, Any]:
        self._validate_match(request, result)

        if result.status == "TEMPORARY_RESEARCH_ERROR":
            item = self.work_repository.schedule_retry(
                request.product_work_item_id,
                error_code="TEMPORARY_EXTERNAL_RESEARCH_ERROR",
                error_detail=result.notes or "scheduled ChatGPT research returned a temporary error",
                delay_seconds=300,
            )
            return {"status": str(item.get("status") or "FAILED_RETRYABLE"), "imported": 0}

        if result.status == "NO_VERIFIED_EVIDENCE":
            self._transition(
                request,
                "NO_DATA_FOUND",
                code="NO_VERIFIED_EXTERNAL_EVIDENCE",
                detail=result.notes or "scheduled ChatGPT research found no verifiable evidence",
            )
            return {"status": "NO_DATA_FOUND", "imported": 0}

        imported = 0
        if request.work_type == "RESEARCH_IMAGES":
            imported = self._import_images(request, result)
        elif request.work_type == "RESEARCH_IDENTITY":
            imported = self._import_identity(request, result)
        elif request.work_type == "ENRICH_TECHNICAL":
            imported = self._import_technical(request, result)
        else:
            raise ValueError(f"unsupported bridge work type: {request.work_type}")

        if result.status == "CONFLICT":
            code = "EXTERNAL_RESEARCH_CONFLICT"
            detail = result.notes or "scheduled ChatGPT research reported conflicting evidence"
        else:
            code = "EXTERNAL_EVIDENCE_REVIEW_REQUIRED"
            detail = result.notes or f"{imported} external evidence candidate(s) imported"
        self._transition(request, "REVIEW_REQUIRED", code=code, detail=detail)
        return {"status": "REVIEW_REQUIRED", "imported": imported}
