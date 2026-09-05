from stech_mcp.services.product_identity_research import ProductIdentityResearchService


class FakeIdentityRepository:
    def list_missing_identifiers(self, **kwargs):
        return {
            "products": [
                {
                    "producto_distribuidor_id": 907,
                    "part_number": "SXS1000R/1000G",
                    "marca": "KINGSTON",
                    "nombre": "Kingston XS1000 red 1TB",
                    "ean": None,
                    "upc": None,
                    "distribuidor_codigo": "DELTRON",
                }
            ],
            "count": 1,
            "has_more": False,
            "next_after_id": 907,
        }

    def partnumber_collision_stats(self, partnumbers):
        return {
            "SXS1000R/1000G": {
                "active_row_count": 1,
                "active_brand_count": 1,
            }
        }


class FakeResearchRepository:
    def __init__(self):
        self.states = {}
        self.saved = []

    def get_for_product_ids(self, product_ids):
        wanted = set(product_ids)
        return {key: value for key, value in self.states.items() if key[0] in wanted}

    def upsert(self, **kwargs):
        self.saved.append(kwargs)
        row = dict(kwargs)
        self.states[(kwargs["producto_distribuidor_id"], kwargs["identifier_type"])] = row
        return row

    def summary(self, partnumber=None):
        rows = [
            value
            for value in self.states.values()
            if partnumber is None or value["partnumber"] == partnumber
        ]
        by_status = {}
        by_identifier = {}
        for row in rows:
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            identifier_type = row["identifier_type"]
            by_identifier[identifier_type] = by_identifier.get(identifier_type, 0) + 1
        return {
            "partnumber": partnumber,
            "total": len(rows),
            "by_status": by_status,
            "by_identifier": by_identifier,
        }


class NoopService:
    pass


def test_queue_persists_new_pending_identifiers_without_incrementing_attempts():
    research = FakeResearchRepository()
    service = ProductIdentityResearchService(
        identity_repository=FakeIdentityRepository(),
        research_repository=research,
        verification_service=NoopService(),
        promotion_service=NoopService(),
    )

    result = service.queue(after_id=0, limit=10)

    assert result["count"] == 1
    assert result["products"][0]["research_status"] == {"EAN": "PENDING", "UPC": "PENDING"}
    assert {(row["identifier_type"], row["status"]) for row in research.saved} == {
        ("EAN", "PENDING"),
        ("UPC", "PENDING"),
    }
    assert all(row["increment_attempt"] is False for row in research.saved)

    status = service.status(partnumber="SXS1000R/1000G")
    assert status["total"] == 2
    assert status["by_status"] == {"PENDING": 2}
    assert status["by_identifier"] == {"EAN": 1, "UPC": 1}


def test_queue_does_not_rewrite_existing_pending_state():
    research = FakeResearchRepository()
    research.states[(907, "EAN")] = {
        "producto_distribuidor_id": 907,
        "partnumber": "SXS1000R/1000G",
        "identifier_type": "EAN",
        "status": "PENDING",
    }
    service = ProductIdentityResearchService(
        identity_repository=FakeIdentityRepository(),
        research_repository=research,
        verification_service=NoopService(),
        promotion_service=NoopService(),
    )

    service.queue(after_id=0, limit=10)

    assert [row["identifier_type"] for row in research.saved] == ["UPC"]
