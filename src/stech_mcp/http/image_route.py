from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.responses import FileResponse, PlainTextResponse
from starlette.routing import Route

from stech_mcp.services.image_signing import ImageUrlSigner, InvalidImageToken


_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def build_vtex_image_route(*, signer: ImageUrlSigner, image_repository: Any, root: str | Path) -> Route:
    configured_root = Path(root).expanduser().resolve()

    async def serve(request):
        token = request.path_params.get("token", "")
        try:
            signed = signer.verify(token)
        except InvalidImageToken:
            return PlainTextResponse("Forbidden", status_code=403)

        row = image_repository.get_by_id(int(signed["product_image_id"]))
        if row is None:
            return PlainTextResponse("Not found", status_code=404)
        if str(row.get("partnumber") or "").strip().upper() != signed["partnumber"]:
            return PlainTextResponse("Forbidden", status_code=403)
        if not bool(row.get("is_approved")):
            return PlainTextResponse("Forbidden", status_code=403)

        storage_path = str(row.get("storage_path") or "").strip()
        if not storage_path:
            return PlainTextResponse("Not found", status_code=404)
        candidate = Path(storage_path).expanduser().resolve()
        if not _inside_root(candidate, configured_root):
            return PlainTextResponse("Forbidden", status_code=403)
        if candidate.suffix.lower() not in _MEDIA_TYPES:
            return PlainTextResponse("Forbidden", status_code=403)
        if not candidate.is_file():
            return PlainTextResponse("Not found", status_code=404)

        return FileResponse(
            path=str(candidate),
            media_type=_MEDIA_TYPES[candidate.suffix.lower()],
            filename=None,
        )

    return Route("/vtex-images/{token}", endpoint=serve, methods=["GET"])
