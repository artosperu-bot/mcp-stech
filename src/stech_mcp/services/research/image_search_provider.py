from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImageSearchResult:
    title: str
    image_url: str
    page_url: str | None = None
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    source_domain: str | None = None


class ImageSearchProvider(Protocol):
    def search(self, query: str, count: int = 10) -> list[ImageSearchResult]: ...