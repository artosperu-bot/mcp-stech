from __future__ import annotations

import json
import re
from collections import Counter
from decimal import Decimal
from typing import Any

from stech_mcp.domain.packaging_rules import estimate_package_weight

TEMPLATE_NAME = "Laptops-All in one"

COOLBOX_FIELDS = [
    "Sku code reference\n(Max. hasta 15 caracteres)",
    "Contador de caracteres de Sku code reference\nMax. hasta 15 ",
    "NOMBRE /TÍTULO DE PRODUCTO\nMax 120 caracteres\nTipo de producto+Marca+característica (s) principales + color",
    "DESCRIPCIÓN DE PRODUCTO\n(Con características importantes)",
    "Rubro", "Familia", "SubFamilia", "GAMA",
    "Alto (cm)", "Ancho (cm)", "Largo  (cm)", "Peso (g)",
    "Modelo", "Marca", "Alto", "Ancho", "Profundidad", "Peso", "Garantía", "Información adicional",
    "Tamaño de pantalla", "Procesador", "Detalle del procesador", "Memoria RAM", "Capacidad de disco sólido (SSD)",
    "Tasa de refresco laptop", "Resolución de pantalla", "Tipo de panel", "Capacidad de disco duro (HDD)",
    "Detalle de memoria RAM", "Detalle de discos", "Memoria unificada", "Tipo de gráficos", "Procesador gráfico",
    "Detalle del procesador gráfico", "Incluye sistema operativo", "Nombre de SO", "Sistema de refrigeración",
    "Certificaciones", "Puertos HDMI", "Puertos USB", "Puertos USB Tipo-C", "Puerto de red", "Entrada de audio",
    "Conexión VGA", "Ranura para tarjeta SD / microSD", "Bluetooth", "Wi-Fi", "Cámara web", "Lector de huellas",
    "Reconocimiento facial", "Teclado iluminado", "Teclado numérico", "Altavoz", "Idioma del teclado", "Batería",
    "Tipo de batería", "Duración de la batería", "Color", "Capacidad de disco eMMC ", "Pantalla táctil", "Consumo",
    "Año", "Conector de carga", "Cantidad de núcleos", "Generación del procesador", "Teclado", "Tamaño (pulgadas)",
    "Requiere transformador", "Tipo transformador", "incluye transformador", "Tipo de enchufe", "¿Qué incluye en la caja?",
    "CROSS 1", "CROSS 2", "CROSS 3", "Precio Lista (Full )", "Precio Base (Especial)", "Fecha de Inicio", "Fecha Fin", "Stock",
]

_ENRICHMENT_TO_COOLBOX = {
    "warranty": "Garantía",
    "ssd_capacity_gb": "Capacidad de disco sólido (SSD)",
    "refresh_rate_hz": "Tasa de refresco laptop",
    "memory_detail": "Detalle de memoria RAM",
    "storage_detail": "Detalle de discos",
    "gpu_model": "Procesador gráfico",
    "gpu_detail": "Detalle del procesador gráfico",
    "os_name": "Nombre de SO",
    "cooling_system": "Sistema de refrigeración",
    "certifications": "Certificaciones",
    "hdmi_ports": "Puertos HDMI",
    "usb_a_ports": "Puertos USB",
    "usb_c_ports": "Puertos USB Tipo-C",
    "vga": "Conexión VGA",
    "card_reader": "Ranura para tarjeta SD / microSD",
    "fingerprint_reader": "Lector de huellas",
    "face_recognition": "Reconocimiento facial",
    "keyboard_backlit": "Teclado iluminado",
    "keyboard_numeric": "Teclado numérico",
    "battery_runtime_hours": "Duración de la batería",
    "emmc_capacity": "Capacidad de disco eMMC ",
    "touchscreen": "Pantalla táctil",
    "power_consumption": "Consumo",
    "announce_year": "Año",
    "cpu_cores": "Cantidad de núcleos",
    "cpu_generation": "Generación del procesador",
    "keyboard_detail": "Teclado",
    "transformer_type": "Tipo transformador",
    "power_adapter": "Tipo transformador",
    "plug_type": "Tipo de enchufe",
    "box_contents": "¿Qué incluye en la caja?",
}

_NUMERIC_ENRICHMENT_FIELDS = {
    "hdmi_ports",
    "usb_a_ports",
    "usb_c_ports",
    "announce_year",
    "cpu_cores",
}


