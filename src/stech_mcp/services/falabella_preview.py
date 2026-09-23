from __future__ import annotations

import re
from collections import Counter
from typing import Any

from stech_mcp.services.coolbox_preview import build_coolbox_preview

TEMPLATE_NAME = "ProductCreationTemplate / Portátiles|notebooks"
CATEGORY_VALUE = "432 - Electrónica / Computación / Computadores / Portátiles|notebooks"

FALABELLA_FIELDS = [
    "Nombre #39", "Marca #26", "Modelo #32", "Descripción #53", "Categoría primaria #1",
    "País de producción #59", "SKU del vendedor #29", "Código de barras #56", "Variación #1700",
    "QuantityFalabella #25", "PriceFalabella #52", "SalePriceFalabella #18",
    "SaleStartDateFalabella #45", "SaleEndDateFalabella #31", "AnoFabricacion #34948",
    "TipoDePortatil #396393", "NucleosDelProcesador #1611", "TamanoDelaPantalla #1703",
    "Alto #10795", "Ancho #10794", "SellerWarrantyInMonths #614607", "Largo #10793",
    "MarcaProcesador #31387", "MarcaTarjetaGrafica #31361", "PantallaTouch #36077",
    "ProcesadorEspecificoTxt #31221", "Profundidad #10801", "TarjetaGraficaEspecifica #31224",
    "MemoriaRam #1540", "SistemaOperativo #1655", "SistemaOperativoEspecifico #1607",
    "CantidadDePuertosHdmi #1645", "CantidadDePuertosUsb #1597", "CapacidadDeAlmacenamiento #1538",
    "CapacidadDeLaTarjetaDeVideo #1562", "Caracteristicas #1657", "CaracteristicasDeLaPantalla #1705",
    "Color #1532", "ConectividadConexion #1651", "CuentaConBluetooth #1568", "Dimensiones #1619",
    "DiscoDuroSecundario #1572", "DuracionDeLaBateriaHrs #1692", "Rendimiento #1666",
    "RequiereSerialNumber #2657", "ResolucionDePantalla #1547", "SistemaDeSonido #1560",
    "TasaDeRefrescoNativa #1554", "VelocidadDeImagen #1593", "VelocidadDeProcesamientoGhz #1616",
    "Condición del Producto #22", "NameCn #133815", "NameEn #133816",
    "Detalles de la condición del Producto #49", "Garantía del producto #35", "Garantía del vendedor #9",
    "Contenido del paquete #19", "Ancho del paquete #60", "Largo del paquete #33", "Alto del paquete #47",
    "Peso del paquete #8", "Imagen principal #IM1", "Imagen2 #IM2", "Imagen3 #IM3", "Imagen4 #IM4",
    "Imagen5 #IM5", "Imagen6 #IM6", "Imagen7 #IM7", "Imagen8 #IM8",
]

