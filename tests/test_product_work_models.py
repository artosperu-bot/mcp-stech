from stech_mcp.domain.product_work_models import (
    ITEM_STATES,
    JOB_STATES,
    TERMINAL_ITEM_STATES,
    WORK_TYPES,
    can_transition,
    make_context_hash,
    normalize_partnumber,
)


def test_work_type_and_state_contract_is_separate_from_vtex_loader():
    assert "ENRICH_TECHNICAL" in WORK_TYPES
    assert "RESEARCH_IMAGES" in WORK_TYPES
    assert "RUNNING" in JOB_STATES
    assert "QUEUED" in ITEM_STATES
    assert "FAILED_RETRYABLE" in ITEM_STATES
    assert "COMPLETED" in TERMINAL_ITEM_STATES
    assert "FAILED_RETRYABLE" not in TERMINAL_ITEM_STATES
    assert "VTEX_CREATE_SKU" not in ITEM_STATES


def test_partnumber_and_context_hash_are_stable_and_case_normalized():
    assert normalize_partnumber(" 82yu00xylm ") == "82YU00XYLM"
    first = make_context_hash("enrich_technical", "82yu00xylm", "laptop", None)
    second = make_context_hash("ENRICH_TECHNICAL", "82YU00XYLM", "LAPTOP", "")
    assert first == second
    assert len(first) == 64


def test_context_hash_changes_when_relevant_context_changes():
    base = make_context_hash("ENRICH_TECHNICAL", "PN1", "LAPTOP", None)
    channel = make_context_hash("ENRICH_TECHNICAL", "PN1", "LAPTOP", "FALABELLA")
    other_product = make_context_hash("ENRICH_TECHNICAL", "PN2", "LAPTOP", None)
    assert base != channel
    assert base != other_product


def test_transition_contract_rejects_backward_or_terminal_mutation():
    assert can_transition("QUEUED", "LOADING_SOURCE_DATA") is True
    assert can_transition("FAILED_RETRYABLE", "QUEUED") is True
    assert can_transition("RESEARCHING", "VALIDATING") is True
    assert can_transition("COMPLETED", "QUEUED") is False
    assert can_transition("VALIDATING", "QUEUED") is False
