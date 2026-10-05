from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from PIL import Image

from stech_mcp.services.product_image_candidate_import import ProductImageCandidateImportService


@dataclass
class Response:
    content: bytes
    content_type: str
    final_url: str
    content_length: int


class CandidateRepo:
    def __init__(self, row):
        self.row = dict(row)
        self.states = []

    def get_candidate(self, candidate_id):
        return dict(self.row)

    def set_state(self, candidate_id, state):
        self.states.append((int(candidate_id), state))
        self.row["state"] = state
        return dict(self.row)


class ImageRepo:
    def __init__(self, rows):
        self.rows = list(rows)
        self.saved = []

    def list_images(self, partnumber):
        return [dict(row) for row in self.rows]

    def upsert_local_image(self, **kwargs):
        self.saved.append(dict(kwargs))
        return {"product_image_id": 99, **kwargs}


class SourceClient:
    def __init__(self, payload):
        self.payload = payload

    def fetch(self, url):
        return Response(self.payload, "image/png", url, len(self.payload))


def _png_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "source.png"
    Image.new("RGB", (1200, 1200), "white").save(path, format="PNG")
    return path.read_bytes()


def test_import_deduplicates_existing_original_by_hash(tmp_path):
    payload = _png_bytes(tmp_path)
    digest = hashlib.sha256(payload).hexdigest()
    candidate = {
        "product_image_candidate_id": 10,
        "partnumber": "ABC-123",
        "source_url": "https://example.com/same.png",
        "source_domain": "example.com",
        "state": "PENDING",
        "partnumber_match": "EXACT",
        "variant_match": "EXACT",
        "exactness_policy": "EXACT_PN_REQUIRED",
    }
    existing = {
        "product_image_id": 41,
        "partnumber": "ABC-123",
        "position": 1,
        "variant_type": "ORIGINAL",
        "sha256_hash": digest,
        "storage_path": str(tmp_path / "already-there.png"),
    }
    candidates = CandidateRepo(candidate)
    images = ImageRepo([existing])
    root = tmp_path / "images"
    service = ProductImageCandidateImportService(
        root=root,
        candidate_repository=candidates,
        image_repository=images,
        source_client=SourceClient(payload),
    )

    result = service.import_candidate(10, brand="LENOVO", category_code="LAPTOP")

    assert result["state"] == "IMPORTED"
    assert result["deduplicated"] is True
    assert result["image"]["product_image_id"] == 41
    assert images.saved == []
    assert not root.exists()
    assert candidates.states[-1] == (10, "IMPORTED")
