from stech_mcp.services.channel_draft_service import ChannelDraftService


def test_blocked_gap_does_not_create_draft():
    class Gap:
        def get(self, *args, **kwargs):
            return {"state": "INCOMPLETE", "required_missing": 2, "fields": []}

    class Drafts:
        def replace_draft(self, **kwargs):
            raise AssertionError("must not write draft")

    result = ChannelDraftService(gap_analyzer=Gap(), draft_repository=Drafts()).prepare(
        "PN1", "FALABELLA", "LAPTOP"
    )
    assert result["created"] is False
    assert result["state"] == "BLOCKED"


def test_ready_gap_creates_versioned_snapshot_without_publication():
    class Gap:
        def get(self, *args, **kwargs):
            return {
                "state": "READY",
                "requirements_version": "V2",
                "channel_code": "FALABELLA",
                "category_code": "LAPTOP",
                "fields": [{"target_field_code": "cpu", "state": "COMPLETE", "value": "Ryzen"}],
                "image_readiness": {"state": "READY", "image_count": 4},
            }

    class Drafts:
        def __init__(self):
            self.kwargs = None

        def replace_draft(self, **kwargs):
            self.kwargs = kwargs
            return {"channel_draft_id": 7, "draft_version": 3, "status": "LISTO_PARA_REVISAR"}

    drafts = Drafts()
    result = ChannelDraftService(gap_analyzer=Gap(), draft_repository=drafts).prepare(
        "PN1", "FALABELLA", "LAPTOP"
    )
    assert result["created"] is True
    assert drafts.kwargs["marketplace"] == "FALABELLA"
    assert drafts.kwargs["template_name"] == "V2"
    assert drafts.kwargs["payload"]["image_readiness"]["state"] == "READY"
