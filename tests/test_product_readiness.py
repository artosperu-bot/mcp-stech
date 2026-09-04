from stech_mcp.domain.product_readiness import calculate_readiness


def _fields(statuses):
    rows = []
    for index, status in enumerate(statuses):
        rows.append({"field": f"F{index}", "value": None if status == "RESEARCH_REQUIRED" else "x", "status": status})
    return rows


def test_complete_identity_without_images_prioritizes_missing_images():
    product = {"part_number": "82YU00XYLM", "marca": "LENOVO", "nombre": "Laptop", "upc": "197528523880"}
    preview = {
        "field_count": 81,
        "fields": _fields(["RESEARCH_REQUIRED"] * 10 + ["DISTRIBUTOR"] * 66 + ["MARKETPLACE_INPUT"] * 5),
        "ready_for_research": [f"F{i}" for i in range(10)],
        "estimated_fields": [],
    }
    package = {"method": "ESTIMATED"}

    result = calculate_readiness(product=product, coolbox_preview=preview, package=package, images=[])

    assert result["state"] == "FALTAN_IMAGENES"
    assert result["identity_score"] == 100
    assert result["image_score"] == 0
    assert result["package_score"] == 70
    assert len(result["missing_fields"]) == 10


def test_approved_images_with_missing_research_fields_becomes_faltan_datos():
    product = {"part_number": "82YU00XYLM", "marca": "LENOVO", "nombre": "Laptop", "ean": "197528523880"}
    preview = {
        "field_count": 81,
        "fields": _fields(["RESEARCH_REQUIRED"] * 2 + ["DISTRIBUTOR"] * 74 + ["MARKETPLACE_INPUT"] * 5),
        "ready_for_research": ["F0", "F1"],
        "estimated_fields": [],
    }
    images = [{"is_approved": True} for _ in range(4)]

    result = calculate_readiness(product=product, coolbox_preview=preview, package={"method": "VERIFIED"}, images=images)

    assert result["state"] == "FALTAN_DATOS"
    assert result["image_score"] == 100
    assert result["package_score"] == 100


def test_marketplace_inputs_do_not_block_listo_para_revisar():
    product = {"part_number": "82YU00XYLM", "marca": "LENOVO", "nombre": "Laptop", "upc": "197528523880"}
    preview = {
        "field_count": 81,
        "fields": _fields(["DISTRIBUTOR"] * 76 + ["MARKETPLACE_INPUT"] * 5),
        "ready_for_research": [],
        "estimated_fields": [],
    }
    images = [{"is_approved": True} for _ in range(4)]

    result = calculate_readiness(product=product, coolbox_preview=preview, package={"method": "VERIFIED"}, images=images)

    assert result["state"] == "LISTO_PARA_REVISAR"
    assert result["coolbox_score"] == 100
