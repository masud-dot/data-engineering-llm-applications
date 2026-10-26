"""versions.toml must agree with uv.lock and the image references."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-digests", action="store_true")
    args = parser.parse_args()
    with Path("versions.toml").open("rb") as fh:
        wanted = tomllib.load(fh)
    with Path("uv.lock").open("rb") as fh:
        locked = {
            p["name"]: p["version"]
            for p in tomllib.load(fh)["package"]
            if "version" in p
        }
    problems = []
    for name, version in wanted["packages"].items():
        if locked.get(name) != version:
            problems.append(
                f"{name}: {version} != lock {locked.get(name)}"
            )
    used = Path("deploy/compose/images.env").read_text()
    for name, ref in wanted["images"].items():
        if ref not in used:
            problems.append(f"image {name}: {ref} not used")
        if args.require_digests and "@sha256:" not in ref:
            problems.append(f"image {name}: not pinned by digest")
    python = Path(".python-version").read_text().strip()
    if python != wanted["python"]:
        problems.append(f"python {wanted['python']} != {python}")
    print(
        f"{len(wanted['packages'])} packages and"
        f" {len(wanted['images'])} images checked"
    )
    print("\n".join(problems) or "versions agree")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
