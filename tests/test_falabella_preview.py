import json

from stech_mcp.services.falabella_preview import build_falabella_preview


def _product():
    return {
        "part_number": "82YU00XYLM",
        "ean": "0197528523880",
        "marca": "LENOVO",
        "nombre": 'Notebook Lenovo V15 G4 AMN, 15.6" FHD TN, AMD Ryzen 5 7520U, 16GB LPDDR5-4800.',
        "atributos_json": json.dumps(
            {
                "especificaciones": {
                    "MODELO": "V15 G4 AMN",
                    "PANTALLA": '15.6 PULG TN LED FHD RESOLUCION 1920 x 1080',
                    "CPU": "AMD RYZEN 5 7520U",
                    "PESO": "1.65 KG",
                }
            }
        ),
    }


def _coolbox_preview(*args, **kwargs):
    values = {
        "NOMBRE /TÍTULO DE PRODUCTO\nMax 120 caracteres\nTipo de producto+Marca+característica (s) principales + color": 'Laptop Lenovo V15 G4 AMN Ryzen 5 7520U 16GB 512GB SSD 15.6" FHD',
        "DESCRIPCIÓN DE PRODUCTO\n(Con características importantes)": "Laptop Lenovo para productividad.",
        "Modelo": "V15 G4 AMN",
        "Marca": "LENOVO",
        "Alto": 1.99,
        "Ancho": 35.92,
        "Profundidad": 23.58,
        "Tamaño de pantalla": '15.6"',
        "Procesador": "AMD Ryzen 5",
        "Detalle del procesador": "AMD Ryzen 5 7520U, 4 núcleos, hasta 4.3 GHz",
        "Memoria RAM": "16 GB",
        "Capacidad de disco sólido (SSD)": "512 GB",
        "Cantidad de núcleos": "4 núcleos",
        "Procesador gráfico": "AMD",
        "Detalle del procesador gráfico": "AMD Radeon 610M Graphics integrada",
        "Pantalla táctil": "No",
        "Bluetooth": "Sí",
        "Resolución de pantalla": "FHD - 1080",
        "Tasa de refresco laptop": "60 Hz",
        "Color": "Arctic Grey (Gris)",
        "Año": 2023,
        "Puertos HDMI": 1,
        "Puertos USB": 2,
        "Puertos USB Tipo-C": 1,
        "¿Qué incluye en la caja?": "Notebook, cargador y documentación.",
        "Alto (cm)": 7,
        "Ancho (cm)": 31.4,
        "Largo  (cm)": 49.2,
        "Peso (g)": 2450,
    }
    return {
        "fields": [
            {"field": key, "value": value, "status": "VERIFIED"}
            for key, value in values.items()
        ]
    }


def test_falabella_preview_maps_required_fields_and_vtex_images(monkeypatch):
    monkeypatch.setattr(
        "stech_mcp.services.falabella_preview.build_coolbox_preview",
        _coolbox_preview,
    )
    urls = [
        "https://ststore227.vtexassets.com/01.jpg",
        "https://ststore227.vtexassets.com/02.jpg",
        "https://ststore227.vtexassets.com/03.jpg",
        "https://ststore227.vtexassets.com/04.jpg",
    ]

    result = build_falabella_preview(product=_product(), image_urls=urls)
    fields = {row["field"]: row["value"] for row in result["fields"]}

    assert result["template"] == "ProductCreationTemplate / Portátiles|notebooks"
    assert result["readiness_state"] == "READY"
    assert result["image_count"] == 4
    assert fields["Código de barras #56"] == "0197528523880"
    assert fields["TipoDePortatil #396393"] == "Laptop"
    assert fields["NucleosDelProcesador #1611"] == "Quad core"
    assert fields["MemoriaRam #1540"] == "16GB"
    assert fields["Imagen principal #IM1"] == urls[0]
    assert fields["Imagen4 #IM4"] == urls[3]
    assert fields["Imagen5 #IM5"] is None


def test_falabella_preview_blocks_without_barcode_or_main_image(monkeypatch):
    monkeypatch.setattr(
        "stech_mcp.services.falabella_preview.build_coolbox_preview",
        _coolbox_preview,
    )
    product = _product()
    product["ean"] = None
    product["upc"] = None

    result = build_falabella_preview(product=product, image_urls=[])

    assert result["readiness_state"] == "BLOCKED"
    assert "Código de barras #56" in result["required_missing"]
    assert "Imagen principal #IM1" in result["required_missing"]
