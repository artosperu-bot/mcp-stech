from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.testclient import TestClient

from stech_mcp.http.image_route import build_vtex_image_route
from stech_mcp.services.image_signing import ImageUrlSigner


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


class FakeImageRepository:
    def __init__(self, rows: dict[int, dict]):
        self.rows = rows

    def get_by_id(self, product_image_id: int):
        row = self.rows.get(int(product_image_id))
        return None if row is None else dict(row)


def _token(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1]


def test_image_route_serves_only_the_signed_exact_file(tmp_path):
    file_path = tmp_path / "82YU00XYLM_01.png"
    file_path.write_bytes(PNG_1X1)
    signer = ImageUrlSigner(
        secret="route-secret",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=900,
        now=lambda: 1_000,
    )
    repo = FakeImageRepository(
        {
            1: {
                "product_image_id": 1,
                "partnumber": "82YU00XYLM",
                "storage_path": str(file_path),
                "format": "PNG",
                "is_approved": True,
            }
        }
    )
    app = Starlette(routes=[build_vtex_image_route(signer=signer, image_repository=repo, root=tmp_path)])
    client = TestClient(app)
    token = _token(signer.sign(product_image_id=1, partnumber="82YU00XYLM"))

    response = client.get(f"/vtex-images/{token}")

    assert response.status_code == 200
    assert response.content == PNG_1X1
    assert response.headers["content-type"].startswith("image/png")


def test_image_route_rejects_expired_token(tmp_path):
    clock = {"now": 1_000}
    signer = ImageUrlSigner(
        secret="route-secret",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=1,
        now=lambda: clock["now"],
    )
    repo = FakeImageRepository({})
    app = Starlette(routes=[build_vtex_image_route(signer=signer, image_repository=repo, root=tmp_path)])
    client = TestClient(app)
    token = _token(signer.sign(product_image_id=1, partnumber="82YU00XYLM"))
    clock["now"] = 1_002

    response = client.get(f"/vtex-images/{token}")

    assert response.status_code == 403


def test_image_route_returns_404_for_unknown_image(tmp_path):
    signer = ImageUrlSigner(
        secret="route-secret",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=900,
        now=lambda: 1_000,
    )
    repo = FakeImageRepository({})
    app = Starlette(routes=[build_vtex_image_route(signer=signer, image_repository=repo, root=tmp_path)])
    client = TestClient(app)
    token = _token(signer.sign(product_image_id=999, partnumber="82YU00XYLM"))

    response = client.get(f"/vtex-images/{token}")

    assert response.status_code == 404


def test_image_route_blocks_storage_path_outside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)
    signer = ImageUrlSigner(
        secret="route-secret",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=900,
        now=lambda: 1_000,
    )
    repo = FakeImageRepository(
        {
            1: {
                "product_image_id": 1,
                "partnumber": "82YU00XYLM",
                "storage_path": str(outside),
                "format": "PNG",
                "is_approved": True,
            }
        }
    )
    app = Starlette(routes=[build_vtex_image_route(signer=signer, image_repository=repo, root=root)])
    client = TestClient(app)
    token = _token(signer.sign(product_image_id=1, partnumber="82YU00XYLM"))

    response = client.get(f"/vtex-images/{token}")

    assert response.status_code == 403
