from stech_mcp.background_config import BackgroundConfig


def test_background_config_defaults_and_bounds(monkeypatch):
    for name in (
        "BACKGROUND_ENABLED",
        "SCANNER_ENABLED",
        "SCAN_INTERVAL_MINUTES",
        "MAX_WORKERS",
        "MAX_RESEARCH_JOBS",
        "MAX_IMAGE_JOBS",
        "MAX_JOBS_PER_SCAN",
        "JOB_TIMEOUT_MINUTES",
        "MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)
    cfg = BackgroundConfig.from_env()
    assert cfg.background_enabled is True
    assert cfg.scanner_enabled is True
    assert cfg.scan_interval_minutes == 10
    assert cfg.max_workers == 3
    assert cfg.max_research_jobs == 2
    assert cfg.max_image_jobs == 1
    assert cfg.max_jobs_per_scan == 100
    assert cfg.max_retries == 3


def test_background_config_clamps_unsafe_values(monkeypatch):
    monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "0")
    monkeypatch.setenv("MAX_WORKERS", "99")
    monkeypatch.setenv("MAX_JOBS_PER_SCAN", "5000")
    monkeypatch.setenv("MAX_RETRIES", "0")
    cfg = BackgroundConfig.from_env()
    assert cfg.scan_interval_minutes >= 1
    assert cfg.max_workers <= 16
    assert cfg.max_jobs_per_scan <= 500
    assert cfg.max_retries >= 1
