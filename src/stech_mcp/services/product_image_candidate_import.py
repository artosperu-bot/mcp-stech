from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")
_FORMAT_EXT = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}


def _segment(value: Any, fallback: str) -> str:
    text = str(value or "").strip().upper()
    cleaned = _SAFE_SEGMENT.sub("_", text).strip("._")
    return cleaned or fallback


class ProductImageCandidateImportService:
    """Import a manually approved exact image candidate as an immutable ORIGINAL.

    This service never publishes to a sales channel and never overwrites an
    existing file. Ambiguous Part Number candidates remain review-only.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        candidate_repository: Any,
        image_repository: Any,
        source_client: Any,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.candidate_repository = candidate_repository
        self.image_repository = image_repository
        self.source_client = source_client

    @staticmethod
    def _next_position(rows: list[dict[str, Any]]) -> int:
        positions = [int(row.get("position") or 0) for row in rows]
        return max([0, *positions]) + 1

    @staticmethod
    def _inspect(content: bytes) -> tuple[str, int, int, str]:
        digest = hashlib.sha256(content).hexdigest()
        with Image.open(BytesIO(content)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        if image_format not in _FORMAT_EXT:
            raise ValueError(f"unsupported image format: {image_format or 'UNKNOWN'}")
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("invalid image dimensions")
        return digest, int(width), int(height), image_format

    def import_candidate(
        self,
        candidate_id: int,
        *,
        brand: str | None = None,
        category_code: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.candidate_repository.get_candidate(int(candidate_id))
        if candidate is None:
            raise ValueError("image candidate not found")

        state = str(candidate.get("state") or "").strip().upper()
        if state == "IMPORTED":
            raise ValueError("image candidate is already imported")
        if state == "REJECTED":
            raise ValueError("rejected image candidate cannot be imported")

        partnumber = str(candidate.get("partnumber") or "").strip().upper()
        if not partnumber:
            raise ValueError("candidate partnumber is required")
        if str(candidate.get("partnumber_match") or "").strip().upper() != "EXACT":
            raise ValueError("only an exact Part Number image candidate can be imported")
        if str(candidate.get("variant_match") or "UNKNOWN").strip().upper() == "MISMATCH":
            raise ValueError("candidate variant does not match the product")

        source_url = str(candidate.get("source_url") or "").strip()
        if not source_url:
            raise ValueError("candidate source_url is required")

        response = self.source_client.fetch(source_url)
        digest, width, height, image_format = self._inspect(response.content)
        extension = _FORMAT_EXT[image_format]
        current = list(self.image_repository.list_images(partnumber))
        position = self._next_position(current)

        target_dir = (
            self.root
            / _segment(brand, "UNKNOWN")
            / _segment(category_code, "DEFAULT")
            / _segment(partnumber, "UNKNOWN")
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{partnumber}_{position:02d}{extension}"

        # Exclusive creation is the safety barrier: originals are never replaced.
        with target_path.open("xb") as handle:
            handle.write(response.content)

        try:
            stored = self.image_repository.upsert_local_image(
                partnumber=partnumber,
                source_type="WEB_RESEARCH",
                storage_path=str(target_path),
                sha256_hash=digest,
                width_px=width,
                height_px=height,
                format=image_format,
                position=position,
                is_approved=True,
                partnumber_match="EXACT",
                variant_type="ORIGINAL",
                source_url=response.final_url,
                source_domain=candidate.get("source_domain"),
                background_status="IMPORTED_FROM_CANDIDATE",
            )
        except Exception:
            # Persistence failed after file creation. Remove only the new file we
            # just created; never touch any pre-existing original.
            try:
                target_path.unlink(missing_ok=True)
            finally:
                raise

        self.candidate_repository.set_state(int(candidate_id), "IMPORTED")
        return {
            "found": True,
            "candidate_id": int(candidate_id),
            "partnumber": partnumber,
            "state": "IMPORTED",
            "position": position,
            "storage_path": str(target_path),
            "image": stored,
        }
