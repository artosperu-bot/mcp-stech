from stech_mcp.services.product_image_readiness import ProductImageReadinessService


class Products:
    def __init__(self, product=None, products=None):
        self.product = product or {"part_number": "PN1", "producto_distribuidor_id": 1}
        self.products = products

    def get_by_partnumber(self, pn):
        return self.product

    def list_by_partnumber(self, pn, limit=100):
        if self.products is not None:
            return list(self.products)[:limit]
        return [self.product]


class Source:
    def __init__(self, rows=None, by_product=None):
        self.rows = rows or []
        self.by_product = by_product or {}

    def list_for_product(self, product_id):
        if product_id in self.by_product:
            return list(self.by_product[product_id])
        return list(self.rows)


class Workspace:
    def __init__(self, images=None, policy=None):
        self.images = images or []
        self.policy = policy

    def list_images(self, pn):
        return list(self.images)

    def get_image_requirement_policy(self, channel_code, category_code):
        return self.policy or {
            "required_min": 1,
            "recommended_min": 4,
            "require_main": True,
            "min_width_px": None,
            "min_height_px": None,
            "exactness_policy": "EXACT_PN_REQUIRED",
            "channel_code": "MASTER",
            "category_code": "DEFAULT",
            "version_code": "V1",
        }


def service(images=None, source=None, policy=None, products=None, by_product=None):
    return ProductImageReadinessService(
        product_repository=Products(products=products),
        source_image_repository=Source(source, by_product=by_product),
        workspace_image_repository=Workspace(images, policy),
    )


def test_zero_images_is_no_images():
    result = service().get("pn1")
    assert result["state"] == "NO_IMAGES"
    assert "no_usable_images" in result["missing_reasons"]


def test_exact_approved_main_but_below_recommended_is_incomplete():
    images = [
        {
            "is_approved": True,
            "partnumber_match": "EXACT",
            "position": 1,
            "width_px": 1200,
            "height_px": 1200,
        }
    ]
    result = service(images=images).get("pn1")
    assert result["state"] == "INCOMPLETE"
    assert result["has_main"] is True
    assert result["approved_count"] == 1
    assert result["exact_count"] == 1
    assert "recommended_count_not_met" in result["missing_reasons"]


def test_four_exact_approved_images_are_ready():
    images = [
        {
            "is_approved": True,
            "partnumber_match": "EXACT",
            "position": position,
            "width_px": 1200,
            "height_px": 1200,
        }
        for position in range(1, 5)
    ]
    result = service(images=images).get("pn1")
    assert result["state"] == "READY"
    assert result["image_count"] == 4


def test_approved_mismatch_requires_review_under_exact_policy():
    images = [
        {"is_approved": True, "partnumber_match": "MISMATCH", "position": 1, "width_px": 1200, "height_px": 1200},
        {"is_approved": True, "partnumber_match": "EXACT", "position": 2, "width_px": 1200, "height_px": 1200},
        {"is_approved": True, "partnumber_match": "EXACT", "position": 3, "width_px": 1200, "height_px": 1200},
        {"is_approved": True, "partnumber_match": "EXACT", "position": 4, "width_px": 1200, "height_px": 1200},
    ]
    result = service(images=images).get("pn1")
    assert result["state"] == "REVIEW_REQUIRED"
    assert "approved_non_exact_image" in result["missing_reasons"]


def test_channel_policy_can_require_only_two_images_and_minimum_resolution():
    policy = {
        "required_min": 2,
        "recommended_min": 2,
        "require_main": True,
        "min_width_px": 1000,
        "min_height_px": 1000,
        "exactness_policy": "EXACT_PN_REQUIRED",
        "channel_code": "FALABELLA",
        "category_code": "LAPTOP",
        "version_code": "V3",
    }
    images = [
        {"is_approved": True, "partnumber_match": "EXACT", "position": 1, "width_px": 1200, "height_px": 1200},
        {"is_approved": True, "partnumber_match": "EXACT", "position": 2, "width_px": 800, "height_px": 800},
    ]
    result = service(images=images, policy=policy).get(
        "pn1",
        category_code="LAPTOP",
        channel_code="FALABELLA",
    )
    assert result["state"] == "INCOMPLETE"
    assert result["quality_ok_count"] == 1
    assert "quality_minimum_not_met" in result["missing_reasons"]

def test_source_images_are_aggregated_across_distributors_for_same_pn():
    products = [
        {"part_number": "PN1", "producto_distribuidor_id": 1, "distribuidor": "DELTRON"},
        {"part_number": "PN1", "producto_distribuidor_id": 2, "distribuidor": "INGRAM"},
    ]
    by_product = {
        1: [
            {
                "part_number_snapshot": "PN1",
                "url_origen": "https://example.test/d1.jpg",
                "orden_imagen": 1,
            }
        ],
        2: [
            {
                "part_number_snapshot": "PN1",
                "url_origen": f"https://example.test/i{position}.jpg",
                "orden_imagen": position,
            }
            for position in range(2, 5)
        ],
    }

    result = service(products=products, by_product=by_product).get("pn1")

    assert result["source_image_count"] == 4
    assert result["image_count"] == 4
    assert result["exact_count"] == 4
    assert result["state"] == "READY"