def _field(value: Any = None, status: str = "RESEARCH_REQUIRED", source: str | None = None, method: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {"value": value, "status": status, "source": source, "method": method or status, "note": note}


def _compact_number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _load_specs(product: dict[str, Any]) -> dict[str, Any]:
    raw = product.get("atributos_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return {}
    specs = parsed.get("especificaciones") if isinstance(parsed, dict) else None
    return specs if isinstance(specs, dict) else {}


def _number(text: Any) -> float | None:
    if text is None:
        return None
    match = re.search(r"(-?\d+(?:[.,]\d+)?)", str(text))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _screen(specs: dict[str, Any], name: str) -> float | None:
    text = str(specs.get("PANTALLA") or name or "")
    match = re.search(r"(\d{2}(?:[.,]\d)?)\s*(?:PULG|\")", text, re.I)
    return float(match.group(1).replace(",", ".")) if match else None


def _ram(name: str) -> tuple[str | None, str | None]:
    match = re.search(r"(\d+)\s*GB\s*((?:LP)?DDR\d(?:-\d+)?)?", name or "", re.I)
    if not match:
        return None, None
    amount = f"{match.group(1)} GB"
    detail = f"{match.group(1)}GB"
    if match.group(2):
        detail += f" {match.group(2).upper()}"
    return amount, detail


def _processor_family(cpu: str) -> str | None:
    upper = cpu.upper()
    patterns = [
        (r"AMD\s+RYZEN\s+([3579])", lambda m: f"AMD Ryzen {m.group(1)}"),
        (r"INTEL\s+CORE\s+(I[3579])", lambda m: f"Intel Core {m.group(1).lower()}"),
        (r"INTEL\s+CELERON", lambda m: "Intel Celeron"),
        (r"INTEL\s+PENTIUM", lambda m: "Intel Pentium"),
    ]
    for pattern, formatter in patterns:
        match = re.search(pattern, upper)
        if match:
            return formatter(match)
    return None


def _panel(pantalla: str) -> str | None:
    upper = pantalla.upper()
    for value in ("OLED", "IPS", "TN", "VA"):
        if re.search(rf"\b{value}\b", upper):
            return value
    return None


def _resolution(pantalla: str) -> str | None:
    compact = pantalla.replace("×", "x").upper()
    if re.search(r"1920\s*X\s*1080", compact) or " FHD" in compact:
        return "FHD - 1080"
    if re.search(r"2560\s*X\s*1600", compact):
        return "WQXGA - 1600p"
    if re.search(r"3840\s*X\s*2160", compact):
        return "UHD - 4K"
    return None


def _color(comments: str) -> str | None:
    match = re.search(r"\bCOLOR\s+(.+?)(?:\s+KENSINGTON|\s+TPM|\s*$)", comments, re.I)
    if not match:
        return None
    value = " ".join(match.group(1).strip().split())
    return value.title().replace("(Gris)", "(Gris)")


def _charge_connector(comments: str) -> str | None:
    if "ROUND TIP" in comments.upper():
        return "Round Tip"
    if "USB-C" in comments.upper() or "USB C" in comments.upper():
        return "USB-C"
    return None


def _adapter(comments: str) -> str | None:
    match = re.search(r"ADAPTADOR DE PODER\s+(\d+W\s+[^\n]+?)(?:\s+C[ÁA]MARA|\s+CAMARA|\s+COLOR|$)", comments, re.I)
    if not match:
        return None
    value = " ".join(match.group(1).split())
    return f"Adaptador {value.title().replace('Round Tip', 'Round Tip').replace('Pin', 'pin')}"


def _package_dimensions(screen_inches: float) -> tuple[float, float, float]:
    if screen_inches <= 14.1:
        return 7.0, 31.0, 49.0
    if screen_inches < 16:
        return 7.4, 33.3, 53.3
    if screen_inches <= 16.2:
        return 7.8, 35.0, 55.0
    return 9.0, 37.0, 61.0


def _fallback_package(screen_inches: float, device_weight: float) -> dict[str, Any]:
    if 15.0 <= screen_inches < 16.0:
        return {
            "width_cm": 33,
            "length_cm": 54,
            "height_cm": 7,
            "weight_g": 2500,
            "status": "ESTIMATED",
            "method": "ESTIMATED",
            "source": "REGLA_STECH_EMPAQUE",
            "rule_code": "LAPTOP_15_X_DEFAULT",
            "confidence_grade": "E",
        }

    package_weight = estimate_package_weight(
        screen_inches=Decimal(str(screen_inches)),
        device_weight_kg=Decimal(str(device_weight)),
        is_gaming=False,
    )
    alto, ancho, largo = _package_dimensions(screen_inches)
    return {
        "width_cm": ancho,
        "length_cm": largo,
        "height_cm": alto,
        "weight_g": int(package_weight * 1000),
        "status": "ESTIMATED",
        "method": "ESTIMATED",
        "source": "Regla de empaque S-TECH",
        "rule_code": None,
        "confidence_grade": "E",
    }


def _title(product: dict[str, Any], specs: dict[str, Any], screen_inches: float | None, ram: str | None, color: str | None) -> str | None:
    brand = str(product.get("marca") or "").title()
    model = str(specs.get("MODELO") or "").strip()
    cpu = str(specs.get("CPU") or "")
    cpu_model = None
    match = re.search(r"((?:RYZEN|CORE|CELERON|PENTIUM)[^,]*?\b[A-Z]?\d{4,5}[A-Z]{0,2}\b)", cpu, re.I)
    if match:
        cpu_model = " ".join(match.group(1).split()).title().replace("Ryzen", "Ryzen").replace("Core", "Core")
    parts = ["Laptop", brand, model]
    if screen_inches:
        parts.append(f'{screen_inches:g}"')
    if cpu_model:
        parts.append(cpu_model)
    if ram:
        parts.append(ram.replace(" ", ""))
    if color:
        parts.append(color.split("(")[0].strip())
    value = " ".join(p for p in parts if p).strip()
    return value[:120] if value else None


def _gamut(processor: str | None) -> str | None:
    text = (processor or "").lower()
    if any(x in text for x in ("ryzen 7", "ryzen 9", "core i7", "core i9")):
        return "Gama alta"
    if any(x in text for x in ("ryzen 5", "core i5")):
        return "Gama media"
    if any(x in text for x in ("ryzen 3", "core i3", "celeron", "pentium")):
        return "Gama de entrada"
    return None


def _format_enrichment_value(field_code: str, row: dict[str, Any]) -> Any:
    value_text = row.get("value_text")
    if value_text is not None and str(value_text).strip() != "":
        return str(value_text).strip()

    number = _compact_number(row.get("value_number"))
    if number is None:
        return None
    unit = str(row.get("unit") or "").strip()

    if field_code == "ssd_capacity_gb":
        return f"{number} GB"
    if field_code == "refresh_rate_hz":
        return f"{number} Hz"
    if field_code == "battery_runtime_hours":
        return f"{number} h"
    if field_code in _NUMERIC_ENRICHMENT_FIELDS:
        return number
    if unit:
        return f"{number} {unit}"
    return number


def _apply_enrichments(fields: dict[str, dict[str, Any]], enrichments: list[dict[str, Any]] | None) -> None:
    for row in enrichments or []:
        field_code = str(row.get("field_code") or "").strip().lower()
        target = _ENRICHMENT_TO_COOLBOX.get(field_code)
        if not target or target not in fields:
            continue
        value = _format_enrichment_value(field_code, row)
        if value is None:
            continue
        method = str(row.get("method") or "VERIFIED").strip().upper()
        grade = str(row.get("confidence_grade") or "").strip().upper()
        source = "STECH_MCP.product_enrichment"
        if grade:
            source += f" [{grade}]"
        fields[target] = _field(
            value,
            method,
            source,
            method,
            note=f"approved enrichment field_code={field_code}",
        )


def build_coolbox_preview(
    product: dict[str, Any],
    *,
    package: dict[str, Any] | None = None,
    enrichments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = _load_specs(product)
    name = str(product.get("nombre") or "")
    source = "DB_DISTRIBUIDORES.dbo.V_PRD_PRODUCTO_ACTUAL / DELTRON"
    fields = {name: _field() for name in COOLBOX_FIELDS}

    pn = str(product.get("part_number") or product.get("partnumber") or "").strip()
    if pn:
        fields[COOLBOX_FIELDS[0]] = _field(pn, "DISTRIBUTOR", source)
        fields[COOLBOX_FIELDS[1]] = _field(len(pn), "DERIVED", source, "DERIVED")

    brand = str(product.get("marca") or "").strip() or None
    model = str(specs.get("MODELO") or "").strip() or None
    pantalla = str(specs.get("PANTALLA") or "")
    cpu = str(specs.get("CPU") or "")
    comments = str(specs.get("COMENTARIOS") or "")
    screen_inches = _screen(specs, name)
    ram, ram_detail = _ram(name)
    color = _color(comments)
    processor = _processor_family(cpu)

    fields["Rubro"] = _field("Computación", "DERIVED", "Regla Coolbox", "BUSINESS_RULE")
    fields["Familia"] = _field("Laptops", "DERIVED", "Regla Coolbox", "BUSINESS_RULE")
    fields["SubFamilia"] = _field("Laptops", "DERIVED", "Regla Coolbox", "BUSINESS_RULE")
    if processor and _gamut(processor):
        fields["GAMA"] = _field(_gamut(processor), "DERIVED", "Regla comercial por procesador", "BUSINESS_RULE")

    title = _title(product, specs, screen_inches, ram, color)
    if title:
        fields[COOLBOX_FIELDS[2]] = _field(title, "DERIVED", source, "DERIVED")
    if name:
        fields[COOLBOX_FIELDS[3]] = _field(name, "DISTRIBUTOR", source)

    if model:
        fields["Modelo"] = _field(model, "DISTRIBUTOR", source)
    if brand:
        fields["Marca"] = _field(brand, "DISTRIBUTOR", source)

    for field_name, spec_name in (("Alto", "ALTO"), ("Ancho", "ANCHO"), ("Profundidad", "LARGO")):
        value = _number(specs.get(spec_name))
        if value is not None:
            fields[field_name] = _field(value, "DISTRIBUTOR", source)
    device_weight = _number(specs.get("PESO"))
    if device_weight is not None:
        fields["Peso"] = _field(f"{device_weight:g} kg", "DISTRIBUTOR", source)

    if screen_inches is not None:
        fields["Tamaño de pantalla"] = _field(f'{screen_inches:g}"', "DISTRIBUTOR", source)
        fields["Tamaño (pulgadas)"] = _field(f'{screen_inches:g}"', "DERIVED", source, "DERIVED")
    if processor:
        fields["Procesador"] = _field(processor, "DISTRIBUTOR", source)
    if cpu:
        fields["Detalle del procesador"] = _field(" ".join(cpu.split()), "DISTRIBUTOR", source)
    if ram:
        fields["Memoria RAM"] = _field(ram, "DISTRIBUTOR", source)
    if ram_detail:
        fields["Detalle de memoria RAM"] = _field(ram_detail, "DISTRIBUTOR", source)

    panel = _panel(pantalla)
    if panel:
        fields["Tipo de panel"] = _field(panel, "DISTRIBUTOR", source)
    resolution = _resolution(pantalla)
    if resolution:
        fields["Resolución de pantalla"] = _field(resolution, "DISTRIBUTOR", source)

    disk_type = str(specs.get("TIPO") or "").strip()
    disk_interface = str(specs.get("INTERFAZ") or "").strip()
    if disk_type or disk_interface:
        fields["Detalle de discos"] = _field(" ".join(x for x in (disk_type, disk_interface) if x), "DISTRIBUTOR", source)

    independiente = str(specs.get("INDEPENDIENTE") or "").upper()
    if independiente == "NO":
        fields["Tipo de gráficos"] = _field("Integrado", "DISTRIBUTOR", source)
    elif independiente == "SI":
        fields["Tipo de gráficos"] = _field("Dedicado", "DISTRIBUTOR", source)

    os_text = str(specs.get("SISTEMA OPERATIVO") or "")
    if "NO INCLUYE" in os_text.upper():
        fields["Incluye sistema operativo"] = _field("No", "DISTRIBUTOR", source)

    rj45 = str(specs.get("RJ45") or "").strip()
    if rj45 and rj45 != "0":
        fields["Puerto de red"] = _field("Sí", "DISTRIBUTOR", source)
    puertos = str(specs.get("PUERTOS") or "")
    if "AUDIO" in puertos.upper() and "SI" in puertos.upper():
        fields["Entrada de audio"] = _field("Sí", "DISTRIBUTOR", source)
    bluetooth = str(specs.get("BLUETOOTH") or "").strip()
    if bluetooth:
        fields["Bluetooth"] = _field("Sí", "DISTRIBUTOR", source, note=f"Versión reportada: {bluetooth}")
    wireless = str(specs.get("WIRELESS") or "").strip()
    if wireless:
        fields["Wi-Fi"] = _field("Sí", "DISTRIBUTOR", source, note=wireless)
    if str(specs.get("WEBCAM") or "").upper() == "SI":
        fields["Cámara web"] = _field("Sí", "DISTRIBUTOR", source)
    parlante = str(specs.get("PARLANTE") or "").strip()
    if parlante:
        fields["Altavoz"] = _field("Sí", "DISTRIBUTOR", source, note=parlante)
    keyboard_lang = str(specs.get("IDIOMA DE TECLADO") or "").strip()
    if keyboard_lang:
        fields["Idioma del teclado"] = _field(keyboard_lang.title(), "DISTRIBUTOR", source)
    battery = str(specs.get("CAPACIDAD") or "").strip()
    if battery:
        number = _number(battery)
        fields["Batería"] = _field(f"{number:g} Wh" if number is not None else battery, "DISTRIBUTOR", source)
    battery_type = str(specs.get("TIPO BATERIA") or "").strip()
    if battery_type:
        fields["Tipo de batería"] = _field(battery_type.title(), "DISTRIBUTOR", source)
    if color:
        fields["Color"] = _field(color, "DISTRIBUTOR", source)

    connector = _charge_connector(comments)
    if connector:
        fields["Conector de carga"] = _field(connector, "DISTRIBUTOR", source)
    adapter = _adapter(comments)
    if adapter:
        fields["Requiere transformador"] = _field("Sí", "DISTRIBUTOR", source)
        fields["Tipo transformador"] = _field(adapter, "DISTRIBUTOR", source)
        fields["incluye transformador"] = _field("Sí", "DISTRIBUTOR", source)

    info_parts = [f"Part Number: {pn}" if pn else None]
    gtin = product.get("ean") or product.get("upc")
    if gtin:
        info_parts.append(f"EAN/UPC: {gtin}")
    info = " | ".join(x for x in info_parts if x)
    if info:
        fields["Información adicional"] = _field(info, "DERIVED", source, "DERIVED")

    resolved_package = package
    if resolved_package is None and screen_inches is not None and device_weight is not None:
        resolved_package = _fallback_package(screen_inches, device_weight)

    if resolved_package is not None:
        package_source = str(resolved_package.get("source") or "STECH_MCP")
        package_status = str(resolved_package.get("status") or resolved_package.get("method") or "ESTIMATED")
        package_method = str(resolved_package.get("method") or package_status)
        rule_code = resolved_package.get("rule_code")
        confidence = resolved_package.get("confidence_grade")
        notes = []
        if rule_code:
            notes.append(f"rule_code={rule_code}")
        if confidence:
            notes.append(f"confidence={confidence}")
        package_note = " | ".join(notes) or None

        fields["Peso (g)"] = _field(_compact_number(resolved_package.get("weight_g")), package_status, package_source, package_method, package_note)
        fields["Alto (cm)"] = _field(_compact_number(resolved_package.get("height_cm")), package_status, package_source, package_method, package_note)
        fields["Ancho (cm)"] = _field(_compact_number(resolved_package.get("width_cm")), package_status, package_source, package_method, package_note)
        fields["Largo  (cm)"] = _field(_compact_number(resolved_package.get("length_cm")), package_status, package_source, package_method, package_note)

    _apply_enrichments(fields, enrichments)

    # Los dos ejemplos completos de la plantilla real "Laptops-All in one"
    # dejan estos campos vacíos. Por tanto, si no hay una fuente confiable,
    # no deben convertirse artificialmente en trabajo pendiente ni bloquear
    # el readiness. Si luego existe enrichment aprobado, este ya fue aplicado
    # arriba y el valor real se conserva.
    for optional_name in (
        "Memoria unificada",
        "Sistema de refrigeración",
        "Duración de la batería",
        "Capacidad de disco eMMC ",
        "Consumo",
        "Tipo de enchufe",
    ):
        current = fields[optional_name]
        if current.get("value") is None and str(current.get("status") or "").upper() == "RESEARCH_REQUIRED":
            fields[optional_name] = _field(
                None,
                "OPTIONAL",
                "Coolbox template Laptops-All in one",
                "OPTIONAL",
                note="Campo vacío en filas completas de referencia; no bloquear sin evidencia adicional.",
            )

    for optional in ("CROSS 1", "CROSS 2", "CROSS 3"):
        fields[optional] = _field(None, "OPTIONAL", "Coolbox")
    for seller_input in ("Precio Lista (Full )", "Precio Base (Especial)", "Fecha de Inicio", "Fecha Fin", "Stock"):
        fields[seller_input] = _field(None, "MARKETPLACE_INPUT", "S-TECH / Seller")

    ordered = [{"field": field_name, **fields[field_name]} for field_name in COOLBOX_FIELDS]
    counts = Counter(row["status"] for row in ordered)
    return {
        "template": TEMPLATE_NAME,
        "field_count": len(COOLBOX_FIELDS),
        "partnumber": pn,
        "fields": ordered,
        "summary": dict(counts),
        "ready_for_research": [row["field"] for row in ordered if row["status"] == "RESEARCH_REQUIRED"],
        "estimated_fields": [row["field"] for row in ordered if row["status"] == "ESTIMATED"],
    }
