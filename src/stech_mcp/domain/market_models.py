from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


MarketAction = Literal[
    "COMPRAR",
    "PUBLICAR",
    "SUBIR_STOCK",
    "BAJAR_PRECIO",
    "SUBIR_PRECIO",
    "MANTENER",
    "LIQUIDAR",
    "NO_COMPETIR",
    "REVISAR_PROVEEDOR",
    "INVESTIGAR",
]

PricingStrategy = Literal["BALANCED", "MARGIN", "VOLUME", "CLEARANCE"]

STRONG_ACTIONS: frozenset[str] = frozenset(
    {"COMPRAR", "PUBLICAR", "SUBIR_STOCK", "BAJAR_PRECIO", "SUBIR_PRECIO", "LIQUIDAR"}
)

DEFAULT_OPPORTUNITY_WEIGHTS: dict[str, float] = {
    "profitability": 30.0,
    "competitiveness": 20.0,
    "supplier_availability": 15.0,
    "demand_rotation": 15.0,
    "market_stability": 10.0,
    "inventory_pressure": 10.0,
}


@dataclass(frozen=True)
class PricingInputs:
    product_cost_pen: Decimal
    commission_pct: Decimal
    payment_fee_pct: Decimal
    fixed_fee_pen: Decimal
    shipping_cost_pen: Decimal
    minimum_margin_pct: Decimal
    minimum_contribution_pen: Decimal
    other_cost_pen: Decimal = Decimal("0")
