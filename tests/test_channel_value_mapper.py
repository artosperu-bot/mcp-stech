from stech_mcp.excel.channel_schema import ChannelField
from stech_mcp.services.channel_value_mapper import ChannelValueMapper


def _field(*, allowed_values=()):
    return ChannelField(
        stable_key="attr:396393",
        header="TipoDePortatil * #396393",
        column_letter="C",
        attribute_id="396393",
        required=True,
        allowed_values=tuple(allowed_values),
    )


def test_mapper_preserves_exact_allowed_value():
    result = ChannelValueMapper().map(
        _field(allowed_values=("Laptop", "Laptop Gamer")),
        "Laptop",
    )

    assert result.state == "MAPPED"
    assert result.value == "Laptop"
    assert result.rule_code == "EXACT_ALLOWED_VALUE"


def test_mapper_accepts_case_only_normalization_but_returns_template_spelling():
    result = ChannelValueMapper().map(
        _field(allowed_values=("Laptop", "Laptop Gamer")),
        "laptop",
    )

    assert result.state == "MAPPED"
    assert result.value == "Laptop"
    assert result.rule_code == "CASEFOLD_ALLOWED_VALUE"


def test_mapper_uses_explicit_boolean_rule_for_closed_list():
    field = ChannelField(
        stable_key="header:pantalla tactil",
        header="Pantalla táctil",
        column_letter="D",
        required=False,
        allowed_values=("Sí", "No"),
    )

    result = ChannelValueMapper().map(field, True)

    assert result.state == "MAPPED"
    assert result.value == "Sí"
    assert result.rule_code == "BOOLEAN_SI_NO_V1"


def test_mapper_does_not_guess_unknown_closed_list_value():
    result = ChannelValueMapper().map(
        _field(allowed_values=("Laptop", "Laptop Gamer")),
        "Ultrabook",
    )

    assert result.state == "REVIEW_REQUIRED"
    assert result.value is None
    assert result.reason == "NO_EXACT_ALLOWED_MAPPING"


def test_mapper_passes_open_text_value_without_closed_list_coercion():
    field = ChannelField(
        stable_key="header:descripcion",
        header="Descripción",
        column_letter="E",
        required=False,
        allowed_values=(),
    )

    result = ChannelValueMapper().map(field, "Laptop Lenovo para productividad")

    assert result.state == "MAPPED"
    assert result.value == "Laptop Lenovo para productividad"
    assert result.rule_code == "OPEN_VALUE"
