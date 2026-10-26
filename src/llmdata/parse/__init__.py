"""Parse stage: PDF (with OCR fallback), HTML, email and records."""

from __future__ import annotations

import email
import email.policy
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

import pdfplumber
from pdfplumber.page import Page
from pypdf import PdfReader

from llmdata.db import connect
from llmdata.loader import load_object
from llmdata.pipeline.context import Context

BLOCKS = {"p", "h1", "h2", "h3", "li", "tr", "div", "br", "title"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in BLOCKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def html_text(raw: str) -> str:
    parser = _Text()
    parser.feed(raw)
    return "".join(parser.parts).strip()


def eml_text(data: bytes) -> str:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    body = msg.get_body(preferencelist=("plain",))
    content = body.get_content() if body is not None else ""
    return f"Subject: {msg['subject']}\n\n{content}".strip()


# region: pdf-adapters
class PdfParser(Protocol):
    """Anything that turns a PDF into one text per page."""

    def pages(self, path: Path) -> list[str]: ...


class PypdfParser:
    """Words in reading order; a table becomes plain lines."""

    def pages(self, path: Path) -> list[str]:
        return [p.extract_text() or "" for p in PdfReader(path).pages]


class PlumberParser:
    """Words in reading order; a ruled table becomes Markdown."""

    def pages(self, path: Path) -> list[str]:
        with pdfplumber.open(path) as pdf:
            return [page_text(page) for page in pdf.pages]


# endregion


# region: table-markdown
def markdown(rows: list[list[str | None]]) -> str:
    """Header row, a rule, then one line per data row."""
    lines = [
        "| " + " | ".join(c or "" for c in r) + " |" for r in rows
    ]
    rule = "|" + " --- |" * len(rows[0])
    return "\n".join([lines[0], rule, *lines[1:]])


def page_text(page: Page) -> str:
    """Lines outside tables, and each table where it sits."""
    tables = page.find_tables()
    rest: Page = page
    for table in tables:
        rest = rest.outside_bbox(table.bbox)
    blocks = [
        (ln["top"], ln["text"]) for ln in rest.extract_text_lines()
    ]
    blocks += [(t.bbox[1], markdown(t.extract())) for t in tables]
    return "\n".join(text for _, text in sorted(blocks))


# endregion


# region: ocr-fallback
MIN_CHARS = 20  # a page with less text than this is read as a scan


def ocr_page(path: Path, index: int, dpi: int = 300) -> str:
    with pdfplumber.open(path) as pdf:
        image = pdf.pages[index].to_image(resolution=dpi).original
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        image.save(png)
        done = subprocess.run(
            ["tesseract", str(png), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            check=True,
        )
    return done.stdout


def pdf_text(path: Path, parser: PdfParser) -> tuple[str, int]:
    """Every page of a PDF, and how many needed OCR."""
    pages, scanned = parser.pages(path), 0
    for i, text in enumerate(pages):
        if len(text.strip()) < MIN_CHARS:
            pages[i], scanned = ocr_page(path, i), scanned + 1
    return "\n\n".join(pages), scanned


# endregion


# region: parse-stage
DEFAULT = "llmdata.parse:PlumberParser"


def parse_one(
    kind: str, path: Path | None, raw: str, parser: PdfParser
) -> tuple[str, int]:
    if kind == "record" or path is None:
        return raw, 0
    if kind == "pdf":
        return pdf_text(path, parser)
    if kind == "html":
        return html_text(path.read_text(encoding="utf-8")), 0
    return eml_text(path.read_bytes()), 0


def run(ctx: Context) -> None:
    parser = load_object(str(ctx.params.get("pdf", DEFAULT)))()
    landing, scanned = ctx.settings.data_dir / "landing", 0
    with connect(ctx.settings.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, kind, ref, raw FROM staged"
            " WHERE run_id = %s AND op = 'upsert' AND parsed IS NULL"
            " ORDER BY doc_key",
            (ctx.run_id,),
        ).fetchall()
        for i, (key, kind, ref, raw) in enumerate(rows, 1):
            path = landing / ref if ref else None
            text, pages = parse_one(kind, path, raw or "", parser)
            scanned += pages
            conn.execute(
                "UPDATE staged SET parsed = %s"
                " WHERE run_id = %s AND doc_key = %s",
                (text, ctx.run_id, key),
            )
            if i % 20 == 0:
                conn.commit()  # a retry resumes after this batch
    print(f"parsed {len(rows)} documents; {scanned} pages by OCR")


# endregion
