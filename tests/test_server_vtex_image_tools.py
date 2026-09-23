from pathlib import Path


def test_server_exposes_vtex_image_tools_and_http_route():
    source = (Path(__file__).resolve().parents[1] / "src" / "stech_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    assert "def product_images_sync_local(" in source
    assert "def product_images_validate(" in source
    assert "def vtex_images_status(" in source
    assert "def vtex_images_sync(" in source
    assert "build_vtex_image_route" in source
