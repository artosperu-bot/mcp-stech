from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

from stech_mcp.services.identity_barcode_extractor import validate_gtin
from stech_mcp.services.identity_consensus import evaluate_identity_consensus
from stech_mcp.services.identity_context import build_identity_context
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
_AUTHORIZED_DISTRIBUTOR_DOMAINS=(
    "deltron.com.pe",
    "ingrammicro.com",
    "ingrammicro.com.pe",
    "intcomex.com",
)


def _row_value(row: dict[str,Any]) -> Any:
    if row.get("value_text") not in (None,""): return row.get("value_text")
    if row.get("value_number") is not None: return row.get("value_number")
    return row.get("value")


def _url_matches_domains(url:str,domains:tuple[str,...])->bool:
    host=str(urlparse(str(url or "")).hostname or "").strip().lower().rstrip(".")
    if not host:return False
    return any(host==domain.lower() or host.endswith("."+domain.lower()) for domain in domains)


def _quoted(value: Any) -> str | None:
    text=str(value or "").strip()
    if not text:return None
    return '"'+text.replace('"',' ')+'"'


def _candidate_fields(candidates:list[dict[str,Any]])->dict[str,list[str]]:
    out:dict[str,list[str]]={}
    for row in candidates:
        field=str(row.get("field_code") or "").strip().lower()
        value=str(row.get("normalized_value") or "").strip()
        if field not in IDENTITY_FIELDS or not value:
            continue
        values=out.setdefault(field,[])
        if value not in values:
            values.append(value)
    return out


def _research_queries(pn: str, context: dict[str,Any]) -> list[str]:
    """Create conservative discovery queries from already-known product facts.

    Context improves URL discovery only. Destination evidence is still gated by
    exact PN and trusted source domains before a barcode can be promoted.
    """
    queries=[f'"{pn}" EAN UPC GTIN']
    brand=str(context.get("brand") or "").strip().upper()
    if brand:
        queries.append(f'"{brand}" "{pn}"')

    variant=[]
    processor=_quoted(context.get("processor"))
    if processor: variant.append(processor)
    ram=context.get("ram_gb")
    if ram not in (None,""): variant.append(f'"{ram}GB RAM"')
    storage=context.get("storage_gb")
    storage_type=str(context.get("storage_type") or "").strip().upper()
    if storage not in (None,""):
        storage_label=f"{storage}GB"+(f" {storage_type}" if storage_type else "")
        variant.append(_quoted(storage_label) or "")
    if variant:
        queries.append(" ".join([f'"{pn}"',*variant]))

    model=_quoted(context.get("model"))
    if model and brand:
        queries.append(" ".join([f'"{brand}"',f'"{pn}"',model,"EAN UPC GTIN"]))

    out=[]
    for query in queries:
        normalized=" ".join(str(query or "").split())
        if normalized and normalized not in out: out.append(normalized)
    return out


