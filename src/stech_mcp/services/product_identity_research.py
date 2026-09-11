from __future__ import annotations

from typing import Any, Callable

from stech_mcp.services.identity_barcode_extractor import validate_gtin
from stech_mcp.services.research.search_provider import SearchProviderNotConfigured


ProgressCallback = Callable[[str, int], None]
IDENTITY_FIELDS=("ean","upc","gtin")
_MANUFACTURER_DOMAINS={
    "ACER":("acer.com",),"APPLE":("apple.com",),"ASUS":("asus.com",),
    "CANON":("canon.com",),"EPSON":("epson.com",),"HP":("hp.com",),
    "JBL":("jbl.com",),"KINGSTON":("kingston.com",),"LENOVO":("lenovo.com",),
    "LOGITECH":("logitech.com",),"MSI":("msi.com",),"SAMSUNG":("samsung.com",),
    "ULEFONE":("ulefone.com",),
}


def _row_value(row: dict[str,Any]) -> Any:
    if row.get("value_text") not in (None,""): return row.get("value_text")
    if row.get("value_number") is not None: return row.get("value_number")
    return row.get("value")


class ProductIdentityResearchService:
    """Research EAN/UPC/GTIN without mutating distributor stock/price rows.

    Only exact-PN evidence from known official manufacturer domains is eligible
    for automatic promotion. Approved identity facts are stored in the shared
    STECH-MCP enrichment/evidence path and can be reused by every channel.
    """
    def __init__(self,*,product_repository,enrichment_repository,candidate_repository,promotion_service,search_provider,source_document_service,fact_extractor,audit_repository=None):
        self.product_repository=product_repository;self.enrichment_repository=enrichment_repository
        self.candidate_repository=candidate_repository;self.promotion_service=promotion_service
        self.search_provider=search_provider;self.source_document_service=source_document_service
        self.fact_extractor=fact_extractor;self.audit_repository=audit_repository

    @staticmethod
    def _brand_domains(product:dict[str,Any])->tuple[str,...]:
        brand=str(product.get("marca") or product.get("brand") or "").strip().upper()
        return _MANUFACTURER_DOMAINS.get(brand,())

    def _approved(self,pn:str)->dict[str,str]:
        rows=self.enrichment_repository.get_approved(pn,list(IDENTITY_FIELDS)) or []
        out={}
        for row in rows:
            field=str(row.get("field_code") or "").strip().lower()
            value=str(_row_value(row) or "").strip()
            if field in IDENTITY_FIELDS and validate_gtin(value): out[field]=value
        return out

    @staticmethod
    def _direct(product:dict[str,Any])->dict[str,str]:
        out={}
        for field in IDENTITY_FIELDS:
            value=str(product.get(field) or "").strip()
            if value and validate_gtin(value): out[field]=value
        return out

    def _persist_candidates(self,pn:str,candidates:list[dict[str,Any]])->list[dict[str,Any]]:
        out=[]
        for row in candidates:
            field=str(row.get("field_code") or "").strip().lower()
            value=str(row.get("normalized_value") or "").strip()
            if field not in IDENTITY_FIELDS or not validate_gtin(value): continue
            saved=self.candidate_repository.add(
                partnumber=pn,field_code=field,raw_value=row.get("raw_value"),normalized_value=value,
                unit=None,source_type=str(row.get("source_type") or "").upper(),source_name=row.get("source_name"),
                source_url=row.get("source_url"),source_partnumber=row.get("source_partnumber"),
                evidence_text=row.get("evidence_text"),page_number=row.get("page_number"),
                confidence_rank=str(row.get("confidence_rank") or "").upper(),state="PENDING")
            out.append({**row,**saved,"normalized_value":value})
        return out

    def _audit(self,pn:str,detail:dict[str,Any])->None:
        recorder=getattr(self.audit_repository,"add_audit_event",None)
        if callable(recorder): recorder(partnumber=pn,event_type="IDENTITY_RESEARCH_V1",actor_source="STECH_IDENTITY_WORKER",channel=None,detail=detail)

    def research(self,partnumber:str,requested_fields:list[str]|None=None,progress:ProgressCallback|None=None)->dict[str,Any]:
        progress=progress or (lambda *_:None)
        pn=str(partnumber or "").strip().upper()
        if not pn: raise ValueError("partnumber is required")
        product=self.product_repository.get_by_partnumber(pn)
        if product is None: raise LookupError(f"product not found: {pn}")
        requested=[]
        for raw in requested_fields or IDENTITY_FIELDS:
            field=str(raw or "").strip().lower()
            if field in IDENTITY_FIELDS and field not in requested: requested.append(field)
        if not requested: requested=list(IDENTITY_FIELDS)

        verified={**self._direct(product),**self._approved(pn)}
        if verified:
            result={"state":"COMPLETED","partnumber":pn,"verified_fields":verified,"promoted_fields":[],"conflicts":[],"sources_consulted":[],"error_code":None}
            self._audit(pn,result); return result

        domains=self._brand_domains(product)
        if not domains:
            result={"state":"PARTIAL","partnumber":pn,"verified_fields":{},"promoted_fields":[],"conflicts":[],"sources_consulted":[],"error_code":"NO_TRUSTED_IDENTITY_SOURCE"}
            self._audit(pn,result); return result

        progress("RESEARCHING",30)
        persisted=[];sources=[];search_error=None;seen=set()
        try:
            # Search all common barcode labels together; the extractor decides
            # the actual type and rejects invalid checksums/unlabeled numbers.
            query=f'"{pn}" EAN UPC GTIN'
            for hit in self.search_provider.search(query,domains=domains,limit=8)[:5]:
                if hit.url in seen: continue
                seen.add(hit.url);progress("READING_DOCUMENTS",50)
                document=self.source_document_service.ingest(hit.url,pn,"MANUFACTURER")
                sources.append(hit.url)
                extracted=self.fact_extractor.extract(document,requested,pn)
                # Exact PN is mandatory for identity auto-promotion.
                extracted=[row for row in extracted if str(row.get("source_partnumber") or "").strip().upper()==pn]
                persisted.extend(self._persist_candidates(pn,extracted))
        except SearchProviderNotConfigured:
            search_error="SEARCH_PROVIDER_NOT_CONFIGURED"

        progress("VALIDATING",75)
        promotion={"promoted":{},"conflicts":[]}
        if persisted: promotion=self.promotion_service.evaluate_and_promote(pn,persisted)
        conflicts=list(promotion.get("conflicts") or [])
        verified={**self._direct(product),**self._approved(pn)}
        if conflicts:
            state="REVIEW_REQUIRED";error_code="IDENTITY_CONFLICT"
        elif verified:
            state="COMPLETED";error_code=None
        else:
            state="PARTIAL";error_code=search_error or "NO_VERIFIED_IDENTITY_FOUND"
        progress("REBUILDING_PRODUCT_MASTER",95)
        result={"state":state,"partnumber":pn,"verified_fields":verified,"promoted_fields":list((promotion.get("promoted") or {}).keys()),"conflicts":conflicts,"sources_consulted":sources,"error_code":error_code}
        self._audit(pn,result);return result
