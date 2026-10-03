from stech_mcp.services.handlers.research_images import ResearchImagesHandler


class Engine:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def research(self, pn, category_code=None, target_count=None):
        self.calls.append((pn, category_code, target_count))
        return dict(self.result)


def call(result, payload=None):
    handler = ResearchImagesHandler(Engine(result))
    item = {"partnumber": "pn1", "input": payload or {}}
    progress = []
    output = handler(item, lambda state, pct: progress.append((state, pct)))
    return output, progress


def test_ready_maps_to_completed():
    output, progress = call({"state": "READY", "candidate_count": 0})
    assert output["status"] == "COMPLETED"
    assert progress[0][0] == "ANALYZING_MISSING_FIELDS"


def test_candidates_map_to_review_required():
    output, _ = call({"state": "REVIEW_REQUIRED", "candidate_count": 3})
    assert output["status"] == "REVIEW_REQUIRED"
    assert output["error_code"] == "IMAGE_REVIEW_REQUIRED"


def test_no_candidates_maps_to_no_data_found():
    output, _ = call({"state": "NO_DATA_FOUND", "candidate_count": 0})
    assert output["status"] == "NO_DATA_FOUND"

class ReadyAfterImport:
    def get(self, pn, category_code=None, channel_code=None):
        return {"state": "READY", "image_count": 4}


class AutoEngine(Engine):
    def __init__(self, result):
        super().__init__(result)
        self.readiness_service = ReadyAfterImport()


class Importer:
    def __init__(self):
        self.ids = []

    def import_candidate(self, candidate_id):
        self.ids.append(candidate_id)
        return {"candidate_id": candidate_id, "state": "IMPORTED"}


def test_trusted_exact_candidate_can_auto_import_and_complete():
    engine = AutoEngine({
        "state": "REVIEW_REQUIRED",
        "candidate_count": 1,
        "candidates": [
            {
                "product_image_candidate_id": 77,
                "partnumber_match": "EXACT",
                "variant_match": "UNKNOWN",
                "confidence_score": 95,
                "source_domain": "support.lenovo.com",
            }
        ],
    })
    importer = Importer()
    handler = ResearchImagesHandler(
        engine,
        candidate_import_service=importer,
        auto_import_exact=True,
        trusted_domains=("lenovo.com",),
    )
    output = handler(
        {"partnumber": "PN1", "input": {"category_code": "LAPTOP"}},
        lambda state, pct: None,
    )

    assert output["status"] == "COMPLETED"
    assert output["imported_count"] == 1
    assert importer.ids == [77]


def test_untrusted_exact_candidate_stays_review_required():
    engine = AutoEngine({
        "state": "REVIEW_REQUIRED",
        "candidate_count": 1,
        "candidates": [
            {
                "product_image_candidate_id": 88,
                "partnumber_match": "EXACT",
                "variant_match": "UNKNOWN",
                "confidence_score": 99,
                "source_domain": "random-marketplace.example",
            }
        ],
    })
    importer = Importer()
    handler = ResearchImagesHandler(
        engine,
        candidate_import_service=importer,
        auto_import_exact=True,
        trusted_domains=("lenovo.com",),
    )
    output = handler({"partnumber": "PN1", "input": {}}, lambda state, pct: None)

    assert output["status"] == "REVIEW_REQUIRED"
    assert importer.ids == []
