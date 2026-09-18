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
_TRUSTED_RETAILER_DOMAINS=(
    "ripley.com.pe",
    "falabella.com.pe",
    "coolbox.pe",
    "oechsle.pe",
    "plazavea.com.pe",
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
    """Return at most two high-value exact-PN discovery queries.

    Bing is free but noisy. We keep its discovery work bounded and focused so a
    failed Bing pass can fall through quickly to the Tavily credit budget.
    Destination pages still need exact-PN evidence before any barcode is kept.
    """
    brand=_quoted(str(context.get("brand") or "").strip().upper())
    model=_quoted(context.get("model"))
    primary=" ".join(value for value in [f'"{pn}"',brand or "","EAN UPC GTIN barcode"] if value)
    secondary=" ".join(value for value in [f'"{pn}"',brand or "",model or "","barcode product code"] if value)

    out=[]
    for query in (primary,secondary):
        normalized=" ".join(str(query or "").split())
        if normalized and normalized not in out: out.append(normalized)
    return out[:2]


def _hit_mentions_partnumber(hit: Any, pn: str) -> bool:
    haystack=" ".join([
        str(getattr(hit,"title","") or ""),
        str(getattr(hit,"url","") or ""),
        str(getattr(hit,"description","") or ""),
    ])
    return pn.casefold() in haystack.casefold()


def _source_type_for_url(url: str, manufacturer_domains: tuple[str,...]) -> str | None:
    if _url_matches_domains(url,manufacturer_domains): return "MANUFACTURER"
    if _url_matches_domains(url,_AUTHORIZED_DISTRIBUTOR_DOMAINS): return "AUTHORIZED_DISTRIBUTOR"
    if _url_matches_domains(url,_TRUSTED_RETAILER_DOMAINS): return "TRUSTED_RETAILER"
    return None


def _first_candidate_value(candidates:list[dict[str,Any]])->str|None:
    for row in candidates:
        value=str(row.get("normalized_value") or "").strip()
        if value and validate_gtin(value): return value
    return None


class ProductIdentityResearchService:
    """Research EAN/UPC/GTIN without mutating distributor stock/price rows.

    Manufacturer evidence is tried first, authorized distributors second, and
    trusted retailers last. Retailer evidence is retained only as candidate
    evidence; Rule B consensus is the only gate that can reach promotion.
    """
    def __init__(
        self,*,
        product_repository,enrichment_repository,candidate_repository,promotion_service,
        search_provider,source_document_service,fact_extractor,audit_repository=None,
        fallback_search_provider=None,max_fallback_searches:int=2,
    ):
        self.product_repository=product_repository;self.enrichment_repository=enrichment_repository
        self.candidate_repository=candidate_repository;self.promotion_service=promotion_service
        self.search_provider=search_provider;self.fallback_search_provider=fallback_search_provider
        self.max_fallback_searches=max(0,min(int(max_fallback_searches),2))
        self.source_document_service=source_document_service
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
        allowed={
            "MANUFACTURER":{"A1","A2"},
            "OFFICIAL_DOCUMENT":{"A1","A2"},
            "AUTHORIZED_DISTRIBUTOR":{"A1","A2","B"},
            "TRUSTED_RETAILER":{"C"},
        }
        for row in candidates:
            field=str(row.get("field_code") or "").strip().lower()
            value=str(row.get("normalized_value") or "").strip()
            if field not in IDENTITY_FIELDS or not validate_gtin(value): continue
            source_pn=str(row.get("source_partnumber") or "").strip().upper()
            source_type=str(row.get("source_type") or "").strip().upper()
            confidence=str(row.get("confidence_rank") or "").strip().upper()
            if source_pn!=pn or confidence not in allowed.get(source_type,set()):
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
                "conflicts":[],"sources_consulted":[],"search_queries":[],"fallback_queries":[],"fallback_searches_used":0,"error_code":None,
            }
            self._audit(pn,result); return result

        domains=self._brand_domains(product)
        if not domains:
            result={
                "state":"PARTIAL","result_code":"NO_VERIFIED_IDENTITY_FOUND","partnumber":pn,
                "identity_context":context,"verified_fields":{},"candidate_fields":{},
                "promoted_fields":[],"decision":"NO_RESULT",
                "evidence_summary":{"strong_source_count":0,"has_primary":False,"has_authorized_distributor":False},
                "conflicts":[],"sources_consulted":[],"search_queries":[],"fallback_queries":[],"fallback_searches_used":0,"error_code":"NO_TRUSTED_IDENTITY_SOURCE",
            }
            self._audit(pn,result); return result

        progress("RESEARCHING",30)
        persisted=[];sources=[];search_error=None;seen=set();queries=_research_queries(pn,context)
        fallback_queries=[];fallback_searches_used=0
        all_domains=tuple(dict.fromkeys([*domains,*_AUTHORIZED_DISTRIBUTOR_DOMAINS,*_TRUSTED_RETAILER_DOMAINS]))

        def ingest_hits(hits:list[Any],allowed_domains:tuple[str,...],forced_source_type:str|None=None)->int:
            accepted=0
            for hit in hits:
                url=str(getattr(hit,"url","") or "").strip()
                if not url or url in seen: continue
                # Bing can return a trusted host's generic home/support page even
                # for a quoted PN. Do not spend document reads on those results.
                if not _hit_mentions_partnumber(hit,pn): continue
                if not _url_matches_domains(url,allowed_domains): continue
                source_type=forced_source_type or _source_type_for_url(url,domains)
                if not source_type: continue
                seen.add(url);accepted+=1
                progress("READING_DOCUMENTS",50)
                document=self.source_document_service.ingest(url,pn,source_type)
                sources.append(url)
                extracted=self.fact_extractor.extract(document,requested,pn)
                extracted=[row for row in extracted if str(row.get("source_partnumber") or "").strip().upper()==pn]
                persisted.extend(self._persist_candidates(pn,extracted))
            return accepted

        def research_layer(layer_domains:tuple[str,...],source_type:str)->None:
            for query in queries:
                hits=self.search_provider.search(query,domains=layer_domains,limit=8)
                ingest_hits(list(hits)[:5],layer_domains,source_type)
                current=evaluate_identity_consensus(pn,persisted)
                if current.get("decision") in {"PROMOTED","CONFLICT"}:
                    return

        def tavily_once(query:str)->None:
            nonlocal fallback_searches_used,search_error
            if self.fallback_search_provider is None or fallback_searches_used>=self.max_fallback_searches:
                return
            normalized=" ".join(str(query or "").split())
            if not normalized or normalized in fallback_queries:
                return
            fallback_queries.append(normalized)
            fallback_searches_used+=1
            try:
                hits=self.fallback_search_provider.search(normalized,domains=all_domains,limit=10)
            except SearchProviderNotConfigured:
                search_error="FALLBACK_SEARCH_PROVIDER_NOT_CONFIGURED"
                return
            ingest_hits(list(hits)[:10],all_domains,None)

        try:
            # Free discovery first, preserving source trust order.
            research_layer(domains,"MANUFACTURER")
            consensus=evaluate_identity_consensus(pn,persisted)
            if consensus.get("decision") not in {"PROMOTED","CONFLICT"}:
                research_layer(_AUTHORIZED_DISTRIBUTOR_DOMAINS,"AUTHORIZED_DISTRIBUTOR")
                consensus=evaluate_identity_consensus(pn,persisted)
            if consensus.get("decision") not in {"PROMOTED","CONFLICT"}:
                research_layer(_TRUSTED_RETAILER_DOMAINS,"TRUSTED_RETAILER")
                consensus=evaluate_identity_consensus(pn,persisted)

            # Tavily is a paid-credit fallback. One Basic Search = one credit.
            # The service hard-caps this block at two calls per PN.
            if consensus.get("decision") not in {"PROMOTED","CONFLICT"}:
                candidate=_first_candidate_value(persisted)
                tavily_once(f'"{pn}" "{candidate}"' if candidate else queries[0])
                consensus=evaluate_identity_consensus(pn,persisted)

            if consensus.get("decision") not in {"PROMOTED","CONFLICT"} and fallback_searches_used<self.max_fallback_searches:
                candidate=_first_candidate_value(persisted)
                confirmation=f'"{pn}" "{candidate}"' if candidate else (queries[1] if len(queries)>1 else f'"{pn}" barcode EAN UPC GTIN')
                if confirmation in fallback_queries:
                    confirmation=queries[1] if len(queries)>1 and queries[1] not in fallback_queries else f'"{pn}" EAN UPC GTIN product code'
                tavily_once(confirmation)
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
            "conflicts":conflicts,"sources_consulted":sources,"search_queries":queries,
            "fallback_queries":fallback_queries,"fallback_searches_used":fallback_searches_used,"error_code":error_code,
        }
        self._audit(pn,result);return result
