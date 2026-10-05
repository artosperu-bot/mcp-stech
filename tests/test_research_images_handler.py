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