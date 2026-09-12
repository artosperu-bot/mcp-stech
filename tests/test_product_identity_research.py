from stech_mcp.services.product_identity_research import ProductIdentityResearchService
from stech_mcp.services.research.search_provider import SearchResult


class Products:
    def __init__(self, product): self.product=product
    def get_by_partnumber(self, pn): return self.product if pn=="PN1" else None

class Enrichments:
    def __init__(self, rows=None): self.rows=list(rows or [])
    def get_approved(self, pn, field_codes=None):
        wanted=set(field_codes or [])
        return [r for r in self.rows if not wanted or r.get("field_code") in wanted]

class Search:
    def __init__(self, results): self.results=list(results); self.calls=[]
    def search(self, query, domains=(), limit=5):
        self.calls.append((query, tuple(domains), limit)); return list(self.results)

class Sources:
    def ingest(self, url, partnumber, source_type):
        return {"url":url,"source_type":source_type,"confidence_rank":"A1","title":"Official","pages":[{"page":1,"text":"PN1 EAN: 4006381333931"}]}

class Extractor:
    def extract(self, doc, fields, pn):
        return [{"field_code":"ean","raw_value":"4006381333931","normalized_value":"4006381333931","unit":None,"source_type":"MANUFACTURER","source_name":"Official","source_url":doc["url"],"source_partnumber":pn,"evidence_text":"PN1 EAN: 4006381333931","page_number":1,"confidence_rank":"A1","status":"PENDING"}]

class Candidates:
    def __init__(self): self.rows=[]
    def add(self, **row): self.rows.append(dict(row)); return {"product_fact_candidate_id":len(self.rows),**row}

class Promotion:
    def __init__(self, enrichments): self.enrichments=enrichments
    def evaluate_and_promote(self, pn, candidates):
        self.enrichments.rows.append({"field_code":"ean","value_text":"4006381333931","is_approved":True,"confidence_grade":"A1"})
        return {"state":"COMPLETED","promoted":{"ean":"4006381333931"},"conflicts":[]}

class ConflictPromotion:
    def evaluate_and_promote(self, pn, candidates):
        return {"state":"REVIEW_REQUIRED","promoted":{},"conflicts":[{"field_code":"ean","reason":"EQUAL_STRENGTH_CONFLICT"}]}

class Audit:
    def add_audit_event(self, **kwargs): pass


def build(product, search_results=None, rows=None, promotion=None):
    enrich=Enrichments(rows)
    return ProductIdentityResearchService(
        product_repository=Products(product), enrichment_repository=enrich,
        candidate_repository=Candidates(), promotion_service=promotion or Promotion(enrich),
        search_provider=Search(search_results or []), source_document_service=Sources(),
        fact_extractor=Extractor(), audit_repository=Audit(),
    )


def test_existing_valid_ean_skips_web_research_and_reports_already_verified():
    svc=build({"part_number":"PN1","marca":"LENOVO","ean":"4006381333931"})
    progress=[]
    out=svc.research("PN1",progress=lambda state,pct:progress.append((state,pct)))
    assert out["state"]=="COMPLETED"
    assert out["result_code"]=="YA_VERIFICADO"
    assert out["verified_fields"]["ean"]=="4006381333931"
    assert svc.search_provider.calls==[]
    assert progress==[("ANALYZING_MISSING_FIELDS",10)]


def test_missing_ean_uses_only_known_official_brand_domain_and_promotes_exact_pn():
    svc=build({"part_number":"PN1","marca":"LENOVO","ean":None,"upc":None},[SearchResult("Official","https://support.lenovo.com/pn1","spec")])
    progress=[]
    out=svc.research("PN1",progress=lambda state,pct:progress.append((state,pct)))
    assert out["state"]=="COMPLETED"
    assert out["result_code"]=="VERIFICADO"
    assert out["verified_fields"]["ean"]=="4006381333931"
    assert svc.search_provider.calls
    assert all("lenovo.com" in domains for _,domains,_ in svc.search_provider.calls)
    assert progress[0]==("ANALYZING_MISSING_FIELDS",10)
    assert progress[-1]==("REBUILDING_PRODUCT_MASTER",95)


def test_off_domain_hit_is_not_treated_as_manufacturer_evidence():
    svc=build(
        {"part_number":"PN1","marca":"LENOVO","ean":None,"upc":None},
        [SearchResult("Marketplace result","https://market.example/pn1","PN1 EAN: 4006381333931")],
    )
    out=svc.research("PN1")
    assert out["state"]=="PARTIAL"
    assert out["result_code"]=="NO_VERIFIED_IDENTITY_FOUND"
    assert out["verified_fields"]=={}
    assert out["sources_consulted"]==[]


def test_unknown_brand_does_not_broad_search_or_fake_success():
    svc=build({"part_number":"PN1","marca":"UNKNOWN","ean":None,"upc":None},[SearchResult("Random","https://market.example/pn1","x")])
    out=svc.research("PN1")
    assert out["state"]=="PARTIAL"
    assert out["result_code"]=="NO_VERIFIED_IDENTITY_FOUND"
    assert out["error_code"]=="NO_TRUSTED_IDENTITY_SOURCE"
    assert svc.search_provider.calls==[]


def test_conflict_is_review_required_and_never_reported_as_verified():
    conflict=ConflictPromotion()
    svc=build(
        {"part_number":"PN1","marca":"LENOVO","ean":None,"upc":None},
        [SearchResult("Official","https://support.lenovo.com/pn1","spec")],
        promotion=conflict,
    )
    out=svc.research("PN1")
    assert out["state"]=="REVIEW_REQUIRED"
    assert out["result_code"]=="REVIEW_REQUIRED"
    assert out["error_code"]=="IDENTITY_CONFLICT"
    assert out["verified_fields"]=={}
