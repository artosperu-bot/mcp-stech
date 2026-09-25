from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


_QUALITY_STEPS = (90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35)


def _normalize_partnumber(value: str) -> str:
    return str(value or "").strip().upper()


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class FalabellaImageBridgeService:
    """Prepare local STECH images for Falabella without touching originals.

    Output contract:
    - 1500x1500 by default.
    - JPEG on a white square canvas.
    - Original aspect ratio preserved and centered.
    - Maximum 8 images; position 1 remains the main image.
    - Output is compressed under Falabella's configured byte limit.
    - Signed URLs point to the prepared channel variant, never to arbitrary paths.

    This service does not perform AI background removal. A non-white source
    background is flagged for review even though the final square canvas is white.
    """

    def __init__(
        self,
        *,
        source_root: str | Path,
        channel_root: str | Path,
        local_service: Any,
        repository: Any,
        signer: Any,
        canvas_px: int = 1500,
        max_bytes: int = 150 * 1024,
        min_source_px: int = 500,
        margin_px: int = 30,
    ) -> None:
        self.source_root = Path(source_root).expanduser().resolve()
        self.channel_root = Path(channel_root).expanduser().resolve()
        self.local_service = local_service
        self.repository = repository
        self.signer = signer
        self.canvas_px = int(canvas_px)
        self.max_bytes = int(max_bytes)
        self.min_source_px = int(min_source_px)
        self.margin_px = int(margin_px)
        if not (500 <= self.canvas_px <= 2000):
            raise ValueError("canvas_px must be between 500 and 2000")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        if self.min_source_px <= 0:
            raise ValueError("min_source_px must be greater than zero")
        if self.margin_px < 0 or self.margin_px * 2 >= self.canvas_px:
            raise ValueError("margin_px is invalid for canvas size")

    @staticmethod
    def _source_background_status(image: Image.Image) -> str:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        points = (
            (0, 0),
            (max(width - 1, 0), 0),
            (0, max(height - 1, 0)),
            (max(width - 1, 0), max(height - 1, 0)),
        )
        for point in points:
            red, green, blue, alpha = rgba.getpixel(point)
            if alpha <= 16:
                continue
            if min(red, green, blue) < 242:
                return "REVIEW_NONWHITE_SOURCE"
            if max(red, green, blue) - min(red, green, blue) > 8:
                return "REVIEW_NONWHITE_SOURCE"
        return "WHITE_OR_TRANSPARENT"

    def _encode_jpeg(self, image: Image.Image) -> tuple[bytes, int]:
        for quality in _QUALITY_STEPS:
            buffer = BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
                dpi=(72, 72),
            )
            payload = buffer.getvalue()
            if len(payload) <= self.max_bytes:
                return payload, quality
        raise ValueError(f"cannot_compress_under_limit:{self.max_bytes}")

    def _prepare_one(self, *, partnumber: str, row: dict[str, Any]) -> dict[str, Any]:
        position = int(row.get("position") or 0)
        image_id = int(row.get("product_image_id") or 0)
        source_path = Path(str(row.get("storage_path") or "")).expanduser().resolve()
        if position <= 0 or image_id <= 0:
            raise ValueError("invalid_source_image_metadata")
        if not _inside_root(source_path, self.source_root):
            raise ValueError("source_path_outside_stech_image_root")
        if not source_path.is_file():
            raise FileNotFoundError(str(source_path))

        with Image.open(source_path) as opened:
            transposed = ImageOps.exif_transpose(opened)
            source_width, source_height = transposed.size
            background_status = self._source_background_status(transposed)

            warnings: list[str] = []
            if min(source_width, source_height) < self.min_source_px:
                warnings.append(
                    f"source_below_{self.min_source_px}px:{source_width}x{source_height}"
                )
            if background_status != "WHITE_OR_TRANSPARENT":
                warnings.append("source_background_requires_review")

            rgba = transposed.convert("RGBA")
            max_content = self.canvas_px - (2 * self.margin_px)
            scale = min(max_content / rgba.width, max_content / rgba.height)
            target_width = max(1, int(round(rgba.width * scale)))
            target_height = max(1, int(round(rgba.height * scale)))
            resized = rgba.resize(
                (target_width, target_height),
                Image.Resampling.LANCZOS,
            )

            canvas = Image.new(
                "RGB",
                (self.canvas_px, self.canvas_px),
                (255, 255, 255),
            )
            left = (self.canvas_px - target_width) // 2
            top = (self.canvas_px - target_height) // 2
            if "A" in resized.getbands():
                canvas.paste(resized, (left, top), resized.getchannel("A"))
            else:
                canvas.paste(resized.convert("RGB"), (left, top))

        payload, quality = self._encode_jpeg(canvas)
        digest = hashlib.sha256(payload).hexdigest()
        output_dir = self.channel_root / "FALABELLA" / partnumber
        output_dir.mkdir(parents=True, exist_ok=True)
        # Content-addressed filenames keep signed URLs immutable if a source
        # image is replaced later with a different binary.
        output_path = output_dir / f"{partnumber}_{position:02d}_{digest[:12]}.jpg"
        temporary = output_path.with_suffix(".jpg.tmp")
        temporary.write_bytes(payload)
        temporary.replace(output_path)

        variant = self.repository.insert_variant(
            parent_image_id=image_id,
            storage_path=str(output_path),
            sha256_hash=digest,
            width_px=self.canvas_px,
            height_px=self.canvas_px,
            format="JPEG",
            variant_type=f"FALABELLA_{self.canvas_px}",
        )
        if not bool(variant.get("is_approved")):
            variant = self.repository.set_approval(
                int(variant["product_image_id"]),
                True,
            )

        public_url = self.signer.sign(
            product_image_id=int(variant["product_image_id"]),
            partnumber=partnumber,
        )
        return {
            "position": position,
            "is_main": position == 1,
            "source_product_image_id": image_id,
            "product_image_id": int(variant["product_image_id"]),
            "source_path": str(source_path),
            "storage_path": str(output_path),
            "width_px": self.canvas_px,
            "height_px": self.canvas_px,
            "format": "JPEG",
            "file_size_bytes": len(payload),
            "jpeg_quality": quality,
            "source_width_px": int(source_width),
            "source_height_px": int(source_height),
            "background_status": background_status,
            "warnings": warnings,
            "url": public_url,
        }

    def prepare(self, partnumber: str, *, max_images: int = 8) -> dict[str, Any]:
        normalized = _normalize_partnumber(partnumber)
        if not normalized:
            raise ValueError("partnumber is required")
        bounded = max(1, min(int(max_images), 8))

        local = self.local_service.sync(normalized)
        source_images = sorted(
            list(local.get("images") or []),
            key=lambda item: (
                int(item.get("position") or 0),
                int(item.get("product_image_id") or 0),
            ),
        )
        if not source_images:
            return {
                "found": True,
                "partnumber": normalized,
                "state": "NO_IMAGES",
                "image_count": 0,
                "images": [],
                "errors": list(local.get("errors") or []),
                "rules": self.rules(),
            }

        selected = source_images[:bounded]
        if not any(int(row.get("position") or 0) == 1 for row in selected):
            return {
                "found": True,
                "partnumber": normalized,
                "state": "REVIEW",
                "reason": "main_image_01_missing",
                "image_count": 0,
                "images": [],
                "errors": list(local.get("errors") or []),
                "rules": self.rules(),
            }

        prepared: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = list(local.get("errors") or [])
        for row in selected:
            try:
                prepared.append(self._prepare_one(partnumber=normalized, row=row))
            except Exception as exc:
                errors.append(
                    {
                        "position": row.get("position"),
                        "product_image_id": row.get("product_image_id"),
                        "reason": f"{type(exc).__name__}:{exc}",
                    }
                )

        prepared.sort(key=lambda item: int(item["position"]))
        warning_count = sum(len(item.get("warnings") or []) for item in prepared)
        if not prepared:
            state = "ERROR"
        elif errors:
            state = "PARTIAL"
        elif warning_count:
            state = "READY_WITH_WARNINGS"
        else:
            state = "READY"

        return {
            "found": True,
            "partnumber": normalized,
            "state": state,
            "image_count": len(prepared),
            "main_image_url": next(
                (item["url"] for item in prepared if item.get("is_main")),
                None,
            ),
            "images": prepared,
            "errors": errors,
            "warning_count": warning_count,
            "rules": self.rules(),
        }

    def prepare_batch(
        self,
        partnumbers: list[str],
        *,
        max_images: int = 8,
    ) -> dict[str, Any]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in list(partnumbers or []):
            pn = _normalize_partnumber(value)
            if not pn or pn in seen:
                continue
            seen.add(pn)
            normalized.append(pn)
        if not normalized:
            raise ValueError("partnumbers are required")
        if len(normalized) > 500:
            raise ValueError("maximum 500 partnumbers per batch")

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for pn in normalized:
            try:
                results.append(self.prepare(pn, max_images=max_images))
            except Exception as exc:
                errors.append(
                    {"partnumber": pn, "error": f"{type(exc).__name__}: {exc}"}
                )
        return {
            "requested_count": len(normalized),
            "prepared_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors,
            "rules": self.rules(),
        }

    def rules(self) -> dict[str, Any]:
        return {
            "canvas_px": self.canvas_px,
            "format": "JPEG",
            "max_bytes": self.max_bytes,
            "max_images": 8,
            "main_position": 1,
            "margin_px": self.margin_px,
            "preserve_aspect_ratio": True,
            "white_canvas": True,
            "automatic_background_removal": False,
            "min_source_px_review_threshold": self.min_source_px,
        }
