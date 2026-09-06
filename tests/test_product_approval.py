from stech_mcp.services.product_approval import ProductApprovalService


class FakeRepository:
    def __init__(self, *, master=None, draft=None, images=None):
        self.master = master
        self.draft = draft
        self.images = images or []
        self.approvals = []
        self.audit = []

    def get(self, partnumber):
        return self.master

    def get_latest_draft(self, partnumber, marketplace):
        return self.draft

    def list_images(self, partnumber):
        return list(self.images)

    def approve_latest_draft(self, **kwargs):
        self.approvals.append(kwargs)
        return {
            "found": True,
            "partnumber": kwargs["partnumber"],
            "marketplace": kwargs["marketplace"],
            "channel_draft_id": 7,
            "draft_version": 3,
            "approval_status": "APROBADO",
            "approved_by": kwargs["approved_by"],
        }

    def add_audit_event(self, **kwargs):
        self.audit.append(kwargs)


def _ready_draft():
    return {
        "channel_draft_id": 7,
        "draft_version": 3,
        "required_missing_count": 0,
        "payload": {
            "fields": [
                {"field": "Precio Lista (Full )", "value": 1999, "status": "MARKETPLACE_INPUT"},
                {"field": "Precio Base (Especial)", "value": 1899, "status": "MARKETPLACE_INPUT"},
                {"field": "Stock", "value": 4, "status": "MARKETPLACE_INPUT"},
            ]
        },
    }


def test_approval_is_blocked_until_research_images_and_commercial_fields_are_ready():
    draft = _ready_draft()
    draft["required_missing_count"] = 2
    draft["payload"]["fields"][2]["value"] = None
    repo = FakeRepository(
        master={"partnumber": "82YU00XYLM", "readiness_state": "FALTAN_DATOS"},
        draft=draft,
        images=[],
    )
    service = ProductApprovalService(repo)

    result = service.approve("82YU00XYLM", marketplace="COOLBOX", approved_by="SCR_UI")

    assert result["approved"] is False
    assert "research_required_fields" in result["blocking_reasons"]
    assert "approved_images" in result["blocking_reasons"]
    assert "commercial:Stock" in result["blocking_reasons"]
    assert repo.approvals == []


def test_approval_marks_exact_latest_draft_when_ready():
    repo = FakeRepository(
        master={"partnumber": "82YU00XYLM", "readiness_state": "LISTO_PARA_REVISAR"},
        draft=_ready_draft(),
        images=[{"is_approved": True}],
    )
    service = ProductApprovalService(repo)

    result = service.approve(
        "82yu00xylm",
        marketplace="coolbox",
        approved_by="SCR_UI",
        note="Revisado visualmente",
    )

    assert result["approved"] is True
    assert result["approval_status"] == "APROBADO"
    assert repo.approvals == [
        {
            "partnumber": "82YU00XYLM",
            "marketplace": "COOLBOX",
            "approved_by": "SCR_UI",
            "note": "Revisado visualmente",
        }
    ]
    assert repo.audit[0]["event_type"] == "CHANNEL_DRAFT_APPROVED"
    assert repo.audit[0]["channel"] == "COOLBOX"
