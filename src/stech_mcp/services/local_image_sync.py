from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from PIL import Image


_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
_ALLOWED_FORMATS = {"JPEG", "PNG", "GIF"}
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class LocalImageSyncService:
    """Discover and persist exact-Part-Number images from PC020 local storage."""

    def __init__(self, *, root: str | Path, repository: Any, max_bytes: int = _DEFAULT_MAX_BYTES):
        self.root = Path(root).expanduser().resolve()
        self.repository = repository
        self.max_bytes = int(max_bytes)
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")

    def _pattern(self, partnumber: str) -> re.Pattern[str]:
        return re.compile(
            rf"^{re.escape(partnumber)}_(?P<position>\d{{2,3}})(?P<ext>\.jpg|\.jpeg|\.png|\.gif)$",
            flags=re.IGNORECASE,
        )

    def _discover(self, partnumber: str) -> list[tuple[int, Path]]:
        if not self.root.exists():
            return []
        pattern = self._pattern(partnumber)
        found: list[tuple[int, Path]] = []
        for path in self.root.rglob(f"{partnumber}_*.*"):
            if not path.is_file():
                continue
            match = pattern.match(path.name)
            if not match:
                continue
            position = int(match.group("position"))
            if position <= 0:
                continue
            resolved = path.resolve()
            if not _is_relative_to(resolved, self.root):
                continue
            found.append((position, resolved))
        return sorted(found, key=lambda item: (item[0], str(item[1]).lower()))

    def _inspect(self, path: Path) -> dict[str, Any]:
        extension = path.suffix.lower()
        if extension not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported_extension:{extension}")
        size_bytes = path.stat().st_size
        if size_bytes <= 0:
            raise ValueError("empty_file")
        if size_bytes > self.max_bytes:
            raise ValueError(f"file_too_large:{size_bytes}")

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width_px, height_px = image.size
            image.verify()
        if image_format not in _ALLOWED_FORMATS:
            raise ValueError(f"unsupported_format:{image_format or 'unknown'}")
        if int(width_px) <= 0 or int(height_px) <= 0:
            raise ValueError("invalid_dimensions")

        return {
            "sha256_hash": digest.hexdigest(),
            "width_px": int(width_px),
            "height_px": int(height_px),
            "format": image_format,
            "size_bytes": int(size_bytes),
        }

    @staticmethod
    def _decorate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {**row, "is_main": int(row.get("position") or 0) == 1}
            for row in sorted(rows, key=lambda item: (int(item.get("position") or 0), int(item.get("product_image_id") or 0)))
        ]

    def sync(self, partnumber: str) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")

        discovered = self._discover(normalized)
        if not discovered:
            return {
                "found": True,
                "partnumber": normalized,
                "state": "NO_IMAGES",
                "reason": "no_local_images",
                "image_count": 0,
                "images": [],
                "errors": [],
            }

        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen_positions: set[int] = set()
        seen_hashes: dict[str, Path] = {}

        for position, path in discovered:
            if position in seen_positions:
                errors.append({"file": str(path), "reason": f"duplicate_position:{position}"})
                continue
            try:
                metadata = self._inspect(path)
            except Exception as exc:
                errors.append({"file": str(path), "reason": str(exc)})
                continue

            duplicate_path = seen_hashes.get(metadata["sha256_hash"])
            if duplicate_path is not None:
                errors.append(
                    {
                        "file": str(path),
                        "reason": "duplicate_binary",
                        "duplicate_of": str(duplicate_path),
                    }
                )
                continue

            seen_positions.add(position)
            seen_hashes[metadata["sha256_hash"]] = path
            stored = self.repository.upsert_local_image(
                partnumber=normalized,
                source_type="LOCAL_PC020",
                storage_path=str(path),
                sha256_hash=metadata["sha256_hash"],
                width_px=metadata["width_px"],
                height_px=metadata["height_px"],
                format=metadata["format"],
                position=position,
                is_approved=True,
                partnumber_match="EXACT",
                variant_type="ORIGINAL",
            )
            rows.append({**stored, "size_bytes": metadata["size_bytes"]})

        decorated = self._decorate(rows)
        has_main = any(row["is_main"] for row in decorated)
        if errors:
            state = "REVIEW"
            reason = "invalid_or_conflicting_images"
        elif not has_main:
            state = "REVIEW"
            reason = "main_image_01_missing"
        else:
            state = "READY"
            reason = None

        return {
            "found": True,
            "partnumber": normalized,
            "state": state,
            "reason": reason,
            "image_count": len(decorated),
            "images": decorated,
            "errors": errors,
        }

    def validate(self, partnumber: str) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        rows = self._decorate(list(self.repository.list_images(normalized) or []))
        local_rows = [row for row in rows if str(row.get("source_type") or "").upper() == "LOCAL_PC020"]
        if not local_rows:
            return {
                "found": True,
                "partnumber": normalized,
                "state": "NO_IMAGES",
                "reason": "no_local_images",
                "image_count": 0,
                "images": [],
            }
        if not any(row["is_main"] for row in local_rows):
            state = "REVIEW"
            reason = "main_image_01_missing"
        elif any(not bool(row.get("is_approved")) for row in local_rows):
            state = "REVIEW"
            reason = "unapproved_local_image"
        else:
            state = "READY"
            reason = None
        return {
            "found": True,
            "partnumber": normalized,
            "state": state,
            "reason": reason,
            "image_count": len(local_rows),
            "images": local_rows,
        }
