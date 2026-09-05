from stech_mcp.db.product_identity_research_repository import ProductIdentityResearchRepository
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
        self.states = {
            (907, "EAN"): {
                "research_id": 101,
                "producto_distribuidor_id": 907,
                "partnumber": "SXS1000R/1000G",
                "identifier_type": "EAN",
                "status": "PENDING",
                "attempt_count": 0,
            },
            (907, "UPC"): {
                "research_id": 102,
                "producto_distribuidor_id": 907,
                "partnumber": "SXS1000R/1000G",
                "identifier_type": "UPC",
                "status": "PENDING",
                "attempt_count": 0,
            },
        }

    def get_for_product_ids(self, product_ids):
        wanted = set(product_ids)
        return {key: value for key, value in self.states.items() if key[0] in wanted}

    def upsert(self, **kwargs):
        raise AssertionError("existing PENDING states must not be rewritten")

    def summary(self, partnumber=None):
        raise NotImplementedError


class NoopService:
    pass


def test_queue_exposes_attempt_count_for_each_pending_identifier():
    service = ProductIdentityResearchService(
        identity_repository=FakeIdentityRepository(),
        research_repository=FakeResearchRepository(),
        verification_service=NoopService(),
        promotion_service=NoopService(),
    )

    result = service.queue(after_id=0, limit=10)

    product = result["products"][0]
    assert product["research_status"] == {"EAN": "PENDING", "UPC": "PENDING"}
    assert product["research_attempt_count"] == {"EAN": 0, "UPC": 0}


class SummaryCursor:
    def __init__(self):
        self.sql = ""
        self.description = None

    def execute(self, sql, *params):
        self.sql = sql.upper()
        if "RESEARCH_ID" in self.sql and "ORDER BY IDENTIFIER_TYPE" in self.sql:
            self.description = [
                ("research_id",),
                ("producto_distribuidor_id",),
                ("partnumber",),
                ("identifier_type",),
                ("status",),
                ("attempt_count",),
                ("updated_at",),
            ]
        return self

    def fetchall(self):
        if "GROUP BY STATUS" in self.sql:
            return [("PENDING", 2)]
        if "GROUP BY IDENTIFIER_TYPE" in self.sql:
            return [("EAN", 1), ("UPC", 1)]
        if "SUM(CAST(ATTEMPT_COUNT" in self.sql:
            return [(0, 0)]
        if "RESEARCH_ID" in self.sql and "ORDER BY IDENTIFIER_TYPE" in self.sql:
            return [
                (101, 907, "SXS1000R/1000G", "EAN", "PENDING", 0, "2026-09-05"),
                (102, 907, "SXS1000R/1000G", "UPC", "PENDING", 0, "2026-09-05"),
            ]
        raise AssertionError(self.sql)


class SummaryConnection:
    def __init__(self):
        self.cursor_obj = SummaryCursor()

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


def test_status_exposes_attempt_aggregates_and_per_identifier_items_for_partnumber():
    repository = ProductIdentityResearchRepository(lambda: SummaryConnection())

    result = repository.summary(partnumber="SXS1000R/1000G")

    assert result["attempt_count_total"] == 0
    assert result["max_attempt_count"] == 0
    assert result["items"] == [
        {
            "research_id": 101,
            "producto_distribuidor_id": 907,
            "partnumber": "SXS1000R/1000G",
            "identifier_type": "EAN",
            "status": "PENDING",
            "attempt_count": 0,
            "updated_at": "2026-09-05",
        },
        {
            "research_id": 102,
            "producto_distribuidor_id": 907,
            "partnumber": "SXS1000R/1000G",
            "identifier_type": "UPC",
            "status": "PENDING",
            "attempt_count": 0,
            "updated_at": "2026-09-05",
        },
    ]
