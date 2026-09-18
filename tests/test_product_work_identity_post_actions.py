from stech_mcp.services.product_work_service import ProductWorkService


class FakeRepository:
    def __init__(self):
        self.created = None

    def create_job(self, **kwargs):
        self.created = kwargs
        return {"job_id": 1, "items": kwargs["items"], "total_items": len(kwargs["items"])}


def test_identity_job_preserves_only_safe_vtex_post_action_context():
    repo = FakeRepository()
    service = ProductWorkService(repo)

    service.create_job(
        rows=[{
            "partnumber": "82YU00XYLM",
            "requested_fields": ["ean", "upc", "gtin"],
            "post_actions": ["VTEX_EAN_SYNC"],
            "vtex_account_code": "VTEX_STECH",
            "price": 999,
            "stock": 5,
            "publish": True,
        }],
        work_type="RESEARCH_IDENTITY",
        source_name="V8_SELECTED_IDENTITY",
        actor_source="SCR_UI",
        priority=50,
    )

    item = repo.created["items"][0]
    assert item["partnumber"] == "82YU00XYLM"
    assert item["requested_fields"] == ["ean", "upc", "gtin"]
    assert item["post_actions"] == ["VTEX_EAN_SYNC"]
    assert item["vtex_account_code"] == "VTEX_STECH"
    assert "price" not in item
    assert "stock" not in item
    assert "publish" not in item
