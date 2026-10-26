"""Parse stage: PDF (with OCR fallback), HTML, email and records."""

from __future__ import annotations

import email
import email.policy
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from llmdata.db import connect
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


def pdf_pages(path: Path, engine: str) -> list[str]:
    if engine == "pypdf":
        texts = [
            p.extract_text() or "" for p in PdfReader(path).pages
        ]
    else:
        with pdfplumber.open(path) as pdf:
            texts = [p.extract_text() or "" for p in pdf.pages]
    return [
        text if len(text.strip()) >= 20 else ocr_page(path, i)
        for i, text in enumerate(texts)
    ]


def parse_one(
    kind: str, path: Path | None, raw: str, engine: str
) -> str:
    if kind == "record" or path is None:
        return raw
    if kind == "pdf":
        return "\n\n".join(pdf_pages(path, engine))
    if kind == "html":
        return html_text(path.read_text(encoding="utf-8"))
    return eml_text(path.read_bytes())


def run(ctx: Context) -> None:
    engine = str(ctx.params.get("pdf", "pdfplumber"))
    landing = ctx.settings.data_dir / "landing"
    with connect(ctx.settings.dsn) as conn:
        rows = conn.execute(
            "SELECT doc_key, kind, ref, raw FROM staged"
            " WHERE run_id = %s AND op = 'upsert' AND parsed IS NULL"
            " ORDER BY doc_key",
            (ctx.run_id,),
        ).fetchall()
        for i, (key, kind, ref, raw) in enumerate(rows, 1):
            path = landing / ref if ref else None
            text = parse_one(kind, path, raw or "", engine)
            conn.execute(
                "UPDATE staged SET parsed = %s"
                " WHERE run_id = %s AND doc_key = %s",
                (text, ctx.run_id, key),
            )
            if i % 20 == 0:
                conn.commit()
    print(f"parsed {len(rows)} documents ({engine})")