class ProductIdentityResearchService:
    """Research EAN/UPC/GTIN without mutating distributor stock/price rows.

    Manufacturer evidence is tried first. If it yields no exact-PN barcode,
    known authorized distributor domains are consulted as a second layer.
    Identity promotion is gated by Rule B consensus before candidates reach the
    generic fact promotion service.
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
            source_pn=str(row.get("source_partnumber") or "").strip().upper()
            source_type=str(row.get("source_type") or "").strip().upper()
            confidence=str(row.get("confidence_rank") or "").strip().upper()
            if source_pn!=pn or source_type not in {"MANUFACTURER","OFFICIAL_DOCUMENT","AUTHORIZED_DISTRIBUTOR"} or confidence not in {"A1","A2","B"}:
                continue
            saved=self.candidate_repository.add(
                partnumber=pn,field_code=field,raw_value=row.get("raw_value"),normalized_value=value,
                unit=None,source_type=source_type,source_name=row.get("source_name"),
                source_url=row.get("source_url"),source_partnumber=source_pn,
                evidence_text=row.get("evidence_text"),page_number=row.get("page_number"),
                confidence_rank=confidence,state="PENDING")
            out.append({**row,**saved,"normalized_value":value,"source_partnumber":source_pn,"source_type":source_type,"confidence_rank":confidence})
        return out

    def _audit(self,pn:str,detail:dict[str,Any])->None:
        recorder=getattr(self.audit_repository,"add_audit_event",None)
        if callable(recorder): recorder(partnumber=pn,event_type="IDENTITY_RESEARCH_V1",actor_source="STECH_IDENTITY_WORKER",channel=None,detail=detail)

    def research(self,partnumber:str,requested_fields:list[str]|None=None,progress:ProgressCallback|None=None)->dict[str,Any]:
        progress=progress or (lambda *_:None)
        pn=str(partnumber or "").strip().upper()
        if not pn: raise ValueError("partnumber is required")

        progress("ANALYZING_MISSING_FIELDS",10)
        product=self.product_repository.get_by_partnumber(pn)
        if product is None: raise LookupError(f"product not found: {pn}")
        context=build_identity_context(product)
        requested=[]
        for raw in requested_fields or IDENTITY_FIELDS:
            field=str(raw or "").strip().lower()
            if field in IDENTITY_FIELDS and field not in requested: requested.append(field)
        if not requested: requested=list(IDENTITY_FIELDS)

        verified={**self._direct(product),**self._approved(pn)}
        if verified:
            result={
                "state":"COMPLETED","result_code":"YA_VERIFICADO","partnumber":pn,
                "identity_context":context,"verified_fields":verified,"candidate_fields":{},
                "promoted_fields":[],"decision":"PROMOTED",
                "evidence_summary":{"strong_source_count":0,"has_primary":False,"has_authorized_distributor":False,"already_verified":True},
                "conflicts":[],"sources_consulted":[],"search_queries":[],"error_code":None,
            }
            self._audit(pn,result); return result

        domains=self._brand_domains(product)
        if not domains:
            result={
                "state":"PARTIAL","result_code":"NO_VERIFIED_IDENTITY_FOUND","partnumber":pn,
                "identity_context":context,"verified_fields":{},"candidate_fields":{},
                "promoted_fields":[],"decision":"NO_RESULT",
                "evidence_summary":{"strong_source_count":0,"has_primary":False,"has_authorized_distributor":False},
                "conflicts":[],"sources_consulted":[],"search_queries":[],"error_code":"NO_TRUSTED_IDENTITY_SOURCE",
            }
            self._audit(pn,result); return result

        progress("RESEARCHING",30)
        persisted=[];sources=[];search_error=None;seen=set();queries=_research_queries(pn,context)

        def research_layer(layer_domains:tuple[str,...],source_type:str)->None:
            for query in queries:
                for hit in self.search_provider.search(query,domains=layer_domains,limit=8)[:5]:
                    if hit.url in seen: continue
                    seen.add(hit.url)
                    if not _url_matches_domains(hit.url,layer_domains): continue
                    progress("READING_DOCUMENTS",50)
                    document=self.source_document_service.ingest(hit.url,pn,source_type)
                    sources.append(hit.url)
                    extracted=self.fact_extractor.extract(document,requested,pn)
                    extracted=[row for row in extracted if str(row.get("source_partnumber") or "").strip().upper()==pn]
                    persisted.extend(self._persist_candidates(pn,extracted))

        try:
            research_layer(domains,"MANUFACTURER")
            if not persisted:
                research_layer(_AUTHORIZED_DISTRIBUTOR_DOMAINS,"AUTHORIZED_DISTRIBUTOR")
        except SearchProviderNotConfigured:
            search_error="SEARCH_PROVIDER_NOT_CONFIGURED"

        progress("VALIDATING",75)
        consensus=evaluate_identity_consensus(pn,persisted)
        promotion={"promoted":{},"conflicts":[]}
        if consensus.get("decision")=="PROMOTED":
            promotion=self.promotion_service.evaluate_and_promote(pn,list(consensus.get("promotable_candidates") or []))

        conflicts=list(consensus.get("conflicts") or [])+list(promotion.get("conflicts") or [])
        verified={**self._direct(product),**self._approved(pn)}
        decision=str(consensus.get("decision") or "NO_RESULT").strip().upper()
        if conflicts:
            state="REVIEW_REQUIRED";result_code="REVIEW_REQUIRED";error_code="IDENTITY_CONFLICT";decision="CONFLICT"
        elif verified:
            state="COMPLETED";result_code="VERIFICADO";error_code=None;decision="PROMOTED"
        else:
            state="PARTIAL";result_code="NO_VERIFIED_IDENTITY_FOUND";error_code=search_error or "NO_VERIFIED_IDENTITY_FOUND"
        progress("REBUILDING_PRODUCT_MASTER",95)
        result={
            "state":state,"result_code":result_code,"partnumber":pn,"identity_context":context,
            "verified_fields":verified,"candidate_fields":_candidate_fields(persisted),
            "promoted_fields":list((promotion.get("promoted") or {}).keys()),"decision":decision,
            "evidence_summary":dict(consensus.get("evidence_summary") or {}),
            "conflicts":conflicts,"sources_consulted":sources,"search_queries":queries,"error_code":error_code,
        }
        self._audit(pn,result);return result
