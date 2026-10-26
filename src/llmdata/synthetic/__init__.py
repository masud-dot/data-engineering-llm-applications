"""Seeded synthetic corpus for Quillmere Mutual, a fictional insurer.

Everything here is invented: names, phone numbers in the 07700 900
drama range, and addresses under the reserved .example domain.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import textwrap
import tomllib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import numpy as np
import pdfplumber
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from llmdata.db import connect

REGIONS = ("north", "south", "east", "west")
BASE = datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
SCALES = {
    "full": {
        "wordings": 60,
        "endorsements": 25,
        "guidelines": 120,
        "emails": 115,
        "claims": 200,
    },
    "small": {
        "wordings": 3,
        "endorsements": 0,
        "guidelines": 4,
        "emails": 4,
        "claims": 10,
    },
}
GOLDEN = {"digital": 20, "scans": 5}
RECORD = Path("data/synthetic/corpus.toml")
WORDS = (
    "cover claim policy insured premium excess limit property damage"
    " escape water storm flood theft accidental contents buildings"
    " tenant landlord inspection survey notice period renewal"
    " endorsement exclusion condition warranty liability loss"
    " adjuster"
    " settlement repair replacement valuation subsidence fire smoke"
    " lightning impact vandalism garden outbuilding unoccupied"
).split()
COVERS = [
    "Buildings",
    "Contents",
    "Accidental damage",
    "Escape of water",
    "Storm and flood",
    "Theft",
    "Garden and outbuildings",
    "Alternative accommodation",
]
EXCLUSIONS = [
    "Wear and tear",
    "Gradual deterioration",
    "Unoccupied over 60 days",
    "Faulty workmanship",
    "Pets",
    "Frost damage",
]
FIRST = [
    "Asha",
    "Ben",
    "Chloe",
    "Dev",
    "Elin",
    "Farid",
    "Grace",
    "Hamish",
    "Isla",
    "Jonah",
    "Kiran",
    "Lena",
    "Mateo",
    "Nia",
]
LAST = [
    "Abbot",
    "Barlow",
    "Carver",
    "Dunmore",
    "Ellery",
    "Fenwick",
    "Garside",
    "Hollis",
    "Ingram",
    "Jessop",
    "Kerridge",
    "Lomax",
]
STATUSES = ["open", "assessing", "settled", "closed"]
Corpus = dict[str, Any]


def sentence(rng: random.Random) -> str:
    words = " ".join(
        rng.choice(WORDS) for _ in range(rng.randint(8, 15))
    )
    return words[0].upper() + words[1:] + "."


def paragraph(rng: random.Random, low: int = 3, high: int = 5) -> str:
    return " ".join(
        sentence(rng) for _ in range(rng.randint(low, high))
    )


def wrap(text: str) -> list[str]:
    return textwrap.wrap(text, 88)


def person(rng: random.Random) -> tuple[str, str, str]:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    phone = f"+44 7700 900{rng.randint(0, 999):03d}"
    return (
        f"{first} {last}",
        phone,
        f"{first}.{last}@example.com".lower(),
    )


def wording(rng: random.Random, i: int) -> dict[str, Any]:
    name, region = f"WRD-{i:04d}", REGIONS[i % 4]
    top = [
        f"Quillmere Mutual Home Policy Wording {name}",
        f"Region {region.title()}. Edition 2027.{1 + i % 4}",
    ]
    for n, title in enumerate(("Cover", "Conditions"), 1):
        top += [f"{n}. {title}", *wrap(paragraph(rng))]
    table = [["Cover", "Limit", "Excess", "Exclusion"]] + [
        [
            rng.choice(COVERS),
            f"GBP {rng.randint(5, 500) * 100}",
            f"GBP {rng.choice((100, 250, 350, 500))}",
            rng.choice(EXCLUSIONS),
        ]
        for _ in range(5)
    ]
    second: list[str] = []
    for n, title in enumerate(
        ("Exclusions", "Claims", "Complaints"), 3
    ):
        second += [f"{n}. {title}", *wrap(paragraph(rng, 4, 6))]
    return {
        "name": name,
        "region": region,
        "table": table,
        "pages": [top, second],
    }


def endorsement(rng: random.Random, i: int) -> dict[str, Any]:
    name, region = f"END-{i:04d}", REGIONS[i % 4]
    pages = []
    for k in (1, 2):
        lines = [
            f"Endorsement {name} page {k}",
            f"Policy POL-{rng.randint(1, 900):05d}. Region"
            f" {region.title()}.",
        ]
        lines += wrap(paragraph(rng, 5, 7)) + wrap(
            paragraph(rng, 5, 7)
        )
        pages.append(lines)
    return {"name": name, "region": region, "pages": pages}


def guideline(rng: random.Random, i: int) -> dict[str, Any]:
    name, region = f"GL-{i:04d}", REGIONS[i % 4]
    parts = [
        "<!doctype html><html><head>",
        f"<title>{name}</title>",
        "<style>p {margin: 0}</style></head><body>",
        f"<h1>Underwriting guideline {name}</h1>",
        "<p>Quillmere Mutual · Internal</p>",
    ]
    for title in ("Appetite", "Referral triggers", "Evidence"):
        parts.append(f"<h2>{title}</h2><p>{paragraph(rng)}</p>")
    parts.append("<script>track()</script></body></html>")
    return {"name": name, "region": region, "text": "\n".join(parts)}


def email_doc(rng: random.Random, i: int) -> dict[str, Any]:
    name, region = f"EM-{i:04d}", REGIONS[i % 4]
    who, phone, address = person(rng)
    msg = EmailMessage()
    msg["From"] = f"{who} <{address}>"
    msg["To"] = "claims@quillmere.example"
    msg["Subject"] = f"Claim CLM-{rng.randint(1, 200):05d} update"
    msg["Date"] = format_datetime(BASE + timedelta(hours=i))
    msg["Message-ID"] = f"<{name}@quillmere.example>"
    msg.set_content(
        f"Hello,\n\n{paragraph(rng)}\n\nCall me on {phone}."
        f"\n\n{who}\n"
    )
    return {"name": name, "region": region, "text": msg.as_string()}


def claims(rng: random.Random, count: int) -> list[list[Any]]:
    rows = []
    for i in range(1, count + 1):
        who, phone, address = person(rng)
        note = (
            f"Caller {who} ({phone}, {address}) reported "
            f"{sentence(rng).lower()} {paragraph(rng, 2, 3)}"
        )
        rows.append(
            [
                f"CLM-{i:05d}",
                f"POL-{rng.randint(1, 900):05d}",
                REGIONS[i % 4],
                rng.choice(STATUSES),
                note,
                (BASE + timedelta(seconds=i)).isoformat(),
            ]
        )
    return rows


def plan(scale: str) -> Corpus:
    counts = SCALES[scale]
    rng = random.Random(f"quillmere-{scale}")
    makers = {
        "wordings": wording,
        "endorsements": endorsement,
        "guidelines": guideline,
        "emails": email_doc,
    }
    corpus: Corpus = {
        origin: [make(rng, i) for i in range(1, counts[origin] + 1)]
        for origin, make in makers.items()
    }
    corpus["claims"] = claims(rng, counts["claims"])
    return corpus


def corpus_hash(corpus: Corpus) -> str:
    text = json.dumps(corpus, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def draw_pdf(
    path: Path,
    pages: list[list[str]],
    table: list[list[str]] | None = None,
) -> None:
    canvas = Canvas(str(path), pagesize=A4, invariant=1)
    for number, lines in enumerate(pages, 1):
        canvas.setFont("Helvetica", 10)
        y = 800.0
        for line in lines:
            canvas.drawString(60, y, line)
            y -= 14
        if table and number == 1:
            xs = [60, 190, 280, 360, 535]
            y -= 6
            for row in table:
                for x, cell in zip(xs, row, strict=False):
                    canvas.drawString(x + 4, y - 13, cell)
                canvas.line(xs[0], y, xs[-1], y)
                y -= 18
            canvas.line(xs[0], y, xs[-1], y)
            top = y + 18 * len(table)
            for x in xs:
                canvas.line(x, top, x, y)
        canvas.drawString(
            60,
            40,
            f"Quillmere Mutual · Page {number} of {len(pages)}",
        )
        canvas.showPage()
    canvas.save()


def degrade(image: Image.Image, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    gray = image.convert("L").rotate(
        float(rng.uniform(-0.6, 0.6)),
        resample=Image.Resampling.BICUBIC,
        fillcolor=255,
    )
    noise = rng.normal(0, 10, size=(gray.height, gray.width))
    pixels = np.asarray(gray, dtype=np.float64) + noise
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def scan_pdf(path: Path, pages: list[list[str]], seed: int) -> None:
    digital = path.with_suffix(".tmp.pdf")
    draw_pdf(digital, pages)
    with pdfplumber.open(digital) as pdf:
        images = [
            degrade(p.to_image(resolution=200).original, seed + n)
            for n, p in enumerate(pdf.pages)
        ]
    digital.unlink()
    stamp = BASE.timetuple()
    images[0].save(
        path,
        "PDF",
        resolution=200.0,
        save_all=True,
        creationDate=stamp,
        modDate=stamp,
        append_images=images[1:],
    )


def truth(doc: dict[str, Any]) -> list[str]:
    pages = [list(lines) for lines in doc["pages"]]
    if "table" in doc:  # the grid as Markdown, header first
        rows = ["| " + " | ".join(row) + " |" for row in doc["table"]]
        rule = "|" + " --- |" * len(doc["table"][0])
        pages[0] += [rows[0], rule, *rows[1:]]
    total = len(pages)
    return [
        "\n".join([*lines, f"Quillmere Mutual · Page {n} of {total}"])
        for n, lines in enumerate(pages, 1)
    ]


def write_files(corpus: Corpus, data_dir: Path) -> None:
    landing = data_dir / "landing"
    shutil.rmtree(landing, ignore_errors=True)
    golden: dict[str, list[dict[str, Any]]] = {
        "digital": [],
        "scans": [],
    }
    for origin, ext in (
        ("wordings", "pdf"),
        ("endorsements", "pdf"),
        ("guidelines", "html"),
        ("emails", "eml"),
    ):
        for n, doc in enumerate(corpus[origin]):
            ref = f"{origin}/{doc['region']}/{doc['name']}.{ext}"
            path = landing / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            if origin == "wordings":
                draw_pdf(path, doc["pages"], doc["table"])
                if n < GOLDEN["digital"]:
                    golden["digital"].append(
                        {
                            "pdf": ref,
                            "pages": truth(doc),
                            "table": doc["table"],
                        }
                    )
            elif origin == "endorsements":
                scan_pdf(path, doc["pages"], seed=1000 + n * 10)
                if n < GOLDEN["scans"]:
                    golden["scans"].append(
                        {"pdf": ref, "pages": truth(doc)}
                    )
            else:
                path.write_text(doc["text"], encoding="utf-8")
    target = data_dir / "golden" / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(golden, indent=1, ensure_ascii=False)
    )


def load_claims(dsn: str, rows: list[list[Any]]) -> None:
    with connect(dsn, vectors=False) as conn:
        conn.execute("DROP TABLE IF EXISTS claims, changesets")
        conn.execute(
            "CREATE TABLE claims (claim_id text PRIMARY KEY,"
            " policy_id text NOT NULL, region text NOT NULL,"
            " status text NOT NULL, note text NOT NULL,"
            " updated_at timestamptz NOT NULL,"
            " deleted_at timestamptz)"
        )
        conn.execute(
            "CREATE TABLE changesets (day int PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO claims VALUES"
                " (%s, %s, %s, %s, %s, %s, NULL)",
                rows,
            )


def parse_changes(spec: str) -> dict[str, float]:
    found = dict(re.findall(r"(\w+):([\d.]+)", spec))
    return {
        k: float(found.get(k, 0)) for k in ("update", "soft", "hard")
    }


def apply_changes(
    dsn: str, data_dir: Path, day: int, pct: dict[str, float]
) -> dict[str, int]:
    rng = random.Random(f"day-{day}")
    stamp = BASE + timedelta(days=day)
    with connect(dsn, vectors=False) as conn:
        seen = conn.execute(
            "SELECT 1 FROM changesets WHERE day = %s", (day,)
        ).fetchone()
        if seen:
            return {}
        live = [
            r[0]
            for r in conn.execute(
                "SELECT claim_id FROM claims WHERE deleted_at IS NULL"
                " ORDER BY claim_id"
            )
        ]
        n = {k: round(len(live) * v / 100) for k, v in pct.items()}
        picked = rng.sample(live, sum(n.values()))
        ups = picked[: n["update"]]
        softs = picked[n["update"] : n["update"] + n["soft"]]
        hards = picked[n["update"] + n["soft"] :]
        for i, cid in enumerate(ups):
            conn.execute(
                "UPDATE claims SET note = note || %s, updated_at = %s"
                " WHERE claim_id = %s",
                (
                    f" Update day {day}: {sentence(rng)}",
                    stamp + timedelta(seconds=i),
                    cid,
                ),
            )
        for i, cid in enumerate(softs):
            conn.execute(
                "UPDATE claims SET deleted_at = %s, updated_at = %s"
                " WHERE claim_id = %s",
                (stamp, stamp + timedelta(seconds=i), cid),
            )
        conn.execute(
            "DELETE FROM claims WHERE claim_id = ANY(%s)", (hards,)
        )
        conn.execute(
            "INSERT INTO changesets (day) VALUES (%s)", (day,)
        )
    landing = data_dir / "landing"
    files = sorted(
        p
        for origin in ("guidelines", "emails")
        for p in (landing / origin).rglob("*")
        if p.is_file()
    )
    edit = round(len(files) * pct["update"] / 100)
    drop = round(len(files) * pct["hard"] / 100)
    chosen = rng.sample(files, edit + drop)
    for path in chosen[:edit]:
        text, extra = path.read_text(encoding="utf-8"), paragraph(rng)
        if path.suffix == ".html":
            text = text.replace("</body>", f"<p>{extra}</p></body>")
        else:
            text += f"\n{extra}\n"
        path.write_text(text, encoding="utf-8")
    for path in chosen[edit:]:
        path.unlink()
    return {
        "claims_updated": len(ups),
        "claims_soft": len(softs),
        "claims_hard": len(hards),
        "files_updated": edit,
        "files_removed": drop,
    }


def recorded(scale: str) -> str | None:
    if not RECORD.exists():
        return None
    with RECORD.open("rb") as fh:
        value = tomllib.load(fh).get("hash", {}).get(scale)
    return str(value) if value else None
