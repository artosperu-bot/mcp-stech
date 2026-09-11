from stech_mcp.tools.product_workspace_v2 import register_product_workspace_v2_tools


class MCP:
    def __init__(self):
        self.names = []

    def tool(self):
        def decorator(fn):
            self.names.append(fn.__name__)
            return fn
        return decorator


class Runtime:
    def status(self): return {"running": True}
    def pause(self): return {"paused": True}
    def resume(self): return {"paused": False}
    def scan_now(self): return {"scanned": 2}
    def config_get(self): return {"max_workers": 3}


class Work:
    def __init__(self):
        self.created = []

    def list_jobs(self, limit=50):
        return [{"status": "PENDING"}, {"status": "RUNNING"}, {"status": "FAILED"}]

    def get_job(self, job_id):
        return {"job_id": int(job_id), "status": "RUNNING", "items": []}

    def retry_item(self, item_id):
        return {"item_id": int(item_id), "status": "QUEUED"}

    def cancel_item(self, item_id):
        return {"item_id": int(item_id), "status": "CANCELLED"}

    def create_job(self, **kwargs):
        self.created.append(kwargs)
        return {"job_id": 9, **kwargs}


class Images:
    def get(self, pn, category_code=None, channel_code=None):
        return {"partnumber": pn, "state": "NO_IMAGES"}


class Candidates:
    def list_for_product(self, pn):
        return [{"partnumber": pn, "state": "PENDING"}]


def test_background_tools_and_image_research_use_persistent_work_queue():
    mcp = MCP()
    work = Work()
    tools = register_product_workspace_v2_tools(
        mcp,
        runtime=Runtime(),
        work_service=work,
        image_readiness_service=Images(),
        candidate_repository=Candidates(),
    )
    required = {
        "background_status",
        "background_pause",
        "background_resume",
        "background_scan_now",
        "background_config_get",
        "background_jobs_summary",
        "background_job_get",
        "background_job_retry",
        "background_job_cancel",
        "product_images_readiness",
        "product_images_research",
        "product_images_research_batch",
        "product_image_candidates",
    }
    assert required <= set(mcp.names)
    assert required <= set(tools)

    job = tools["product_images_research"]("pn1", "LAPTOP", 4)
    assert job["work_type"] == "RESEARCH_IMAGES"
    assert job["rows"][0]["scope"] == "MASTER"
    assert job["rows"][0]["partnumber"] == "PN1"

    batch = tools["product_images_research_batch"]([" pn1 ", "PN2", "pn1"], "LAPTOP", 5)
    assert batch["work_type"] == "RESEARCH_IMAGES"
    assert [row["partnumber"] for row in batch["rows"]] == ["PN1", "PN2"]
    assert all(row["image_target_count"] == 5 for row in batch["rows"])

    assert tools["background_job_get"](7)["job_id"] == 7
    assert tools["background_job_retry"](11)["status"] == "QUEUED"
    assert tools["background_job_cancel"](12)["status"] == "CANCELLED"
