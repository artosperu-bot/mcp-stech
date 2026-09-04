from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


_Q = Decimal("0.01")


def estimate_package_weight(*, screen_inches: Decimal, device_weight_kg: Decimal, is_gaming: bool) -> Decimal:
    if device_weight_kg <= 0:
        raise ValueError("device_weight_kg must be positive")
    if screen_inches <= 0:
        raise ValueError("screen_inches must be positive")

    if is_gaming:
        extra = Decimal("1.35") if screen_inches <= Decimal("16.1") else Decimal("1.55")
    elif screen_inches <= Decimal("14.1"):
        extra = Decimal("0.65")
    elif screen_inches < Decimal("16"):
        extra = Decimal("0.70")
    else:
        extra = Decimal("0.80")

    return (device_weight_kg + extra).quantize(_Q, rounding=ROUND_HALF_UP)


def validate_package_dimensions(
    *,
    device_width_cm: Decimal,
    device_depth_cm: Decimal,
    device_height_cm: Decimal,
    package_width_cm: Decimal,
    package_length_cm: Decimal,
    package_height_cm: Decimal,
) -> tuple[bool, list[str]]:
    values = [
        device_width_cm,
        device_depth_cm,
        device_height_cm,
        package_width_cm,
        package_length_cm,
        package_height_cm,
    ]
    if any(value <= 0 for value in values):
        return False, ["non_positive_dimension"]

    reasons: list[str] = []
    if not (
        package_width_cm > device_width_cm
        and package_length_cm > device_depth_cm
        and package_height_cm > device_height_cm
    ):
        reasons.append("package_not_larger_than_device")

    return not reasons, reasons
