from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Callable

from pypdf import PdfReader

from stech_mcp.http.source_client import SourceClient


_SOURCE_CONFIDENCE = {
    "MANUFACTURER": "A1",
    "OFFICIAL_DOCUMENT": "A2",
    "MANUAL": "A2",
    "AUTHORIZED_DISTRIBUTOR": "B",
    "TRUSTED_RETAILER": "C",
}


class _VisibleTextParser(HTMLParser):
    _IGNORED = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lower = tag.lower()
        if lower in self._IGNORED:
            self._ignored_depth += 1
        if lower == "title" and self._ignored_depth == 0:
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "title":
            self._in_title = False
        if lower in self._IGNORED and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self._in_title:
            self.title_parts.append(cleaned)

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)

    @property
    def title(self) -> str | None:
        value = " ".join(self.title_parts).strip()
        return value or None


def _contains_exact_partnumber(text: str, partnumber: str) -> bool:
    return partnumber.casefold() in text.casefold()


class SourceDocumentService:
    def __init__(
        self,
        *,
        document_repository: Any,
        http_client: Any | None = None,
        pdf_reader_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.http_client = http_client or SourceClient()
        self.document_repository = document_repository
        self.pdf_reader_factory = pdf_reader_factory or PdfReader

    def _extract_pdf(self, content: bytes) -> tuple[str | None, list[dict[str, Any]]]:
        reader = self.pdf_reader_factory(BytesIO(content))
        pages: list[dict[str, Any]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = " ".join(str(page.extract_text() or "").split())
            pages.append({"page": index, "text": text})
        return None, pages

    @staticmethod
    def _extract_html(content: bytes) -> tuple[str | None, list[dict[str, Any]]]:
        text = content.decode("utf-8", errors="replace")
        parser = _VisibleTextParser()
        parser.feed(text)
        parser.close()
        return parser.title, [{"page": 1, "text": parser.text}]

    def ingest(self, url: str, partnumber: str, source_type: str) -> dict[str, Any]:
        pn = str(partnumber or "").strip().upper()
        source = str(source_type or "").strip().upper()
        if not pn:
            raise ValueError("partnumber is required")
        if not source:
            raise ValueError("source_type is required")

        response = self.http_client.fetch(url)
        digest = sha256(response.content).hexdigest()
        content_type = str(response.content_type or "").lower()
        final_url = str(response.final_url)
        is_pdf = "application/pdf" in content_type or final_url.lower().split("?", 1)[0].endswith(".pdf")
        document_type = "PDF" if is_pdf else "HTML"

        if is_pdf:
            title, pages = self._extract_pdf(response.content)
        else:
            title, pages = self._extract_html(response.content)

        full_text = "\n".join(page["text"] for page in pages if page.get("text"))
        matched_pages = [
            int(page["page"])
            for page in pages
            if _contains_exact_partnumber(str(page.get("text") or ""), pn)
        ]
        exact_match = bool(matched_pages)
        confidence = _SOURCE_CONFIDENCE.get(source, "C") if exact_match else "E"
        match_type = "EXACT_PN" if exact_match else "NO_EXACT_PN"

        document = self.document_repository.upsert_by_hash(
            sha256=digest,
            url=final_url,
            document_type=document_type,
            title=title,
            content_type=response.content_type,
            content_length=int(response.content_length),
            extracted_text=full_text,
            pages=pages,
        )
        document_id = int(document["source_document_id"])
        self.document_repository.add_match(
            document_id,
            partnumber=pn,
            match_type=match_type,
            pages=matched_pages,
            confidence=confidence,
        )

        return {
            "document_id": document_id,
            "sha256": digest,
            "url": document.get("url") or final_url,
            "document_type": document_type,
            "title": title or document.get("title"),
            "content_type": response.content_type,
            "content_length": int(response.content_length),
            "pages": pages,
            "text": full_text,
            "matched_pages": matched_pages,
            "match_type": match_type,
            "confidence_rank": confidence,
            "source_type": source,
            "partnumber": pn,
        }
