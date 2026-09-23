from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


_ALLOWED_SOURCE_TYPES = {
    "MANUFACTURER",
    "OFFICIAL_DOCUMENT",
    "AUTHORIZED_DISTRIBUTOR",
    "TRUSTED_RETAILER",
    "SAME_CHASSIS",
    "RULE",
    "MANUAL",
}

_RANK_BY_CONFIDENCE = {
    "A1": 100,
    "A2": 90,
    "B": 80,
    "C": 60,
    "D": 40,
    "E": 20,
}

_VARIANT_SENSITIVE_FIELDS = {
    "gtin",
    "ean",
    "upc",
    "cpu_model",
    "gpu_model",
    "gpu_detail",
    "ram_capacity_gb",
    "memory_detail",
    "ssd_capacity_gb",
    "storage_detail",
    "refresh_rate_hz",
    "os_name",
    "color",
}

_STRONG_EXACT_SOURCE_TYPES = {
    "MANUFACTURER",
    "OFFICIAL_DOCUMENT",
    "AUTHORIZED_DISTRIBUTOR",
}


class ProductFieldVerificationService:
    """Persist a reviewed product fact together with auditable source evidence.

    This service intentionally does not browse the web. It accepts evidence already
    found by an operator/agent and enforces the source-quality rules before a fact
    can become an approved VERIFIED enrichment.
    """

    def __init__(self, enrichment_repository: Any):
        self.enrichment_repository = enrichment_repository

    def verify(
        self,
        *,
        partnumber: str,
        field_code: str,
        value_text: str | None = None,
        value_number: Any | None = None,
        unit: str | None = None,
        confidence_grade: str,
        source_url: str | None = None,
        source_type: str,
        source_partnumber: str | None = None,
        evidence_text: str | None = None,
    ) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        code = str(field_code or "").strip().lower()
        grade = str(confidence_grade or "").strip().upper()
        evidence_type = str(source_type or "").strip().upper()
        source_pn = str(source_partnumber or "").strip().upper() or None
        url = str(source_url or "").strip() or None
        evidence = str(evidence_text or "").strip() or None

        if not pn:
            raise ValueError("partnumber is required")
        if not code:
            raise ValueError("field_code is required")
        if value_text is None and value_number is None:
            raise ValueError("value_text or value_number is required")
        if grade not in _RANK_BY_CONFIDENCE:
            raise ValueError("confidence_grade must be A1, A2, B, C, D or E")
        if evidence_type not in _ALLOWED_SOURCE_TYPES:
            raise ValueError("unsupported source_type")
        if not url or not evidence:
            raise ValueError("source_url and evidence_text are required for VERIFIED values")

        if code in _VARIANT_SENSITIVE_FIELDS:
            if grade not in {"A1", "A2", "B"}:
                raise ValueError("variant-sensitive fields require confidence A1, A2 or B")
            if evidence_type not in _STRONG_EXACT_SOURCE_TYPES:
                raise ValueError("variant-sensitive fields require manufacturer, official document or authorized distributor evidence")
            if source_pn != pn:
                raise ValueError("variant-sensitive fields require exact source_partnumber")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an absolute http(s) URL")

        saved = self.enrichment_repository.upsert(
            partnumber=pn,
            field_code=code,
            value_text=value_text,
            value_number=value_number,
            unit=unit,
            method="VERIFIED",
            confidence_grade=grade,
            is_approved=True,
        )

        if saved.get("preserved_manual"):
            return {
                "verified": False,
                "preserved_manual": True,
                "partnumber": pn,
                "field_code": code,
                "enrichment_id": saved.get("enrichment_id"),
                "evidence_id": None,
            }

        evidence_row = self.enrichment_repository.add_evidence(
            enrichment_id=int(saved["enrichment_id"]),
            source_url=url,
            source_domain=str(parsed.hostname).lower(),
            source_type=evidence_type,
            source_partnumber=source_pn,
            evidence_text=evidence,
            rank_score=_RANK_BY_CONFIDENCE[grade],
        )
        return {
            "verified": True,
            "preserved_manual": False,
            "partnumber": pn,
            "field_code": code,
            "enrichment_id": saved["enrichment_id"],
            "evidence_id": evidence_row["evidence_id"],
            "method": "VERIFIED",
            "confidence_grade": grade,
            "source_domain": str(parsed.hostname).lower(),
        }
