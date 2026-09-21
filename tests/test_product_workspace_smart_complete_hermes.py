from stech_mcp.tools.product_workspace_v2 import register_product_workspace_v2_tools


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorate(func):
            self.tools[func.__name__] = func
            return func
        return decorate


class FakeRuntime:
    def status(self): return {"running": True}
    def pause(self): return {"paused": True}
    def resume(self): return {"running": True}
    def scan_now(self): return {"queued": True}
    def config_get(self): return {}


class FakeWorkService:
    def __init__(self):
        self.created = []

    def list_jobs(self, limit=50): return []
    def get_job(self, job_id): return None
    def retry_item(self, item_id): return {}
    def cancel_item(self, item_id): return {}

    def create_job(self, **kwargs):
        self.created.append(kwargs)
        return {
            "job_id": len(self.created),
            "status": "PENDING",
            "total_items": len(kwargs["rows"]),
            "items": kwargs["rows"],
        }


class FakeWorkspace:
    def get(self, pn):
        if pn == "KNOWN-PN":
            return {
                "found": True,
                "partnumber": pn,
                "master": {"ean": "1234567890123"},
                "technical": {"known_fields": {"ram_gb": 16, "cpu_model": "Ryzen 5"}},
            }
        return {"found": False, "partnumber": pn, "master": {}, "technical": {"known_fields": {}}}


class FakeImageReadiness:
    def get(self, pn, category_code=None, channel_code="MASTER"):
        return {
            "partnumber": pn,
            "image_count": 4 if pn == "KNOWN-PN" else 1,
            "state": "READY" if pn == "KNOWN-PN" else "INCOMPLETE",
        }


def _tools():
    mcp = FakeMcp()
    work = FakeWorkService()
    register_product_workspace_v2_tools(
        mcp,
        runtime=FakeRuntime(),
        work_service=work,
        image_readiness_service=FakeImageReadiness(),
        workspace_service=FakeWorkspace(),
    )
    return mcp.tools, work


def test_smart_complete_reuses_known_fields_and_sufficient_images():
    tools, work = _tools()
    out = tools["product_workspace_smart_complete"](
        ["KNOWN-PN"],
        requested_fields=["ram_gb", "cpu_model", "ean"],
        image_target_count=4,
        category_code="LAPTOP",
    )

    assert out["items"][0]["state"] == "READY"
    assert out["items"][0]["resolved_fields"] == 3
    assert out["items"][0]["missing_fields"] == []
    assert work.created == []


def test_smart_complete_queues_technical_and_image_gaps_but_not_unsupported_identity_job():
    tools, work = _tools()
    out = tools["product_workspace_smart_complete"](
        ["NEW-PN"],
        requested_fields=["ram_gb", "ean"],
        image_target_count=4,
        category_code="LAPTOP",
        channel_code="FALABELLA",
        template_code="falabella-laptop",
    )

    item = out["items"][0]
    assert item["state"] == "PROCESSING"
    assert "ean" in item["identity_review_fields"]
    assert any(job["work_type"] == "ENRICH_TECHNICAL" for job in work.created)
    assert any(job["work_type"] == "RESEARCH_IMAGES" for job in work.created)
    assert all(job["work_type"] != "RESEARCH_IDENTITY" for job in work.created)
