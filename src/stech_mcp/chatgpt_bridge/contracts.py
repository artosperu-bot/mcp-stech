from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


WorkType = Literal["RESEARCH_IMAGES", "RESEARCH_IDENTITY", "ENRICH_TECHNICAL"]
ResultStatus = Literal[
    "EVIDENCE_FOUND",
    "NO_VERIFIED_EVIDENCE",
    "CONFLICT",
    "TEMPORARY_RESEARCH_ERROR",
]

_REQUEST_ID_PATTERN = r"^rw_[A-Za-z0-9_-]{6,80}$"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchPolicyV1(_StrictModel):
    exact_partnumber_required: bool = True
    prefer_official_sources: bool = True
    max_sources: int = Field(default=5, ge=1, le=10)
    max_candidates: int = Field(default=10, ge=1, le=10)


class ResearchSourceV1(_StrictModel):
    page_url: HttpUrl
    source_domain: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=40)
    title: str | None = Field(default=None, max_length=500)
    exact_partnumber_match: bool = False


class ImageCandidateV1(_StrictModel):
    image_url: HttpUrl
    page_url: HttpUrl
    title: str | None = Field(default=None, max_length=500)
    width: int | None = Field(default=None, gt=0, le=50000)
    height: int | None = Field(default=None, gt=0, le=50000)
    exact_partnumber_match: bool = False


class IdentityCandidateV1(_StrictModel):
    identifier_type: Literal["EAN", "UPC", "GTIN"]
    value: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=100)
    page_url: HttpUrl
    source_domain: str = Field(min_length=1, max_length=255)
    source_type: str = Field(default="WEB", min_length=1, max_length=40)
    exact_partnumber_match: bool = False
    evidence_text: str | None = Field(default=None, max_length=2000)


class TechnicalCandidateV1(_StrictModel):
    field_name: str = Field(min_length=1, max_length=100)
    value: Any
    page_url: HttpUrl
    source_domain: str = Field(min_length=1, max_length=255)
    source_type: str = Field(default="WEB", min_length=1, max_length=40)
    exact_partnumber_match: bool = False
    evidence_text: str | None = Field(default=None, max_length=2000)


class ResearchRequestV1(_StrictModel):
    schema_version: Literal[1] = 1
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    created_at: datetime
    product_work_item_id: int = Field(gt=0)
    product_work_job_id: int = Field(gt=0)
    work_type: WorkType
    partnumber: str = Field(min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=200)
    category_code: str | None = Field(default=None, max_length=80)
    requested_fields: list[str] = Field(default_factory=list, max_length=50)
    research_policy: ResearchPolicyV1 = Field(default_factory=ResearchPolicyV1)

    @field_validator("partnumber")
    @classmethod
    def normalize_partnumber(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")
        return normalized

    @field_validator("brand", "model", "category_code")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("requested_fields")
    @classmethod
    def normalize_requested_fields(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output


class ResearchResultV1(_StrictModel):
    schema_version: Literal[1] = 1
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    partnumber: str = Field(min_length=1, max_length=160)
    work_type: WorkType
    researched_at: datetime
    status: ResultStatus
    sources: list[ResearchSourceV1] = Field(default_factory=list, max_length=10)
    image_candidates: list[ImageCandidateV1] = Field(default_factory=list, max_length=10)
    identity_candidates: list[IdentityCandidateV1] = Field(default_factory=list, max_length=10)
    technical_candidates: list[TechnicalCandidateV1] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=4000)

    @field_validator("partnumber")
    @classmethod
    def normalize_partnumber(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError("partnumber is required")
        return normalized
