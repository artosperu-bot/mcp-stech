import json
from decimal import Decimal

from stech_mcp.services.coolbox_preview import build_coolbox_preview


def _product():
    atributos = {
        "especificaciones": {
            "MODELO": "V15 G4 AMN",
            "PANTALLA": "15.6 PULG TN LED FHD WIDE RESOLUCION MAXIMA 1920 x 1080 ANTI-REFLEJO",
            "CPU": "AMD RYZEN 5 7520U 2.80 / 4.30 GHZ CACHE L2 2 MB CACHE L3 4 MB",
            "CAPACIDAD": "38 WH",
            "TIPO": "SSD M.2",
            "BUS": "4800 MHZ",
            "INTERFAZ": "2242 PCIe 4.0x4 NVMe",
            "INDEPENDIENTE": "NO",
            "SALIDAS": "HDMI",
            "WIRELESS": "802.11AX 2x2 Wi-Fi 6",
            "BLUETOOTH": "5.1",
            "PARLANTE": "STEREO SPEAKERS, 1.5W X2, DOLBY AUDIO",
            "WEBCAM": "SI",
            "RJ45": "1",
            "NRO CELDAS": "3",
            "TIPO BATERIA": "INTEGRADA",
            "IDIOMA DE TECLADO": "ESPAÑOL",
            "LARGO": "24.20 CM",
            "ANCHO": "35.92 CM",
            "ALTO": "1.99 CM",
            "PESO": "1.65 KG",
            "SISTEMA OPERATIVO": "VERSION NO INCLUYE SISTEMA OPERATIVO",
            "COMENTARIOS": "ADAPTADOR DE PODER 65W ROUND TIP (3-PIN) CÁMARA WEB HD 720p CON OBTURADOR DE PRIVACIDAD + MICROFONO 2x ARRAY COLOR ARTIC GREY (GRIS)",
        }
    }
    return {
        "part_number": "82YU00XYLM",
        "upc": "197528523880",
        "marca": "LENOVO",
        "nombre": 'Notebook Lenovo V15 G4 AMN, 15.6" FHD TN, AMD Ryzen 5 7520U 2.8/4.3GHz, 16GB LPDDR5-4800.',
        "atributos_json": json.dumps(atributos),
    }


def test_preview_uses_exact_coolbox_columns_and_deltron_values():
    preview = build_coolbox_preview(_product())

    assert preview["template"] == "Laptops-All in one"
    assert preview["field_count"] == 81
    fields = {row["field"]: row for row in preview["fields"]}

    assert fields["Sku code reference\n(Max. hasta 15 caracteres)"]["value"] == "82YU00XYLM"
    assert fields["Modelo"]["value"] == "V15 G4 AMN"
    assert fields["Marca"]["value"] == "LENOVO"
    assert fields["Tamaño de pantalla"]["value"] == '15.6"'
    assert fields["Tipo de panel"]["value"] == "TN"
    assert fields["Memoria RAM"]["value"] == "16 GB"
    assert fields["Batería"]["value"] == "38 Wh"
    assert fields["Color"]["value"] == "Artic Grey (Gris)"
    assert fields["Alto"]["value"] == 1.99
    assert fields["Ancho"]["value"] == 35.92
    assert fields["Profundidad"]["value"] == 24.2


def test_preview_never_invents_missing_config_sensitive_specs():
    preview = build_coolbox_preview(_product())
    fields = {row["field"]: row for row in preview["fields"]}

    assert fields["Capacidad de disco sólido (SSD)"]["value"] is None
    assert fields["Capacidad de disco sólido (SSD)"]["status"] == "RESEARCH_REQUIRED"
    assert fields["Tasa de refresco laptop"]["value"] is None
    assert fields["Procesador gráfico"]["value"] is None


def test_preview_uses_approved_15_x_packaging_fallback():
    preview = build_coolbox_preview(_product())
    fields = {row["field"]: row for row in preview["fields"]}

    assert fields["Alto (cm)"]["value"] == 7
    assert fields["Ancho (cm)"]["value"] == 33
    assert fields["Largo  (cm)"]["value"] == 54
    assert fields["Peso (g)"]["value"] == 2500
    for field_name in ("Alto (cm)", "Ancho (cm)", "Largo  (cm)", "Peso (g)"):
        assert fields[field_name]["status"] == "ESTIMATED"
        assert fields[field_name]["method"] == "ESTIMATED"
        assert fields[field_name]["source"] == "REGLA_STECH_EMPAQUE"
        assert "LAPTOP_15_X_DEFAULT" in (fields[field_name]["note"] or "")


def test_preview_prefers_resolved_official_package_over_fallback():
    package = {
        "width_cm": Decimal("31.0"),
        "length_cm": Decimal("50.5"),
        "height_cm": Decimal("7.2"),
        "weight_g": 2180,
        "status": "VERIFIED",
        "method": "VERIFIED",
        "source": "Lenovo PSREF exact PN",
        "rule_code": None,
        "confidence_grade": "A1",
    }

    preview = build_coolbox_preview(_product(), package=package)
    fields = {row["field"]: row for row in preview["fields"]}

    assert fields["Alto (cm)"]["value"] == Decimal("7.2")
    assert fields["Ancho (cm)"]["value"] == Decimal("31.0")
    assert fields["Largo  (cm)"]["value"] == Decimal("50.5")
    assert fields["Peso (g)"]["value"] == 2180
    for field_name in ("Alto (cm)", "Ancho (cm)", "Largo  (cm)", "Peso (g)"):
        assert fields[field_name]["status"] == "VERIFIED"
        assert fields[field_name]["method"] == "VERIFIED"
        assert fields[field_name]["source"] == "Lenovo PSREF exact PN"
