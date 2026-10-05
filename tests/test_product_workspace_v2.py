from stech_mcp.services.product_workspace_v2 import ProductWorkspaceV2Service


def _deps(technical):
    class Products:
        def get_by_partnumber(self, pn):
            return {"part_number": pn, "marca": "Lenovo", "nombre": "V15", "categoria": "NUEVA"}

    class Images:
        def get(self, pn, category_code=None, channel_code=None):
            return {"state": "NO_IMAGES", "image_count": 0, "recommended_min": 4, "category_code": category_code}

    class ImageCandidates:
        def list_for_product(self, pn):
            return [{"product_image_candidate_id": 1, "state": "PENDING"}]

    class Facts:
        def list_for_product(self, pn):
            return [{"product_fact_candidate_id": 2, "state": "CONFLICT", "field_code": "ram_gb"}]

    class Work:
        def list_for_product(self, pn, limit=20):
            return [{"item_id": 3, "status": "RUNNING", "work_type": "RESEARCH_IMAGES"}]

    return ProductWorkspaceV2Service(
        product_repository=Products(),
        technical_status_service=technical,
        image_readiness_service=Images(),
        image_candidate_repository=ImageCandidates(),
        fact_candidate_repository=Facts(),
        work_repository=Work(),
    )


def test_workspace_v2_groups_master_technical_images_evidence_and_jobs():
    class Technical:
        def get(self, pn):
            return {
                "partnumber": pn,
                "category_code": "LAPTOP",
                "known_fields": {"ram_gb": 16},
                "missing_required": ["cpu_model"],
                "missing_recommended": [],
                "completion_pct": 50,
            }

    result = _deps(Technical()).get("pn1")
    assert result["found"] is True
    assert result["partnumber"] == "PN1"
    assert result["master"]["brand"] == "Lenovo"
    assert result["technical"]["completion_pct"] == 50
    assert result["images"]["readiness"]["state"] == "NO_IMAGES"
    assert result["images"]["candidate_count"] == 1
    assert result["evidence"]["conflict_count"] == 1
    assert result["jobs"][0]["work_type"] == "RESEARCH_IMAGES"


def test_workspace_v2_keeps_images_available_when_category_schema_is_not_configured():
    class Technical:
        def get(self, pn):
            raise LookupError("supported technical category could not be resolved")

    result = _deps(Technical()).get("pn-new")

    assert result["found"] is True
    assert result["technical"]["state"] == "NOT_CONFIGURED"
    assert result["images"]["readiness"]["state"] == "NO_IMAGES"
    assert result["images"]["candidate_count"] == 1
