from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from stech_mcp.domain.derived_fact import DerivedFact


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _cpu_score(value: Any) -> float | None:
    text = str(value or "").upper()
    if not text:
        return None
    if any(token in text for token in ("CELERON", "PENTIUM", "ATHLON", "N4020", "N4500")):
        score = -1.0
    elif any(token in text for token in ("CORE ULTRA 9", "CORE I9", "RYZEN 9")):
        score = 5.0
    elif any(token in text for token in ("CORE ULTRA 7", "CORE I7", "RYZEN 7")):
        score = 4.0
    elif any(token in text for token in ("CORE ULTRA 5", "CORE I5", "RYZEN 5")):
        score = 2.5
    elif any(token in text for token in ("CORE I3", "RYZEN 3")):
        score = 1.0
    elif re.search(r"\bINTEL\s+N\d{3,4}\b", text):
        score = -0.5
    else:
        return None

    if any(token in text for token in ("HX", "HK")):
        score += 0.5
    elif re.search(r"\dH\b", text):
        score += 0.25
    return score


def _ram_score(value: Any) -> float | None:
    ram = _number(value)
    if ram is None:
        return None
    if ram <= 4:
        return -1.0
    if ram < 16:
        return 0.0
    if ram < 32:
        return 1.0
    if ram < 64:
        return 2.0
    return 2.5


def _storage_score(value: Any) -> float | None:
    storage = _number(value)
    if storage is None:
        return None
    if storage <= 128:
        return -0.5
    if storage < 512:
        return 0.0
    if storage < 1024:
        return 0.5
    return 1.0


def _gpu_score(value: Any) -> float | None:
    text = str(value or "").upper()
    if not text:
        return None
    if any(token in text for token in ("RTX 4090", "RTX 4080", "RTX 4070", "RTX 4060", "RX 7900", "RX 7800", "RX 7700", "RX 7600")):
        return 3.0
    if any(token in text for token in ("RTX 4050", "RTX 3080", "RTX 3070", "RTX 3060", "RTX 3050")):
        return 2.0
    if any(token in text for token in ("GEFORCE GTX", "GEFORCE RTX", "RADEON RX")):
        return 1.5
    if any(token in text for token in ("INTEL UHD", "INTEL IRIS", "RADEON 610M", "RADEON 680M", "RADEON 780M", "INTEGRATED", "INTEGRADA")):
        return 0.0
    return 0.0


def _screen_score(resolution: Any, refresh_rate_hz: Any) -> tuple[float, int]:
    score = 0.0
    signals = 0
    resolution_text = str(resolution or "").upper().replace(" ", "")
    if resolution_text:
        signals += 1
        match = re.search(r"(\d{3,4})[X×](\d{3,4})", resolution_text)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            if width >= 2560 or height >= 1440:
                score += 0.5
    refresh = _number(refresh_rate_hz)
    if refresh is not None:
        signals += 1
        if refresh >= 120:
            score += 0.5
    return score, signals


def derive_laptop_gama_v1(
    facts: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> DerivedFact | None:
    """Derive Baja/Media/Alta from reproducible laptop technical signals.

    Deltron relative price is deliberately a weak secondary signal and can never
    lift a technically weak machine directly into a high tier.
    """

    context = dict(context or {})
    inputs = {
        key: facts.get(key)
        for key in (
            "cpu_model",
            "ram_gb",
            "storage_gb",
            "gpu_model",
            "resolution",
            "refresh_rate_hz",
        )
        if facts.get(key) not in (None, "")
    }
    cpu = _cpu_score(facts.get("cpu_model"))
    if cpu is None:
        return None

    technical_scores: list[float] = [cpu]
    evidence_signals = 1
    for scorer, field_code in (
        (_ram_score, "ram_gb"),
        (_storage_score, "storage_gb"),
        (_gpu_score, "gpu_model"),
    ):
        score = scorer(facts.get(field_code))
        if score is not None:
            technical_scores.append(score)
            evidence_signals += 1

    screen_score, screen_signals = _screen_score(
        facts.get("resolution"), facts.get("refresh_rate_hz")
    )
    technical_scores.append(screen_score)
    evidence_signals += screen_signals

    # CPU plus at least two additional technical observations are required.
    if evidence_signals < 3:
        return None

    score = sum(technical_scores)
    percentile = _number(context.get("deltron_price_percentile"))
    if percentile is not None:
        inputs["deltron_price_percentile"] = percentile
        if percentile >= 0.85:
            score += 0.25
        elif percentile <= 0.15:
            score -= 0.25

    if score >= 7.0:
        value = "Alta"
    elif score >= 2.5:
        value = "Media"
    else:
        value = "Baja"

    confidence = min(0.95, 0.55 + 0.07 * evidence_signals)
    highlights = [str(facts.get("cpu_model"))]
    for key in ("gpu_model", "ram_gb", "storage_gb", "resolution", "refresh_rate_hz"):
        if facts.get(key) not in (None, ""):
            highlights.append(str(facts.get(key)))
    explanation = (
        f"Clasificación {value} por señales técnicas: "
        + ", ".join(highlights)
        + f"; puntaje reproducible {score:.2f}."
    )

    return DerivedFact(
        field_code="gama",
        value=value,
        rule_code="LAPTOP_GAMA_V1",
        rule_version=1,
        inputs=inputs,
        confidence=round(confidence, 2),
        explanation=explanation,
        derived_at=datetime.now(timezone.utc),
    )
