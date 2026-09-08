from stech_mcp.services.fact_normalizers import (
    normalize_bluetooth,
    normalize_capacity_wh,
    normalize_dimensions,
    normalize_duration_hours,
    normalize_frequency_range,
    normalize_ip_rating,
    normalize_power_w,
    normalize_ram_gb,
    normalize_resolution,
    normalize_storage_gb,
    normalize_weight,
)


def test_normalizes_common_units_without_guessing():
    assert normalize_weight("1.65 kg") == {"value": 1.65, "unit": "kg"}
    assert normalize_weight("250 g", target_unit="kg") == {"value": 0.25, "unit": "kg"}
    assert normalize_bluetooth("Bluetooth 5.4") == "5.4"
    assert normalize_ip_rating("IP67 waterproof") == "IP67"
    assert normalize_power_w("30 W RMS") == {"value": 30, "unit": "W"}
    assert normalize_capacity_wh("68 Wh") == {"value": 68, "unit": "Wh"}
    assert normalize_duration_hours("hasta 12 horas") == {"value": 12, "unit": "h"}


def test_normalizes_dimensions_frequency_memory_storage_and_resolution():
    assert normalize_dimensions("100 x 80 x 50 mm") == {"value": [100, 80, 50], "unit": "mm"}
    assert normalize_dimensions("10 x 8 x 5 cm") == {"value": [100, 80, 50], "unit": "mm"}
    assert normalize_frequency_range("65 Hz - 20 kHz") == {"value": [65, 20000], "unit": "Hz"}
    assert normalize_ram_gb("16 GB LPDDR5") == {"value": 16, "unit": "GB"}
    assert normalize_storage_gb("512GB SSD") == {"value": 512, "unit": "GB"}
    assert normalize_storage_gb("1 TB SSD") == {"value": 1024, "unit": "GB"}
    assert normalize_resolution("1920 × 1080") == "1920x1080"


def test_ambiguous_or_unitless_values_are_rejected():
    assert normalize_weight("peso ligero") is None
    assert normalize_power_w("30") is None
    assert normalize_dimensions("100 x 80") is None
    assert normalize_frequency_range("20 kHz") is None
    assert normalize_bluetooth("Bluetooth") is None
