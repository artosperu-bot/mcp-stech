from types import SimpleNamespace

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
    def status(self):
        return {"running": True}
    def pause(self): return {"paused": True}
    def resume(self): return {"running": True}
    def scan_now(self): return {"queued": True}
    def config_get(self): return {}


class FakeWorkService:
    def __init__(self):
        self.created = []
    def list_jobs(self, limit=50): return []
    def create_job(self, **kwargs):
        self.created.append(kwargs)
        return {"job_id": len(self.created), "status": "PENDING", "total_items": len(kwargs["rows"]), "items": kwargs["rows"]}
    def get_job(self, job_id): return None
    def retry_item(self, item_id): return {}
    def cancel_item(self, item_id): return {}


class FakeWorkspace:
    def get(self, pn):
        if pn == "KNOWN-PN":
            return {
                "found": True,
                "partnumber": pn,
                "technical": {"known_fields": {"ram_gb": 16, "cpu_model": "Ryzen 5"}},
            }
        return {"found": False, "partnumber": pn}


class FakeImageReadiness:
    def get(self, pn, category_code=None, channel_code="MASTER"):
        return {"partnumber": pn, "image_count": 4 if pn == "KNOWN-PN" else 1, "state": "READY" if pn == "KNOWN-PN" else "INCOMPLETE"}


def _tools():
    mcp = FakeMcp(); work = FakeWorkService()
    register_product_workspace_v2_tools(
        mcp,
        runtime=FakeRuntime(),
        work_service=work,
        image_readiness_service=FakeImageReadiness(),
        workspace_service=FakeWorkspace(),
    )
    return mcp.tools, work


def test_smart_complete_accepts_known_and_unknown_manual_partnumbers():
    tools, work = _tools()
    out = tools["product_workspace_smart_complete"](
        ["known-pn", " new-pn "],
        requested_fields=["ram_gb", "ean", "description"],
        image_target_count=4,
        category_code="LAPTOP",
        channel_code="FALABELLA",
        template_code="falabella-laptop",
    )
    assert [row["partnumber"] for row in out["items"]] == ["KNOWN-PN", "NEW-PN"]
    assert out["requested_count"] == 2
    assert any(job["work_type"] == "RESEARCH_IDENTITY" for job in work.created)
    assert any(job["work_type"] == "ENRICH_TECHNICAL" for job in work.created)
    assert any(job["work_type"] == "RESEARCH_IMAGES" for job in work.created)


def test_smart_complete_reuses_known_fields_and_sufficient_local_images():
    tools, work = _tools()
    out = tools["product_workspace_smart_complete"](
        ["KNOWN-PN"],
        requested_fields=["ram_gb", "cpu_model"],
        image_target_count=4,
        category_code="LAPTOP",
    )
    assert out["items"][0]["resolved_fields"] == 2
    assert out["items"][0]["missing_fields"] == []
    assert out["items"][0]["images"]["missing"] == 0
    assert out["items"][0]["state"] == "READY"
    assert work.created == []


def test_smart_complete_researches_only_image_deficit_context():
    tools, work = _tools()
    out = tools["product_workspace_smart_complete"](
        ["NEW-PN"], requested_fields=[], image_target_count=4, category_code="PRINTER"
    )
    assert out["items"][0]["images"] == {"current": 1, "target": 4, "missing": 3}
    image_job = next(job for job in work.created if job["work_type"] == "RESEARCH_IMAGES")
    assert image_job["rows"][0]["image_target_count"] == 4
    assert image_job["rows"][0]["image_missing_count"] == 3
