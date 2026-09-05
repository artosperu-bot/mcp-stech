from stech_mcp.services.product_images import normalize_deltron_images


def test_exact_snapshot_active_image_is_eligible_without_manual_editing():
    rows = [
        {
            "imagen_id": 395,
            "producto_distribuidor_id": 1343,
            "orden_imagen": 8,
            "url_origen": "https://imagenes.deltron.com.pe/images/productos/carrusel/NBLEN82XQ00LYLM/x.jpg",
            "ruta_relativa": r"LENOVO\COMPUTADORAS_NOTEBOOK\82XQ00LYLM\x.jpg",
            "ruta_actual": r"C:\STECH_IMAGENES\LENOVO\COMPUTADORAS_NOTEBOOK\82XQ00LYLM\x.jpg",
            "nombre_archivo": "x.jpg",
            "part_number_snapshot": "82XQ00LYLM",
            "modelo_snapshot": "V15",
            "marca_snapshot": "LENOVO",
            "ancho_px": 1200,
            "alto_px": 1200,
            "megapixeles": 1.44,
            "tamano_bytes": 345678,
            "formato": "jpg",
            "hash_sha256": "a" * 64,
            "calidad": "ALTA",
            "estado_descarga": "OK",
            "estado_archivo": "ACTIVO",
            "ruta_papelera": None,
            "fecha_eliminacion": None,
            "ultimo_error": None,
        }
    ]

    images = normalize_deltron_images("82xq00lylm", rows)

    assert len(images) == 1
    image = images[0]
    assert image["source_image_id"] == 395
    assert image["source_type"] == "DELTRON_DB"
    assert image["source_domain"] == "imagenes.deltron.com.pe"
    assert image["partnumber_match"] == "EXACT"
    assert image["source_eligible"] is True
    assert image["is_approved"] is False
    assert image["editing_required"] is False
    assert image["position"] == 8
    assert image["storage_path"].endswith("x.jpg")


def test_mismatched_or_deleted_deltron_image_is_not_eligible():
    rows = [
        {
            "imagen_id": 1,
            "orden_imagen": 1,
            "url_origen": "https://imagenes.deltron.com.pe/x.jpg",
            "part_number_snapshot": "OTHER-PN",
            "fecha_eliminacion": None,
        },
        {
            "imagen_id": 2,
            "orden_imagen": 2,
            "url_origen": "https://imagenes.deltron.com.pe/y.jpg",
            "part_number_snapshot": "82XQ00LYLM",
            "fecha_eliminacion": "2026-09-04T10:00:00",
        },
    ]

    images = normalize_deltron_images("82XQ00LYLM", rows)

    assert images[0]["partnumber_match"] == "MISMATCH"
    assert images[0]["source_eligible"] is False
    assert images[1]["partnumber_match"] == "EXACT"
    assert images[1]["source_eligible"] is False
