"""Listing parity: every numbered listing is a marked file region."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

START = re.compile(r"^\s*(?:#|--)\s*region:\s*(\S+)\s*$")
END = re.compile(r"^\s*(?:#|--)\s*endregion\s*$")
SAMPLE = "a = 1\n# region: demo\nb = 2\n\nc = 3\n# endregion\n"


def regions(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        start = START.match(line)
        if start:
            name, lines = start.group(1), []
        elif END.match(line) and name:
            found[name] = "\n".join(lines).strip("\n")
            name = None
        elif name:
            lines.append(line.rstrip())
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--manuscript",
        type=Path,
        help="folder of listing-<n>.txt files",
    )
    args = parser.parse_args()
    if args.self_test:
        assert regions(SAMPLE) == {"demo": "b = 2\n\nc = 3"}
        print("check_listings self-test passed")
        return 0
    with Path("tools/listings.toml").open("rb") as fh:
        table = tomllib.load(fh).get("listings", {})
    problems = []
    for number, where in sorted(table.items()):
        path = Path(where["file"])
        code = regions(path.read_text()).get(where["region"])
        if code is None:
            problems.append(f"{number}: region missing in {path}")
            continue
        if args.manuscript:
            printed = args.manuscript / f"listing-{number}.txt"
            if printed.read_text().strip("\n") != code:
                problems.append(f"{number}: differs from {path}")
    print(f"{len(table)} listings checked, {len(problems)} problems")
    print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
