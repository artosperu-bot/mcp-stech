from pathlib import Path


def test_authoritative_and_worker_accept_canonical_search_language_name():
    root = Path(__file__).parents[1] / "src" / "stech_mcp"
    config = (root / "config.py").read_text(encoding="utf-8")

    assert 'AliasChoices("STECH_SEARCH_LANGUAGE", "STECH_SEARCH_LANG")' in config

    for relative in ("server_authoritative.py", "worker.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert ".stech_search_language" in text
