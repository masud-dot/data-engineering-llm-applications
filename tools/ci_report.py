"""Post CI output as a check run that the API can read."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LIMIT = 60000


def main() -> int:
    name, *paths = sys.argv[1:]
    parts = []
    for item in paths:
        path = Path(item)
        text = (
            path.read_text(errors="replace") if path.exists() else ""
        )
        parts.append(f"## {item}\n\n{text[-25000:] or '(missing)'}")
    Path("ci-report.md").write_text("\n\n".join(parts)[-LIMIT:])
    repo, sha = (
        os.environ["GITHUB_REPOSITORY"],
        os.environ["GITHUB_SHA"],
    )
    subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/check-runs",
            "-f",
            f"name={name}-report",
            "-f",
            f"head_sha={sha}",
            "-f",
            "status=completed",
            "-f",
            "conclusion=neutral",
            "-f",
            f"output[title]={name} report",
            "-F",
            "output[summary]=@ci-report.md",
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
