from stech_mcp.services.rules.laptop_gama_v1 import derive_laptop_gama_v1


def test_entry_laptop_is_baja():
    result = derive_laptop_gama_v1(
        {
            "cpu_model": "Intel Celeron N4020",
            "ram_gb": 4,
            "storage_gb": 128,
            "gpu_model": "Intel UHD Graphics 600",
            "resolution": "1366x768",
        }
    )

    assert result is not None
    assert result.value == "Baja"
    assert result.rule_code == "LAPTOP_GAMA_V1"
    assert result.rule_version == 1


def test_mainstream_productivity_laptop_is_media():
    result = derive_laptop_gama_v1(
        {
            "cpu_model": "AMD Ryzen 5 7520U",
            "ram_gb": 16,
            "storage_gb": 512,
            "gpu_model": "AMD Radeon 610M",
            "resolution": "1920x1080",
            "refresh_rate_hz": 60,
        }
    )

    assert result is not None
    assert result.value == "Media"
    assert result.confidence >= 0.75


def test_high_performance_gaming_laptop_is_alta():
    result = derive_laptop_gama_v1(
        {
            "cpu_model": "Intel Core i7-14650HX",
            "ram_gb": 32,
            "storage_gb": 1024,
            "gpu_model": "NVIDIA GeForce RTX 4060 Laptop GPU",
            "resolution": "2560x1600",
            "refresh_rate_hz": 165,
        }
    )

    assert result is not None
    assert result.value == "Alta"
    assert "RTX 4060" in result.explanation


def test_high_price_alone_does_not_turn_weak_laptop_into_alta():
    result = derive_laptop_gama_v1(
        {
            "cpu_model": "Intel Celeron N4020",
            "ram_gb": 4,
            "storage_gb": 128,
            "gpu_model": "Intel UHD Graphics 600",
        },
        context={"deltron_price_percentile": 0.98},
    )

    assert result is not None
    assert result.value == "Baja"


def test_insufficient_inputs_do_not_invent_gama():
    assert derive_laptop_gama_v1({"ram_gb": 16}) is None
