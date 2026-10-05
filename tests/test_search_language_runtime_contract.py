from pathlib import Path


def test_authoritative_and_worker_accept_canonical_search_language_name():
    root = Path(__file__).parents[1] / "src" / "stech_mcp"
    for relative in ("server_authoritative.py", "worker.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert 'STECH_SEARCH_LANGUAGE' in text
