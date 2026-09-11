from decimal import Decimal

from stech_mcp.services.product_prepare import ProductPrepareService, _approved_identity


class ProductRepo:
    def __init__(self, row): self.row=row
    def get_by_partnumber(self, partnumber): return self.row

class EnrichmentRepo:
    def __init__(self, rows=None): self.rows=rows or []
    def get_approved(self, partnumber, field_codes=None): return self.rows
    def get_package_override(self, partnumber): return None

class PackagingRepo:
    def find_rule(self, **kwargs): return None

class MasterRepo:
    def __init__(self): self.snapshot=None;self.audit=[]
    def list_images(self, partnumber): return []
    def upsert_master(self, snapshot): self.snapshot=dict(snapshot);return dict(snapshot)
    def replace_draft(self, **kwargs): return {"draft_version":1,"field_count":len(kwargs.get("payload") or {})}
    def add_audit_event(self, **kwargs): self.audit.append(kwargs)


def test_approved_identity_prefers_enrichment_over_source_value():
    rows=[{"field_code":"ean","value_text":"4006381333931"},{"field_code":"upc","value_text":"012345678905"}]
    assert _approved_identity(rows,"ean","OLD")=="4006381333931"
    assert _approved_identity(rows,"upc",None)=="012345678905"


def test_prepare_writes_approved_ean_into_master_snapshot():
    product={"part_number":"PN1","nombre":"Notebook PN1","marca":"LENOVO","ean":None,"upc":None,"atributos_json":{},"producto_distribuidor_id":1}
    enrich=EnrichmentRepo([{"field_code":"ean","value_text":"4006381333931","is_approved":True}])
    master=MasterRepo()
    svc=ProductPrepareService(product_repository=ProductRepo(product),enrichment_repository=enrich,packaging_rule_repository=PackagingRepo(),product_master_repository=master)
    out=svc.prepare("PN1")
    assert out["found"] is True
    assert master.snapshot["ean"]=="4006381333931"


def test_approved_identity_number_compacts_without_scientific_notation():
    rows=[{"field_code":"gtin","value_number":Decimal("12345678901234")}]
    assert _approved_identity(rows,"gtin",None)=="12345678901234"
