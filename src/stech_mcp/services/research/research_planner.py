from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from stech_mcp.domain.product_schema import normalize_category_code, normalize_field_code


@dataclass(frozen=True, slots=True)
class ResearchQuery:
    partnumber: str
    field_code: str
    category_code: str
    query: str
    domains: tuple[str, ...]
    stage: str


_DEFAULT_MANUFACTURER_DOMAINS: dict[str, tuple[str, ...]] = {
    "ACER": ("acer.com",),
    "APPLE": ("apple.com",),
    "ASUS": ("asus.com",),
    "EPSON": ("epson.com",),
    "HP": ("hp.com",),
    "JBL": ("jbl.com",),
    "KINGSTON": ("kingston.com",),
    "LENOVO": ("lenovo.com",),
    "LOGITECH": ("logitech.com",),
}

_FIELD_TERMS = {
    "cpu_model": "processor CPU",
    "ram_gb": "RAM memory",
    "storage_gb": "storage SSD capacity",
    "storage_type": "storage type SSD NVMe",
    "screen_inches": "screen size",
    "resolution": "screen resolution",
    "wifi": "Wi-Fi wireless",
    "bluetooth_version": "Bluetooth version",
    "battery_wh": "battery Wh capacity",
    "battery_capacity_wh": "battery Wh capacity",
    "battery_runtime_hours": "battery life hours",
    "weight_kg": "weight",
    "weight_g": "weight",
    "dimensions_mm": "dimensions",
    "os_name": "operating system",
    "speaker_power_w": "speaker power W",
    "ip_rating": "IP rating water resistance",
    "frequency_response_hz": "frequency response Hz",
    "box_contents": "box contents included",
    "driver_size_mm": "driver size mm",
    "anc": "active noise cancellation ANC",
    "transparency_mode": "transparency ambient mode",
    "codec": "audio codec",
    "microphone": "microphone",
    "charging_time_hours": "charging time hours",
    "impedance_ohm": "impedance ohm",
    "sensitivity_db": "sensitivity dB",
}


class ResearchPlanner:
    def __init__(self, *, manufacturer_domains: dict[str, tuple[str, ...]] | None = None) -> None:
        self.manufacturer_domains = dict(_DEFAULT_MANUFACTURER_DOMAINS)
        if manufacturer_domains:
            for brand, domains in manufacturer_domains.items():
                self.manufacturer_domains[str(brand).strip().upper()] = tuple(domains)

    def plan(
        self,
        partnumber: str,
        brand: str,
        category_code: str,
        pending_fields: Iterable[str],
    ) -> list[ResearchQuery]:
        pn = str(partnumber or "").strip().upper()
        normalized_brand = str(brand or "").strip().upper()
        category = normalize_category_code(category_code)
        if not pn:
            raise ValueError("partnumber is required")

        domains = self.manufacturer_domains.get(normalized_brand, ())
        fields: list[str] = []
        for raw in pending_fields:
            code = normalize_field_code(raw)
            if code and code not in fields:
                fields.append(code)

        result: list[ResearchQuery] = []
        quoted_pn = f'"{pn}"'
        brand_text = normalized_brand if normalized_brand else "product"
        for field_code in fields:
            terms = _FIELD_TERMS.get(field_code, field_code.replace("_", " "))
            result.append(
                ResearchQuery(
                    partnumber=pn,
                    field_code=field_code,
                    category_code=category,
                    query=f"{quoted_pn} {brand_text} {terms} specifications",
                    domains=domains,
                    stage="MANUFACTURER",
                )
            )
            result.append(
                ResearchQuery(
                    partnumber=pn,
                    field_code=field_code,
                    category_code=category,
                    query=f"{quoted_pn} {brand_text} {terms} datasheet manual filetype:pdf",
                    domains=domains,
                    stage="OFFICIAL_DOCUMENT",
                )
            )
        return result
