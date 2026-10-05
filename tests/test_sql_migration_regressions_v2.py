from pathlib import Path

ROOT = Path(__file__).parents[1]
SQL010 = ROOT / "sql" / "010_product_image_research_v2.sql"
SQL011 = ROOT / "sql" / "011_channel_requirements_v2.sql"


def _batches(text: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().upper() == "GO":
            if current:
                batches.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        batches.append("\n".join(current))
    return batches


def test_011_does_not_reference_requirement_level_in_same_batch_that_adds_it():
    batches = _batches(SQL011.read_text(encoding="utf-8"))
    add_batches = [b.upper() for b in batches if "ADD REQUIREMENT_LEVEL" in b.upper()]
    assert add_batches, "migration must add requirement_level"
    assert all("UPDATE DBO.MARKETPLACE_TEMPLATE_FIELD" not in b for b in add_batches)
    assert any(
        "UPDATE DBO.MARKETPLACE_TEMPLATE_FIELD" in b.upper()
        and "REQUIREMENT_LEVEL" in b.upper()
        for b in batches
    ), "backfill must run in a later batch after ALTER TABLE is compiled"


def test_010_uses_fixed_width_hash_for_unique_url_index():
    upper = SQL010.read_text(encoding="utf-8").upper()
    assert "SOURCE_URL_HASH" in upper
    assert "HASHBYTES" in upper
    assert "CREATE UNIQUE INDEX UX_PRODUCT_IMAGE_CANDIDATE_URL" in upper
    assert "(PARTNUMBER, SOURCE_URL_HASH)" in upper
    assert "(PARTNUMBER, SOURCE_URL);" not in upper
