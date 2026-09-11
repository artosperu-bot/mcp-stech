from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SearchProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    description: str | None = None


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        domains: tuple[str, ...] = (),
        limit: int = 5,
    ) -> list[SearchResult]: ...
