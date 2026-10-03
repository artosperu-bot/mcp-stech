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


def _classify_folder(rel_parts: tuple[str, ...], folder_name: str, partnumber: str) -> tuple[str, int]:
    upper_parts = [p.upper() for p in rel_parts]
    has_underscore_prefix = any(p.startswith("_") for p in upper_parts)
    is_psref = any("PSREF" in p for p in upper_parts)
    has_resolution = any(bool(re.search(r"\b\d{3,4}X\d{3,4}\b", p)) for p in upper_parts)
    is_uncategorized = any("SIN_CATEGORIA" in p for p in upper_parts)

    if not has_underscore_prefix and not is_psref and not has_resolution and not is_uncategorized:
        if len(rel_parts) == 3 and folder_name.upper() == partnumber:
            return ("CANONICAL", 100)
        return ("CATEGORIZED_CLEAN", 90)

    if is_uncategorized:
        return ("UNCATEGORIZED", 20)
    if is_psref and has_underscore_prefix:
        return ("CONVERTED_PSREF", 45)
    if is_psref:
        return ("REFERENCE_PSREF", 40)
    if has_resolution:
        return ("RESIZED_CONVERTED" if has_underscore_prefix else "RESIZED", 50)
    if has_underscore_prefix:
        return ("CONVERTED", 55)

    return ("OTHER", 30)


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
            rf"^{re.escape(partnumber)}_(?P<position>\d{{1,3}})(?P<ext>\.jpg|\.jpeg|\.png|\.gif)$",
            flags=re.IGNORECASE,
        )

    def folders_find(self, partnumber: str) -> list[dict[str, Any]]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized or not self.root.exists():
            return []

        pattern = self._pattern(normalized)
        candidate_map: dict[Path, list[int]] = {}

        for path in self.root.rglob(f"{normalized}_*.*"):
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
            parent = resolved.parent
            if parent not in candidate_map:
                candidate_map[parent] = []
            candidate_map[parent].append(position)

        candidates: list[dict[str, Any]] = []
        for folder, raw_positions in candidate_map.items():
            positions = sorted(list(set(raw_positions)))
            has_main = 1 in positions
            rel = folder.relative_to(self.root)
            kind, base_score = _classify_folder(rel.parts, folder.name, normalized)
            priority_score = base_score + (30 if has_main else 0) + min(len(positions), 10)
            candidates.append(
                {
                    "folder_path": str(folder),
                    "folder_name": folder.name,
                    "relative_path": str(rel).replace("\\", "/"),
                    "kind": kind,
                    "is_canonical": kind == "CANONICAL",
                    "image_count": len(positions),
                    "positions": positions,
                    "has_main": has_main,
                    "priority_score": priority_score,
                    "is_recommended": False,
                }
            )

        candidates.sort(
            key=lambda c: (
                -c["priority_score"],
                len(c["folder_path"]),
                c["folder_path"].lower(),
            )
        )
        if candidates:
            candidates[0]["is_recommended"] = True

        return candidates

    def _discover_folder(self, folder: Path, partnumber: str) -> list[tuple[int, Path]]:
        if not folder.is_dir():
            return []
        pattern = self._pattern(partnumber)
        found: list[tuple[int, Path]] = []
        for path in folder.iterdir():
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

    def _discover(self, partnumber: str) -> list[tuple[int, Path]]:
        candidates = self.folders_find(partnumber)
        if not candidates or len(candidates) > 1:
            return []
        recommended_folder = Path(candidates[0]["folder_path"])
        return self._discover_folder(recommended_folder, partnumber)

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
            for row in sorted(
                rows,
                key=lambda item: (
                    int(item.get("position") or 0),
                    int(item.get("product_image_id") or 0),
                ),
            )
        ]

    def sync(
        self,
        partnumber: str,
        *,
        folder_path: str | Path | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")

        candidate_folders = self.folders_find(normalized)

        if folder_path is not None and str(folder_path).strip():
            explicit_path = Path(folder_path).expanduser().resolve()
            if not explicit_path.is_dir() or not _is_relative_to(explicit_path, self.root):
                raise ValueError(f"invalid_or_outside_folder:{folder_path}")
            selected_folder = explicit_path
            rel = explicit_path.relative_to(self.root)
            selected_kind, _ = _classify_folder(rel.parts, explicit_path.name, normalized)
            discovered = self._discover_folder(selected_folder, normalized)
        else:
            if not candidate_folders:
                return {
                    "found": True,
                    "partnumber": normalized,
                    "state": "NO_IMAGES",
                    "reason": "no_local_images",
                    "selected_folder": None,
                    "selected_folder_kind": None,
                    "has_multiple_folders": False,
                    "candidate_folders": [],
                    "image_count": 0,
                    "images": [],
                    "errors": [],
                }
            if len(candidate_folders) > 1:
                return {
                    "found": True,
                    "partnumber": normalized,
                    "state": "CHOICE_REQUIRED",
                    "reason": "multiple_folders_found",
                    "message": (
                        f"Se encontraron {len(candidate_folders)} carpetas locales para el Part Number {normalized}. "
                        "Para evitar seleccionar una ruta incorrecta, se requiere especificar folder_path."
                    ),
                    "selected_folder": None,
                    "selected_folder_kind": None,
                    "has_multiple_folders": True,
                    "candidate_folders": candidate_folders,
                    "image_count": 0,
                    "images": [],
                    "errors": [],
                }
            selected_info = candidate_folders[0]
            selected_folder = Path(selected_info["folder_path"])
            selected_kind = selected_info["kind"]
            discovered = self._discover_folder(selected_folder, normalized)

        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen_positions: set[int] = set()

        for position, path in discovered:
            if position in seen_positions:
                errors.append({"file": str(path), "reason": f"duplicate_position:{position}"})
                continue
            seen_positions.add(position)
            try:
                metadata = self._inspect(path)
            except Exception as exc:
                errors.append({"file": str(path), "reason": str(exc)})
                continue

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
            "selected_folder": str(selected_folder),
            "selected_folder_kind": selected_kind,
            "has_multiple_folders": len(candidate_folders) > 1,
            "candidate_folders": candidate_folders,
            "image_count": len(decorated),
            "images": decorated,
            "errors": errors,
        }

    def validate(
        self,
        partnumber: str,
        *,
        folder_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return self.sync(partnumber, folder_path=folder_path)
