from stech_mcp.services.product_image_research import ProductImageResearchService
from stech_mcp.services.research.image_search_provider import ImageSearchResult


class Products:
    def get_by_partnumber(self, pn):
        return {
            "part_number": pn,
            "marca": "Lenovo",
            "modelo": "V15",
            "nombre": "Notebook Lenovo V15",
        }


class Local:
    def __init__(self):
        self.calls = []

    def sync(self, pn):
        self.calls.append(pn)
        return {"state": "NO_IMAGES"}


class Readiness:
    def __init__(self, states):
        self.states = list(states)
        self.calls = 0

    def get(self, pn, category_code=None, channel_code=None):
        index = min(self.calls, len(self.states) - 1)
        self.calls += 1
        return self.states[index]


class Provider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query, count=10):
        self.calls.append((query, count))
        return self.rows


class Candidates:
    def __init__(self):
        self.rows = []

    def add_candidate(self, **kwargs):
        self.rows.append(kwargs)
        return {
            "product_image_candidate_id": len(self.rows),
            **kwargs,
            "state": "PENDING",
        }

    def list_for_product(self, pn):
        return []


def test_external_search_not_called_when_local_or_deltron_becomes_ready():
    provider = Provider([])
    candidates = Candidates()
    service = ProductImageResearchService(
        product_repository=Products(),
        local_image_sync_service=Local(),
        readiness_service=Readiness(
            [
                {"state": "NO_IMAGES"},
                {"state": "READY", "recommended_min": 4, "image_count": 4},
            ]
        ),
        candidate_repository=candidates,
        search_provider=provider,
    )
    result = service.research("82yu00xylm")
    assert result["state"] == "READY"
    assert provider.calls == []


def test_missing_images_search_exact_pn_and_persist_candidate():
    row = ImageSearchResult(
        title="Lenovo 82YU00XYLM front",
        image_url="https://img.example/82YU00XYLM.jpg",
        page_url="https://www.lenovo.com/82YU00XYLM",
        thumbnail_url=None,
        width=1200,
        height=900,
        source_domain="lenovo.com",
    )
    provider = Provider([row])
    candidates = Candidates()
    service = ProductImageResearchService(
        product_repository=Products(),
        local_image_sync_service=Local(),
        readiness_service=Readiness(
            [
                {"state": "NO_IMAGES", "recommended_min": 4},
                {"state": "NO_IMAGES", "recommended_min": 4},
            ]
        ),
        candidate_repository=candidates,
        search_provider=provider,
    )
    result = service.research("82yu00xylm")
    assert "82YU00XYLM" in provider.calls[0][0]
    assert "Lenovo" in provider.calls[0][0]
    assert candidates.rows[0]["partnumber_match"] == "EXACT"
    assert candidates.rows[0]["source_url"] == "https://img.example/82YU00XYLM.jpg"
    assert result["candidate_count"] == 1
    assert result["state"] == "REVIEW_REQUIRED"


def test_ambiguous_image_stays_review_candidate():
    row = ImageSearchResult(
        title="Lenovo V15 laptop",
        image_url="https://img.example/generic.jpg",
        page_url="https://shop.example/v15",
        thumbnail_url=None,
        width=1000,
        height=1000,
        source_domain="shop.example",
    )
    candidates = Candidates()
    provider = Provider([row])
    service = ProductImageResearchService(
        product_repository=Products(),
        local_image_sync_service=Local(),
        readiness_service=Readiness(
            [
                {"state": "NO_IMAGES", "recommended_min": 4},
                {"state": "NO_IMAGES", "recommended_min": 4},
            ]
        ),
        candidate_repository=candidates,
        search_provider=provider,
    )
    result = service.research("82YU00XYLM")
    assert candidates.rows[0]["partnumber_match"] == "UNKNOWN"
    assert candidates.rows[0]["exactness_policy"] == "MANUAL_REVIEW"
    assert result["state"] == "REVIEW_REQUIRED"