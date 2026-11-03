"""Operations: every target checked often, each with a runbook."""

from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path

from llmdata.config import settings
from llmdata.db import Conn, connect
from llmdata.freshness import lag
from llmdata.pipeline.context import Context

LIMITS = Path(__file__).with_name("limits.toml")


class OpsError(RuntimeError):
    """A target is missed; the message names the runbooks."""


# region: ops-checks
@dataclass(frozen=True)
class Check:
    name: str  # also the runbook's name
    ok: bool
    detail: str


def checks(conn: Conn) -> list[Check]:
    """One result for every target the data layer has promised."""
    found = [
        Check(
            "freshness", r["ok"], f"{n}: {r['lag']} of {r['target']}"
        )
        for n, r in lag().items()
    ]
    for name, t in tomllib.loads(LIMITS.read_text()).items():
        row = conn.execute(t["query"]).fetchone()
        value = row[0] if row else None
        ok = value is not None and value <= t["limit"]
        shown = "none" if value is None else f"{value:.0f}"
        detail = f"{shown} {t['unit']}; limit {t['limit']}"
        found.append(Check(name, ok, detail))
    return found


# endregion


def run(ctx: Context) -> None:
    """The scheduled check: fail, naming runbooks, on any miss."""
    with connect(ctx.settings.dsn) as conn:
        found = checks(conn)
    for c in found:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.name:<13} {c.detail}")
    failed = sorted({c.name for c in found if not c.ok})
    if failed:
        books = ", ".join(f"docs/runbooks/{b}.md" for b in failed)
        raise OpsError(f"targets missed; follow {books}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.ops")
    parser.add_argument("command", choices=["check"])
    parser.parse_args(argv)
    with connect(settings().dsn) as conn:
        found = checks(conn)
    for c in found:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark} {c.name:<13} {c.detail}")
    return 0 if all(c.ok for c in found) else 1


if __name__ == "__main__":
    raise SystemExit(main())
