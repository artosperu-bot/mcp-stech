from stech_mcp.services.product_scanner import ProductScanner


class Products:
    def __init__(self, rows):
        self.rows = rows

    def list_for_scan(self, after_partnumber="", limit=100):
        return self.rows[:limit]


class Technical:
    def __init__(self, by_pn):
        self.by_pn = by_pn

    def get(self, pn):
        return self.by_pn[pn]


class Images:
    def __init__(self, by_pn):
        self.by_pn = by_pn

    def get(self, pn, category_code=None, channel_code=None):
        return self.by_pn[pn]


class Work:
    def __init__(self):
        self.calls = []

    def create_job(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "job_id": len(self.calls),
            "status": "PENDING",
            "total_items": len(kwargs["rows"]),
            "items": [{"state": "QUEUED"} for _ in kwargs["rows"]],
        }


def build(rows, technical, images):
    work = Work()
    scanner = ProductScanner(
        product_repository=Products(rows),
        technical_status_service=Technical(technical),
        image_readiness_service=Images(images),
        work_service=work,
    )
    return scanner, work


def test_complete_product_creates_no_job():
    scanner, work = build(
        [{"partnumber": "PN1", "category_code": "LAPTOP", "stock_total": 5}],
        {"PN1": {"missing_required": [], "missing_recommended": []}},
        {"PN1": {"state": "READY", "recommended_min": 4}},
    )
    result = scanner.scan_once(limit=10)
    assert result["technical_jobs_created"] == 0
    assert result["image_jobs_created"] == 0
    assert work.calls == []


def test_technical_gap_creates_master_enrichment_job():
    scanner, work = build(
        [{"partnumber": "PN1", "category_code": "LAPTOP", "stock_total": 5}],
        {"PN1": {"missing_required": ["ram_gb"], "missing_recommended": []}},
        {"PN1": {"state": "READY", "recommended_min": 4}},
    )
    result = scanner.scan_once(limit=10)
    call = work.calls[0]
    assert call["work_type"] == "ENRICH_TECHNICAL"
    assert call["rows"][0]["scope"] == "MASTER"
    assert call["rows"][0]["requested_fields"] == ["ram_gb"]
    assert result["technical_jobs_created"] == 1


def test_image_gap_creates_research_images_job():
    scanner, work = build(
        [{"partnumber": "PN1", "category_code": "LAPTOP", "stock_total": 5}],
        {"PN1": {"missing_required": [], "missing_recommended": []}},
        {"PN1": {"state": "NO_IMAGES", "recommended_min": 4}},
    )
    result = scanner.scan_once(limit=10)
    call = work.calls[0]
    assert call["work_type"] == "RESEARCH_IMAGES"
    assert call["rows"][0]["scope"] == "MASTER"
    assert call["rows"][0]["image_target_count"] == 4
    assert result["image_jobs_created"] == 1

def test_multi_distributor_rows_are_scanned_once_and_use_stock_valor_for_priority():
    scanner, work = build(
        [
            {"partnumber": "PN1", "category_code": "LAPTOP", "stock_valor": 0, "distribuidor": "A"},
            {"partnumber": "PN1", "category_code": "LAPTOP", "stock_valor": 9, "distribuidor": "B"},
        ],
        {"PN1": {"missing_required": ["ram_gb"], "missing_recommended": []}},
        {"PN1": {"state": "NO_IMAGES", "recommended_min": 4}},
    )

    result = scanner.scan_once(limit=10)

    assert result["scanned"] == 2
    assert result["unique_products_scanned"] == 1
    assert len(work.calls) == 2
    assert work.calls[0]["priority"] == 80
    assert work.calls[1]["priority"] == 90
    assert work.calls[0]["rows"][0]["source_context"]["stock"] == 9
    assert work.calls[0]["rows"][0]["source_context"]["distributor_count"] == 2
