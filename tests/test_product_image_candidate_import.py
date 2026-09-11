from __future__ import annotations

from dataclasses import dataclass
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
        return dict(self.row) if int(candidate_id) == int(self.row["product_image_candidate_id"]) else None

    def set_state(self, candidate_id, state):
        self.states.append((int(candidate_id), state))
        self.row["state"] = state
        return dict(self.row)


class ImageRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.saved = []

    def list_images(self, partnumber):
        return [dict(row) for row in self.rows]

    def upsert_local_image(self, **kwargs):
        self.saved.append(dict(kwargs))
        return {"product_image_id": 99, **kwargs}


class SourceClient:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return Response(self.payload, "image/png", url, len(self.payload))


def _png_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "source.png"
    Image.new("RGB", (1200, 1200), "white").save(path, format="PNG")
    return path.read_bytes()


def test_import_exact_candidate_creates_original_without_replacing_existing(tmp_path):
    candidate = {
        "product_image_candidate_id": 7,
        "partnumber": "ABC-123",
        "source_url": "https://example.com/a.png",
        "source_domain": "example.com",
        "state": "PENDING",
        "partnumber_match": "EXACT",
        "variant_match": "EXACT",
        "exactness_policy": "EXACT_PN_REQUIRED",
    }
    candidates = CandidateRepo(candidate)
    images = ImageRepo([{"position": 1, "storage_path": str(tmp_path / "existing.jpg")}])
    client = SourceClient(_png_bytes(tmp_path))
    service = ProductImageCandidateImportService(
        root=tmp_path / "images",
        candidate_repository=candidates,
        image_repository=images,
        source_client=client,
    )

    result = service.import_candidate(7, brand="LENOVO", category_code="LAPTOP")

    assert result["state"] == "IMPORTED"
    assert result["position"] == 2
    assert result["storage_path"].endswith("ABC-123_02.png")
    assert Path(result["storage_path"]).exists()
    assert images.saved[0]["variant_type"] == "ORIGINAL"
    assert images.saved[0]["is_approved"] is True
    assert images.saved[0]["partnumber_match"] == "EXACT"
    assert candidates.states[-1] == (7, "IMPORTED")


def test_import_rejects_non_exact_candidate_without_downloading(tmp_path):
    candidate = {
        "product_image_candidate_id": 8,
        "partnumber": "ABC-123",
        "source_url": "https://example.com/a.png",
        "state": "PENDING",
        "partnumber_match": "UNKNOWN",
        "variant_match": "UNKNOWN",
        "exactness_policy": "MANUAL_REVIEW",
    }
    candidates = CandidateRepo(candidate)
    images = ImageRepo()
    client = SourceClient(_png_bytes(tmp_path))
    service = ProductImageCandidateImportService(
        root=tmp_path / "images",
        candidate_repository=candidates,
        image_repository=images,
        source_client=client,
    )

    try:
        service.import_candidate(8)
    except ValueError as exc:
        assert "exact" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")

    assert client.urls == []
    assert images.saved == []


def test_import_never_overwrites_existing_file(tmp_path):
    candidate = {
        "product_image_candidate_id": 9,
        "partnumber": "ABC-123",
        "source_url": "https://example.com/a.png",
        "state": "PENDING",
        "partnumber_match": "EXACT",
        "variant_match": "EXACT",
        "exactness_policy": "EXACT_PN_REQUIRED",
    }
    candidates = CandidateRepo(candidate)
    images = ImageRepo()
    client = SourceClient(_png_bytes(tmp_path))
    root = tmp_path / "images"
    existing = root / "UNKNOWN" / "DEFAULT" / "ABC-123" / "ABC-123_01.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"do-not-replace")
    service = ProductImageCandidateImportService(
        root=root,
        candidate_repository=candidates,
        image_repository=images,
        source_client=client,
    )

    try:
        service.import_candidate(9)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")

    assert existing.read_bytes() == b"do-not-replace"
    assert images.saved == []
