from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any


class InvalidImageToken(ValueError):
    pass


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class ImageUrlSigner:
    """Create short-lived URLs that identify one approved local image."""

    def __init__(
        self,
        *,
        secret: str,
        public_base: str,
        ttl_seconds: int = 900,
        now: Callable[[], float] | None = None,
    ):
        secret_text = str(secret or "").strip()
        if not secret_text:
            raise ValueError("image signing secret is required")
        if int(ttl_seconds) <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        base = str(public_base or "").strip().rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("public_base must use https")
        self._secret = secret_text.encode("utf-8")
        self.public_base = base
        self.ttl_seconds = int(ttl_seconds)
        self._now = now or time.time

    def sign(self, *, product_image_id: int, partnumber: str) -> str:
        image_id = int(product_image_id)
        normalized = str(partnumber or "").strip().upper()
        if image_id <= 0 or not normalized:
            raise ValueError("product_image_id and partnumber are required")
        payload = {
            "i": image_id,
            "p": normalized,
            "e": int(self._now()) + self.ttl_seconds,
        }
        raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = _b64encode(raw)
        signature = _b64encode(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{self.public_base}/{encoded}.{signature}"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            encoded, signature = str(token or "").split(".", 1)
        except ValueError as exc:
            raise InvalidImageToken("invalid token signature format") from exc
        expected = _b64encode(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise InvalidImageToken("invalid token signature")
        try:
            payload = json.loads(_b64decode(encoded).decode("utf-8"))
            image_id = int(payload["i"])
            partnumber = str(payload["p"]).strip().upper()
            expires_at = int(payload["e"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidImageToken("invalid signed token payload") from exc
        if image_id <= 0 or not partnumber:
            raise InvalidImageToken("invalid signed token payload")
        if int(self._now()) > expires_at:
            raise InvalidImageToken("signed image token expired")
        return {
            "product_image_id": image_id,
            "partnumber": partnumber,
            "expires_at": expires_at,
        }
