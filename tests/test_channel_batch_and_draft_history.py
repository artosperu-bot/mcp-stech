from stech_mcp.services.channel_draft_service import ChannelDraftService
from stech_mcp.tools.product_workspace_v2 import register_product_workspace_v2_tools


class MCP:
    def __init__(self): self.names = []
    def tool(self):
        def deco(fn):
            self.names.append(fn.__name__)
            return fn
        return deco


class Runtime:
    def status(self): return {"running": True}
    def pause(self): return {"paused": True}
    def resume(self): return {"paused": False}
    def scan_now(self): return {"scanned": 1}
    def config_get(self): return {"max_workers": 3}


class Work:
    def list_jobs(self, limit=50): return []
    def get_job(self, job_id): return None
    def retry_item(self, item_id): return {"item_id": item_id}
    def cancel_item(self, item_id): return {"item_id": item_id}
    def create_job(self, **kwargs): return {"job_id": 1, **kwargs}


class Images:
    def get(self, *args, **kwargs): return {"state": "READY"}


class Gap:
    def get(self, pn, channel, category, version=None):
        return {
            "partnumber": pn,
            "channel_code": channel,
            "category_code": category,
            "state": "READY" if pn != "PN2" else "INCOMPLETE",
        }


class Drafts:
    def __init__(self): self.created = []
    def replace_draft(self, **kwargs):
        self.created.append(kwargs)
        return {"channel_draft_id": len(self.created), "draft_version": len(self.created), "status": "LISTO_PARA_REVISAR"}
    def list_drafts(self, partnumber, marketplace=None, limit=20):
        return [{"partnumber": partnumber, "marketplace": marketplace or "FALABELLA", "draft_version": 2, "status": "LISTO_PARA_REVISAR"}]


def test_channel_draft_service_exposes_history():
    service = ChannelDraftService(gap_analyzer=Gap(), draft_repository=Drafts())
    rows = service.history("pn1", "falabella", limit=10)
    assert rows[0]["partnumber"] == "PN1"
    assert rows[0]["marketplace"] == "FALABELLA"


def test_workspace_tools_support_channel_gap_and_draft_batches():
    draft_service = ChannelDraftService(gap_analyzer=Gap(), draft_repository=Drafts())
    tools = register_product_workspace_v2_tools(
        MCP(), runtime=Runtime(), work_service=Work(), image_readiness_service=Images(),
        channel_gap_analyzer=Gap(), channel_draft_service=draft_service,
    )
    gaps = tools["product_channel_gap_batch"](["pn1", "PN2", "pn1"], "FALABELLA", "LAPTOP")
    assert gaps["count"] == 2
    assert gaps["by_state"]["READY"] == 1
    assert gaps["by_state"]["INCOMPLETE"] == 1

    drafts = tools["product_channel_draft_prepare_batch"](["PN1", "PN2"], "FALABELLA", "LAPTOP")
    assert drafts["created_count"] == 1
    assert drafts["blocked_count"] == 1

    history = tools["product_channel_draft_history"]("pn1", "falabella", 10)
    assert history["count"] == 1
    assert history["drafts"][0]["draft_version"] == 2
