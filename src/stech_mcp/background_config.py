from __future__ import annotations

from dataclasses import dataclass
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class BackgroundConfig:
    background_enabled: bool
    scanner_enabled: bool
    scan_interval_minutes: int
    max_workers: int
    max_research_jobs: int
    max_image_jobs: int
    max_jobs_per_scan: int
    job_timeout_minutes: int
    max_retries: int

    @classmethod
    def from_env(cls) -> "BackgroundConfig":
        return cls(
            background_enabled=_env_bool("BACKGROUND_ENABLED", True),
            scanner_enabled=_env_bool("SCANNER_ENABLED", True),
            scan_interval_minutes=_env_int("SCAN_INTERVAL_MINUTES", 10, 1, 1440),
            max_workers=_env_int("MAX_WORKERS", 3, 1, 16),
            max_research_jobs=_env_int("MAX_RESEARCH_JOBS", 2, 1, 16),
            max_image_jobs=_env_int("MAX_IMAGE_JOBS", 1, 1, 16),
            max_jobs_per_scan=_env_int("MAX_JOBS_PER_SCAN", 100, 1, 500),
            job_timeout_minutes=_env_int("JOB_TIMEOUT_MINUTES", 30, 1, 1440),
            max_retries=_env_int("MAX_RETRIES", 3, 1, 10),
        )
