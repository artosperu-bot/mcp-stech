from __future__ import annotations

from typing import Any


def _present(value: Any) -> bool:
    return value not in (None, "", [], (), {})


def _fmt_number(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _subject(kind: str, facts: dict[str, Any]) -> str:
    pieces = [kind]
    for key in ("brand", "model"):
        value = facts.get(key)
        if _present(value):
            pieces.append(str(value).strip())
    return " ".join(pieces)


def laptop_blocks(facts: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    subject = _subject("Laptop", facts)

    performance: list[str] = []
    if _present(facts.get("cpu_model")):
        performance.append(f"procesador {facts['cpu_model']}")
    if _present(facts.get("ram_gb")):
        performance.append(f"{_fmt_number(facts['ram_gb'])} GB de memoria RAM")
    if _present(facts.get("storage_gb")):
        storage = f"{_fmt_number(facts['storage_gb'])} GB de almacenamiento"
        if _present(facts.get("storage_type")):
            storage += f" {facts['storage_type']}"
        performance.append(storage)
    if performance:
        blocks.append(f"{subject} integra " + ", ".join(performance) + ".")
    else:
        blocks.append(f"{subject}.")

    display: list[str] = []
    if _present(facts.get("screen_inches")):
        display.append(f"pantalla de {_fmt_number(facts['screen_inches'])} pulgadas")
    if _present(facts.get("resolution")):
        display.append(f"resolución {facts['resolution']}")
    if _present(facts.get("refresh_rate_hz")):
        display.append(f"tasa de refresco de {_fmt_number(facts['refresh_rate_hz'])} Hz")
    if _present(facts.get("gpu_model")):
        display.append(f"gráficos {facts['gpu_model']}")
    if display:
        blocks.append("En el apartado visual cuenta con " + ", ".join(display) + ".")

    connectivity: list[str] = []
    if _present(facts.get("wifi")):
        connectivity.append(str(facts["wifi"]))
    if _present(facts.get("bluetooth_version")):
        connectivity.append(f"Bluetooth {facts['bluetooth_version']}")
    if _present(facts.get("ports")):
        connectivity.append(str(facts["ports"]))
    if connectivity:
        blocks.append("Conectividad: " + ", ".join(connectivity) + ".")

    mobility: list[str] = []
    if _present(facts.get("battery_wh")):
        mobility.append(f"batería de {_fmt_number(facts['battery_wh'])} Wh")
    if _present(facts.get("weight_kg")):
        mobility.append(f"peso de {_fmt_number(facts['weight_kg'])} kg")
    if _present(facts.get("dimensions_mm")):
        mobility.append(f"dimensiones {facts['dimensions_mm']}")
    if mobility:
        blocks.append("Características físicas: " + ", ".join(mobility) + ".")

    if _present(facts.get("os_name")):
        blocks.append(f"Sistema operativo: {facts['os_name']}.")
    if _present(facts.get("box_contents")):
        blocks.append(f"Contenido de caja: {facts['box_contents']}.")
    if _present(facts.get("warranty")):
        blocks.append(f"Garantía: {facts['warranty']}.")
    return blocks


def smartphone_blocks(facts: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    subject = _subject("Smartphone", facts)

    performance: list[str] = []
    chipset = facts.get("chipset") or facts.get("cpu_model")
    if _present(chipset):
        performance.append(f"chipset {chipset}")
    if _present(facts.get("ram_gb")):
        performance.append(f"{_fmt_number(facts['ram_gb'])} GB de RAM")
    if _present(facts.get("storage_gb")):
        performance.append(f"{_fmt_number(facts['storage_gb'])} GB de almacenamiento")
    if performance:
        blocks.append(f"{subject} integra " + ", ".join(performance) + ".")
    else:
        blocks.append(f"{subject}.")

    display: list[str] = []
    if _present(facts.get("screen_inches")):
        display.append(f"pantalla de {_fmt_number(facts['screen_inches'])} pulgadas")
    if _present(facts.get("resolution")):
        display.append(f"resolución {facts['resolution']}")
    if _present(facts.get("refresh_rate_hz")):
        display.append(f"{_fmt_number(facts['refresh_rate_hz'])} Hz")
    if display:
        blocks.append("Pantalla: " + ", ".join(display) + ".")

    camera_bits: list[str] = []
    for key, label in (("main_camera_mp", "cámara principal"), ("front_camera_mp", "cámara frontal")):
        if _present(facts.get(key)):
            camera_bits.append(f"{label} de {_fmt_number(facts[key])} MP")
    if camera_bits:
        blocks.append("Cámaras: " + ", ".join(camera_bits) + ".")

    durability: list[str] = []
    if _present(facts.get("battery_mah")):
        durability.append(f"batería de {_fmt_number(facts['battery_mah'])} mAh")
    if _present(facts.get("network")):
        durability.append(f"conectividad {facts['network']}")
    if _present(facts.get("ip_rating")):
        durability.append(f"protección {facts['ip_rating']}")
    if durability:
        blocks.append("Autonomía y conectividad: " + ", ".join(durability) + ".")

    if _present(facts.get("os_name")):
        blocks.append(f"Sistema operativo: {facts['os_name']}.")
    if _present(facts.get("box_contents")):
        blocks.append(f"Contenido de caja: {facts['box_contents']}.")
    if _present(facts.get("warranty")):
        blocks.append(f"Garantía: {facts['warranty']}.")
    return blocks
