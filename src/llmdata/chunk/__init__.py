"""Chunk stage: cut cleaned text along the document's structure."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

from llmdata.db import connect
from llmdata.pipeline.context import Context

SENTENCE = re.compile(r"(?<=[.!?])\s+")
Section = tuple[str, list["Block"]]


# region: chunk-structure
@dataclass(frozen=True)
class Block:
    kind: str  # "table" or "prose"
    text: str


def structure(
    text: str, heading: re.Pattern[str]
) -> tuple[str, list[Section]]:
    """The context header, then each heading with its blocks."""
    lines = text.splitlines()
    first = next(
        (i for i, ln in enumerate(lines) if heading.match(ln)), 1
    )
    sections: list[Section] = [("", [])]
    prev = ""  # the kind of the line before, or "" after a gap
    for line in lines[first:]:
        blocks = sections[-1][1]
        kind = "table" if line.startswith("|") else "prose"
        if heading.match(line):
            sections.append((line, []))
            prev = ""
        elif not line:
            prev = ""
        elif kind == prev:
            joint = "\n" if kind == "table" else " "
            blocks[-1] = Block(kind, blocks[-1].text + joint + line)
        else:
            blocks.append(Block(kind, line))
            prev = kind
    head = "\n".join(lines[:first])
    return head, [s for s in sections if s[0] or s[1]]


# endregion


# region: chunk-split
def pack(items: list[str], budget: int, joint: str) -> list[str]:
    """Join items in order into parts no longer than the budget."""
    parts: list[str] = []
    for item in items:
        room = budget - len(joint) - len(item)
        if parts and len(parts[-1]) <= room:
            parts[-1] += joint + item
        elif len(item) > budget and "\n" not in item:
            parts += textwrap.wrap(item, budget)  # one long sentence
        else:
            parts.append(item)
    return parts


def split(block: Block, budget: int) -> list[str]:
    """A block that fits, or parts that fit, with whole table rows."""
    if len(block.text) <= budget:
        return [block.text]
    if block.kind == "prose":
        return pack(SENTENCE.split(block.text), budget, " ")
    header, rule, *rows = block.text.split("\n")
    parts = [[header, rule]]
    for row in rows:
        width = len("\n".join([*parts[-1], row]))
        if width > budget and len(parts[-1]) > 2:
            parts.append([header, rule])  # repeat the header row
        parts[-1].append(row)
    return ["\n".join(part) for part in parts]


# endregion


# region: chunker
@dataclass(frozen=True)
class Piece:
    section: str  # the heading this chunk falls under, or ""
    text: str  # context header, heading and body: what is embedded


def chunk(
    text: str, size: int, heading: re.Pattern[str]
) -> list[Piece]:
    """Chunks that never cross a heading or cut a table row."""
    head, sections = structure(text, heading)
    pieces: list[Piece] = []
    for title, blocks in sections or [("", [])]:
        context = "\n".join(filter(None, (head, title)))
        budget = size - len(context) - 2
        parts = [p for b in blocks for p in split(b, budget)]
        for body in pack(parts, budget, "\n\n") or [""]:
            pieces.append(
                Piece(title, f"{context}\n\n{body}".strip())
            )
    return [p for p in pieces if p.text]


# endregion


# region: chunk-stage
def run(ctx: Context) -> None:
    size = int(ctx.params.get("size", 900))
    heading = re.compile(str(ctx.params.get("headings", "(?!)")))
    total = 0
    with connect(ctx.settings.dsn) as conn:
        conn.execute(
            "DELETE FROM staged_chunks WHERE run_id = %s",
            (ctx.run_id,),
        )
        rows = conn.execute(
            "SELECT doc_key, cleaned FROM staged"
            " WHERE run_id = %s AND op = 'upsert' ORDER BY doc_key",
            (ctx.run_id,),
        ).fetchall()
        for key, cleaned in rows:
            pieces = chunk(cleaned or "", size, heading)
            for ordinal, piece in enumerate(pieces):
                conn.execute(
                    "INSERT INTO staged_chunks (run_id, doc_key,"
                    " ordinal, section, text)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (
                        ctx.run_id,
                        key,
                        ordinal,
                        piece.section,
                        piece.text,
                    ),
                )
            total += len(pieces)
    print(f"{total} chunks from {len(rows)} documents")


# endregion