_REQUIRED_FIELDS = [
    "Nombre #39", "Marca #26", "Descripción #53", "Categoría primaria #1", "SKU del vendedor #29",
    "Código de barras #56", "Variación #1700", "AnoFabricacion #34948", "TipoDePortatil #396393",
    "NucleosDelProcesador #1611", "TamanoDelaPantalla #1703", "Ancho del paquete #60",
    "Largo del paquete #33", "Alto del paquete #47", "Peso del paquete #8", "Imagen principal #IM1",
]


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    match = re.search(r"(-?\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    return int(number) if number.is_integer() else number


def _compact_ram(value: Any) -> str | None:
    number = _number(value)
    return f"{int(number)}GB" if number is not None else None


def _cores(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    mapping = {
        1: "Single core", 2: "Dual core", 3: "Triple core", 4: "Quad core",
        6: "Hexa core", 8: "Octa core", 10: "Deca core", 11: "11 core",
        12: "12 core", 14: "14 core", 16: "16 core", 24: "24 core",
    }
    return mapping.get(int(number), f"{int(number)} core")


def _processor_brand(value: Any) -> str | None:
    text = str(value or "").strip()
    normalized = text.lower()
    if normalized == "amd ryzen 5":
        return "Amd Ryzen 5"
    if normalized in {"amd ryzen", "amd ryzen 3", "amd ryzen 7", "amd ryzen 9"}:
        return text.replace("Amd", "AMD")
    if re.fullmatch(r"intel core i[3579]", normalized):
        suffix = normalized.rsplit(" ", 1)[-1]
        return f"Intel Core {suffix}"
    if normalized in {"intel celeron", "intel pentium"}:
        return "Intel Celeron" if normalized.endswith("celeron") else "Intel Pentium"
    return text or None


def _resolution(value: Any) -> str | None:
    text = str(value or "").upper()
    if "FHD" in text or "1080" in text:
        return "FHD"
    if "4K" in text or "2160" in text:
        return "4K UHD"
    if "HD" in text or "720" in text:
        return "HD"
    return None


def _color(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"\(([^)]+)\)\s*$", text)
    return match.group(1).strip() if match else (text or None)


def _cpu_specific(value: Any) -> str | None:
    text = str(value or "").strip()
    return text.split(",", 1)[0].strip() if text else None


def _max_ghz(value: Any) -> str | None:
    numbers = [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*GHz", str(value or ""), re.I)]
    return f"{max(numbers):g} GHz" if numbers else None


def _coolbox_values(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        str(row.get("field")): row.get("value")
        for row in (preview.get("fields") or [])
        if isinstance(row, dict) and row.get("field")
    }


def build_falabella_preview(
    *,
    product: dict[str, Any],
    package: dict[str, Any] | None = None,
    enrichments: list[dict[str, Any]] | None = None,
    image_urls: list[str] | None = None,
    marketplace_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coolbox = build_coolbox_preview(product, package=package, enrichments=enrichments)
    source = _coolbox_values(coolbox)
    seller = marketplace_inputs or {}
    urls: list[str] = []
    seen: set[str] = set()
    for value in image_urls or []:
        url = str(value or "").strip()
        if not url or url in seen:
            continue
        urls.append(url)
        seen.add(url)
        if len(urls) == 8:
            break

    fields = {name: None for name in FALABELLA_FIELDS}
    pn = str(product.get("part_number") or product.get("partnumber") or "").strip().upper()
    gtin = str(product.get("ean") or product.get("upc") or "").strip() or None

    title_key = "NOMBRE /TÍTULO DE PRODUCTO\nMax 120 caracteres\nTipo de producto+Marca+característica (s) principales + color"
    desc_key = "DESCRIPCIÓN DE PRODUCTO\n(Con características importantes)"
    fields.update({
        "Nombre #39": source.get(title_key) or product.get("nombre"),
        "Marca #26": source.get("Marca") or product.get("marca"),
        "Modelo #32": source.get("Modelo"),
        "Descripción #53": source.get(desc_key) or product.get("nombre"),
        "Categoría primaria #1": CATEGORY_VALUE,
        "SKU del vendedor #29": pn or None,
        "Código de barras #56": gtin,
        "Variación #1700": "...",
        "QuantityFalabella #25": seller.get("quantity"),
        "PriceFalabella #52": seller.get("price"),
        "SalePriceFalabella #18": seller.get("sale_price"),
        "SaleStartDateFalabella #45": seller.get("sale_start"),
        "SaleEndDateFalabella #31": seller.get("sale_end"),
        "AnoFabricacion #34948": _number(source.get("Año")),
        "TipoDePortatil #396393": "Laptop",
        "NucleosDelProcesador #1611": _cores(source.get("Cantidad de núcleos")),
        "TamanoDelaPantalla #1703": _number(source.get("Tamaño de pantalla")),
        "Alto #10795": _number(source.get("Alto")),
        "Ancho #10794": _number(source.get("Ancho")),
        "Largo #10793": _number(source.get("Profundidad")),
        "MarcaProcesador #31387": _processor_brand(source.get("Procesador")),
        "MarcaTarjetaGrafica #31361": source.get("Procesador gráfico"),
        "PantallaTouch #36077": source.get("Pantalla táctil"),
        "ProcesadorEspecificoTxt #31221": _cpu_specific(source.get("Detalle del procesador")),
        "Profundidad #10801": f"{_number(source.get('Profundidad')):g} cm" if _number(source.get("Profundidad")) is not None else None,
        "TarjetaGraficaEspecifica #31224": source.get("Detalle del procesador gráfico"),
        "MemoriaRam #1540": _compact_ram(source.get("Memoria RAM")),
        "CantidadDePuertosHdmi #1645": _number(source.get("Puertos HDMI")),
        "CantidadDePuertosUsb #1597": sum(int(_number(source.get(k)) or 0) for k in ("Puertos USB", "Puertos USB Tipo-C")) or None,
        "CapacidadDeAlmacenamiento #1538": source.get("Capacidad de disco sólido (SSD)"),
        "CapacidadDeLaTarjetaDeVideo #1562": "No aplica",
        "CaracteristicasDeLaPantalla #1705": "Anti glare" if str(source.get("Tipo de panel") or "").strip() else None,
        "Color #1532": _color(source.get("Color")),
        "CuentaConBluetooth #1568": source.get("Bluetooth"),
        "Dimensiones #1619": (
            f"{_number(source.get('Alto')):g} cm x {_number(source.get('Profundidad')):g} cm x {_number(source.get('Ancho')):g} cm"
            if all(_number(source.get(k)) is not None for k in ("Alto", "Profundidad", "Ancho")) else None
        ),
        "DiscoDuroSecundario #1572": "No aplica",
        "RequiereSerialNumber #2657": "Si",
        "ResolucionDePantalla #1547": _resolution(source.get("Resolución de pantalla")),
        "TasaDeRefrescoNativa #1554": str(source.get("Tasa de refresco laptop") or "").replace(" ", "") or None,
        "VelocidadDeImagen #1593": str(source.get("Tasa de refresco laptop") or "").replace(" ", "") or None,
        "VelocidadDeProcesamientoGhz #1616": _max_ghz(source.get("Detalle del procesador")),
        "Condición del Producto #22": "Nuevo",
        "Detalles de la condición del Producto #49": "Producto nuevo, sellado y sin uso.",
        "Contenido del paquete #19": source.get("¿Qué incluye en la caja?"),
        "Ancho del paquete #60": _number(source.get("Ancho (cm)")),
        "Largo del paquete #33": _number(source.get("Largo  (cm)")),
        "Alto del paquete #47": _number(source.get("Alto (cm)")),
        "Peso del paquete #8": (_number(source.get("Peso (g)")) / 1000) if _number(source.get("Peso (g)")) is not None else None,
    })

    for index, url in enumerate(urls, start=1):
        fields["Imagen principal #IM1" if index == 1 else f"Imagen{index} #IM{index}"] = url

    required_missing = [name for name in _REQUIRED_FIELDS if not _present(fields.get(name))]
    ordered = []
    for name in FALABELLA_FIELDS:
        value = fields[name]
        if name in required_missing:
            status = "REQUIRED_MISSING"
        elif name.startswith("Imagen") and _present(value):
            status = "VTEX_ASSET"
        elif name in {"QuantityFalabella #25", "PriceFalabella #52", "SalePriceFalabella #18", "SaleStartDateFalabella #45", "SaleEndDateFalabella #31"} and not _present(value):
            status = "MARKETPLACE_INPUT"
        elif _present(value):
            status = "MAPPED"
        else:
            status = "OPTIONAL"
        ordered.append({"field": name, "value": value, "status": status})

    summary = Counter(row["status"] for row in ordered)
    return {
        "template": TEMPLATE_NAME,
        "category_value": CATEGORY_VALUE,
        "partnumber": pn,
        "field_count": len(FALABELLA_FIELDS),
        "image_count": len(urls),
        "image_source": "VTEX_ASSETS" if urls else None,
        "readiness_state": "READY" if not required_missing else "BLOCKED",
        "required_missing": required_missing,
        "fields": ordered,
        "summary": dict(summary),
    }
