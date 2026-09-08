from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx


MAX_SOURCE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceResponse:
    content: bytes
    content_type: str | None
    final_url: str
    content_length: int


def _validate_public_url(url: str, *, resolve_dns: bool = True) -> str:
    value = str(url or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("source URL must use http or https")
    if not parsed.hostname:
        raise ValueError("source URL requires a hostname")
    if parsed.username or parsed.password:
        raise ValueError("source URL credentials are not allowed")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("private source hosts are not allowed")

    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(hostname)))
    except ValueError:
        if resolve_dns:
            try:
                for info in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
                    addresses.add(info[4][0])
            except socket.gaierror as exc:
                raise ValueError(f"source hostname could not be resolved: {hostname}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("private or non-public source addresses are not allowed")
    return value


class SourceClient:
    def __init__(
        self,
        *,
        max_bytes: int = MAX_SOURCE_BYTES,
        timeout_seconds: float = 15.0,
        http_client: Any | None = None,
        resolve_dns: bool = True,
    ) -> None:
        self.max_bytes = int(max_bytes)
        self.timeout_seconds = float(timeout_seconds)
        self.http_client = http_client
        self.resolve_dns = bool(resolve_dns)
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

    def fetch(self, url: str) -> SourceResponse:
        validated_url = _validate_public_url(url, resolve_dns=self.resolve_dns)
        timeout = httpx.Timeout(self.timeout_seconds)
        owned_client = self.http_client is None
        client = self.http_client or httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "STECH-Enrichment-Worker/2.0"},
        )
        try:
            with client.stream("GET", validated_url, timeout=timeout, follow_redirects=True) as response:
                response.raise_for_status()
                header_length = response.headers.get("Content-Length")
                if header_length:
                    try:
                        if int(header_length) > self.max_bytes:
                            raise ValueError("source response exceeds 25 MB limit")
                    except ValueError as exc:
                        if "exceeds" in str(exc):
                            raise

                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError("source response exceeds 25 MB limit")
                    chunks.append(chunk)

                final_url = str(response.url)
                _validate_public_url(final_url, resolve_dns=self.resolve_dns)
                return SourceResponse(
                    content=b"".join(chunks),
                    content_type=response.headers.get("Content-Type"),
                    final_url=final_url,
                    content_length=size,
                )
        finally:
            if owned_client:
                client.close()
