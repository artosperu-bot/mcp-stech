from __future__ import annotations

from typing import Any

from stech_mcp.domain.market_models import STRONG_ACTIONS


def _bounded(value: float | int | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def score_opportunity(factors: dict[str, float | None], weights: dict[str, float]) -> dict[str, float]:
    total_weight = sum(max(0.0, float(weight)) for weight in weights.values())
    used_weight = 0.0
    weighted = 0.0
    for name, weight in weights.items():
        weight_value = max(0.0, float(weight))
        score = _bounded(factors.get(name))
        if score is None or weight_value == 0:
            continue
        used_weight += weight_value
        weighted += score * weight_value

    if used_weight == 0:
        opportunity = 0.0
    else:
        opportunity = weighted / used_weight
    coverage = 0.0 if total_weight == 0 else used_weight / total_weight * 100.0
    return {
        "opportunity_score": round(opportunity, 2),
        "coverage_pct": round(coverage, 2),
    }


def score_confidence(inputs: dict[str, Any]) -> float:
    identity = 100.0 if bool(inputs.get("identity_verified")) else 0.0
    supplier_freshness = _bounded(inputs.get("supplier_freshness")) or 0.0
    competitor_freshness = _bounded(inputs.get("competitor_freshness")) or 0.0
    competitor_count = min(max(float(inputs.get("competitor_count") or 0), 0.0), 5.0) / 5.0 * 100.0
    history_depth = min(max(float(inputs.get("history_depth") or 0), 0.0), 20.0) / 20.0 * 100.0
    internal_quality = _bounded(inputs.get("internal_signal_quality")) or 0.0
    observed_pct = _bounded(inputs.get("observed_input_pct")) or 0.0

    score = (
        identity * 0.20
        + supplier_freshness * 0.15
        + competitor_freshness * 0.20
        + competitor_count * 0.10
        + history_depth * 0.10
        + internal_quality * 0.10
        + observed_pct * 0.15
    )
    return round(score, 2)


def score_risk(inputs: dict[str, Any]) -> float:
    margin = _bounded(inputs.get("margin_headroom_score")) or 0.0
    volatility = _bounded(inputs.get("price_volatility_score")) or 0.0
    price_war = 100.0 if bool(inputs.get("price_war")) else 0.0
    supplier = _bounded(inputs.get("supplier_risk_score")) or 0.0
    decline = _bounded(inputs.get("market_decline_score")) or 0.0
    sellers = _bounded(inputs.get("seller_pressure_score")) or 0.0
    staleness = _bounded(inputs.get("staleness_score")) or 0.0
    aging = _bounded(inputs.get("inventory_aging_score")) or 0.0

    score = (
        margin * 0.18
        + volatility * 0.14
        + price_war * 0.18
        + supplier * 0.12
        + decline * 0.12
        + sellers * 0.08
        + staleness * 0.10
        + aging * 0.08
    )
    return round(score, 2)


def gate_action(
    action_code: str,
    confidence_score: float,
    risk_score: float,
    *,
    minimum_confidence: float = 70.0,
    maximum_risk: float = 65.0,
) -> str:
    action = str(action_code or "").strip().upper()
    if action in STRONG_ACTIONS and (float(confidence_score) < minimum_confidence or float(risk_score) > maximum_risk):
        return "INVESTIGAR"
    return action
