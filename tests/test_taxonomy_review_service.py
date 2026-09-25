from stech_mcp.services.taxonomy_review import TaxonomyReviewService


class FakeRepository:
    def __init__(self):
        self.calls = []

    def sync_missing(self, *, limit, distributor):
        self.calls.append(("sync", limit, distributor))
        return {"detected": 2, "inserted": 2, "refreshed": 0}

    def list_reviews(self, *, status, limit):
        self.calls.append(("list", status, limit))
        return [{"taxonomy_review_id": 1}, {"taxonomy_review_id": 2}]

    def count_reviews(self, *, status):
        self.calls.append(("count", status))
        return 1234

    def list_missing(self, *, limit, distributor):
        self.calls.append(("missing", limit, distributor))
        return [{"producto_distribuidor_id": 101}]

    def taxonomy_catalog(self, *, limit):
        self.calls.append(("catalog", limit))
        return [
            {"category": "COMPUTADORAS", "subcategory": "NOTEBOOK", "product_count": 10},
            {"category": "ALMACENAMIENTO", "subcategory": "SSD INTERNO", "product_count": 7},
        ]

    def get_review(self, review_id):
        return {"taxonomy_review_id": review_id}

    def propose(self, review_id, **kwargs):
        return {"taxonomy_review_id": review_id, "status": "PROPOSED", **kwargs}

    def approve(self, review_id, *, approved_by):
        return {"taxonomy_review_id": review_id, "status": "APPROVED", "approved_by": approved_by}

    def reject(self, review_id, *, rejected_by, reason=None):
        return {
            "taxonomy_review_id": review_id,
            "status": "REJECTED",
            "approved_by": rejected_by,
            "reason": reason,
        }

    def sql_preview(self, review_id):
        return {
            "taxonomy_review_id": review_id,
            "guard": "ONLY_MISSING_OR_GENERIC_FIELDS_AND_APPROVED_REVIEW",
        }

    def apply_review(self, review_id, *, applied_by):
        return {"taxonomy_review_id": review_id, "status": "APPLIED", "applied_by": applied_by}


def test_sync_queues_only_unresolved_products():
    repo = FakeRepository()
    service = TaxonomyReviewService(repo)

    out = service.sync(limit=50, distributor="DELTRON")

    assert out["detected"] == 2
    assert out["pending_count"] == 1234
    assert out["pending_sample_count"] == 2
    assert len(out["pending_sample"]) == 2
    assert repo.calls[0] == ("sync", 50, "DELTRON")


def test_catalog_exposes_existing_pairs_for_ai_context():
    service = TaxonomyReviewService(FakeRepository())

    out = service.catalog(limit=100)

    assert out["category_count"] == 2
    assert out["pair_count"] == 2
    assert "COMPUTADORAS" in out["categories"]


def test_apply_is_separate_from_propose_and_approve():
    service = TaxonomyReviewService(FakeRepository())

    proposed = service.propose(
        7,
        category="VIDEO",
        subcategory="CAPTURADORA",
        confidence="ALTA",
        reason="Nombre y especificaciones identifican una capturadora HDMI.",
        evidence=["nombre", "especificaciones"],
        proposed_by="CHATGPT",
    )
    approved = service.approve(7, approved_by="STEVE")
    applied = service.apply(7, applied_by="CHATGPT")

    assert proposed["review"]["status"] == "PROPOSED"
    assert approved["review"]["status"] == "APPROVED"
    assert applied["review"]["status"] == "APPLIED"


def test_batch_propose_approve_apply_preserves_review_stages():
    service = TaxonomyReviewService(FakeRepository())

    proposed = service.propose_batch(
        [
            {
                "review_id": 41,
                "category": "REPUESTOS",
                "subcategory": "REPUESTO PARA NOTEBOOK",
                "confidence": "MEDIA",
                "reason": "Pieza interna ASUS para notebook.",
                "evidence": ["product_name"],
            },
            {
                "review_id": 48,
                "category": "COMPONENTES",
                "subcategory": "FUENTE DE PODER",
                "confidence": "ALTA",
                "reason": "PSU ASUS.",
                "evidence": ["product_name:PSU"],
            },
        ],
        proposed_by="CHATGPT",
    )
    approved = service.approve_batch([41, 48], approved_by="STEVE")
    applied = service.apply_batch([41, 48], applied_by="CHATGPT")

    assert proposed["proposed_count"] == 2
    assert proposed["error_count"] == 0
    assert approved["approved_count"] == 2
    assert applied["applied_count"] == 2


def test_batch_rejects_duplicate_review_id_without_aborting_other_items():
    service = TaxonomyReviewService(FakeRepository())

    out = service.propose_batch(
        [
            {
                "review_id": 41,
                "category": "REPUESTOS",
                "subcategory": "REPUESTO PARA NOTEBOOK",
                "confidence": "ALTA",
                "reason": "pieza",
            },
            {
                "review_id": 41,
                "category": "REPUESTOS",
                "subcategory": "REPUESTO PARA NOTEBOOK",
                "confidence": "ALTA",
                "reason": "duplicado",
            },
        ]
    )

    assert out["proposed_count"] == 1
    assert out["error_count"] == 1
