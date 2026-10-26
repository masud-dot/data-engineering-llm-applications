"""S-3: parser accuracy on golden PDFs; OCR accuracy on scans."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader
from rapidfuzz.distance import Levenshtein

sys.path.insert(0, "src")
from llmdata.parse import ocr_page  # noqa: E402

DATA = Path("data")


def norm(text: str) -> str:
    return " ".join(text.split())


def score(got: str, want: str) -> float:
    target = norm(want)
    lost = Levenshtein.distance(norm(got), target)
    return max(0.0, 1 - lost / max(1, len(target)))


def digital(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        path = DATA / "landing" / item["pdf"]
        pages = {"pypdf": [p.extract_text() or ""
                           for p in PdfReader(path).pages]}
        with pdfplumber.open(path) as pdf:
            pages["pdfplumber"] = [p.extract_text() or ""
                                   for p in pdf.pages]
            grid = [norm(c or "") for t in pdf.pages[0].extract_tables()
                    for row in t for c in row]
        cells = [norm(c) for row in item["table"] for c in row]
        for engine, texts in pages.items():
            chars = statistics.mean(
                score(g, w) for g, w in zip(texts, item["pages"],
                                            strict=True))
            pool = grid if engine == "pdfplumber" else [norm(texts[0])]
            kept = sum(any(c == p or (engine == "pypdf" and c in p)
                           for p in pool) for c in cells) / len(cells)
            rows.append({"pdf": item["pdf"], "engine": engine,
                         "chars": round(chars, 4), "cells": kept})
    return rows


def scans(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        path = DATA / "landing" / item["pdf"]
        for i, want in enumerate(item["pages"]):
            rows.append({"pdf": item["pdf"], "page": i + 1,
                         "chars": round(score(ocr_page(path, i), want),
                                        4)})
    return rows


def main() -> int:
    golden = json.loads((DATA / "golden" / "manifest.json").read_text())
    pdf_rows, ocr_rows = digital(golden["digital"]), scans(golden["scans"])
    summary: dict[str, Any] = {}
    for engine in ("pypdf", "pdfplumber"):
        mine = [r for r in pdf_rows if r["engine"] == engine]
        summary[engine] = {
            "files": len(mine),
            "mean_chars": round(statistics.mean(r["chars"] for r in mine),
                                4),
            "min_chars": min(r["chars"] for r in mine),
            "cells_kept": round(statistics.mean(r["cells"]
                                                for r in mine), 4),
        }
    summary["ocr"] = {
        "pages": len(ocr_rows),
        "mean_chars": round(statistics.mean(r["chars"]
                                            for r in ocr_rows), 4),
        "min_chars": min(r["chars"] for r in ocr_rows),
    }
    passing = [e for e in ("pdfplumber", "pypdf")
               if summary[e]["mean_chars"] >= 0.98
               and summary[e]["cells_kept"] == 1.0]
    summary["chosen"] = passing[0] if passing else None
    summary["pass"] = bool(passing) and summary["ocr"]["mean_chars"] >= 0.9
    Path("spike").mkdir(exist_ok=True)
    Path("spike/s3.json").write_text(json.dumps(
        {"summary": summary, "pdf": pdf_rows, "ocr": ocr_rows}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
