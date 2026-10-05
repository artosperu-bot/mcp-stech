from stech_mcp.domain.product_work_models import make_context_hash
from stech_mcp.services.product_work_service import ProductWorkService


class Repo:
    def create_job(self, **kwargs):
        return kwargs


def test_context_hash_changes_for_master_vs_channel_scope():
    master = make_context_hash(
        "ENRICH_TECHNICAL",
        "PN1",
        "LAPTOP",
        "FALABELLA",
        context={"scope": "MASTER", "requested_fields": ["ram_gb"]},
    )
    channel = make_context_hash(
        "ENRICH_TECHNICAL",
        "PN1",
        "LAPTOP",
        "FALABELLA",
        context={
            "scope": "CHANNEL",
            "requirements_version": "V2",
            "requested_fields": ["ram_gb"],
        },
    )
    assert master != channel


def test_channel_scoped_technical_rows_are_not_collapsed_by_partnumber():
    service = ProductWorkService(Repo())
    result = service.create_job(
        rows=[
            {
                "partnumber": "PN1",
                "scope": "MASTER",
                "requested_fields": ["ram_gb"],
            },
            {
                "partnumber": "PN1",
                "scope": "CHANNEL",
                "channel_code": "FALABELLA",
                "requirements_version": "V2",
                "requested_fields": ["plug_type"],
            },
        ],
        work_type="ENRICH_TECHNICAL",
        source_name="x",
        actor_source="x",
    )
    assert len(result["items"]) == 2