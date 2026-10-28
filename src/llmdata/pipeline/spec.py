"""Stage files: pipelines/<name>/NN-stage[+tag].toml.

Standard library only, because Airflow's own interpreter imports
this module when it parses the DAG factory.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESERVED = {"policies", "profiles"}


@dataclass(frozen=True)
class Policy:
    retries: int = 0
    retry_delay_s: int = 30
    timeout_s: int = 3600
    keep_staged_runs: int | None = None
    backfill_batch: int = 100
    schedules: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class Stage:
    name: str
    chapter: int
    callable: str
    params: dict[str, Any] = field(default_factory=dict)


def chapter_no(until: str | int | None) -> int:
    if until is None or until == "":
        return 99
    return int(str(until).lower().removeprefix("ch"))


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if key == "chapter" and "chapter" in base:
            continue
        if isinstance(value, dict) and isinstance(
            base.get(key), dict
        ):
            _merge(base[key], value)
        else:
            base[key] = value


def _files(folder: Path) -> list[tuple[str, Path]]:
    found = []
    for path in folder.glob("*.toml"):
        base, plus, _ = path.stem.partition("+")
        found.append((base, 1 if plus else 0, path))
    found.sort(key=lambda t: (t[0], t[1], t[2].name))
    return [(base, path) for base, _, path in found]


def pipelines(root: Path) -> list[str]:
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name not in RESERVED
    )


# region: stage-loader
def load(
    root: Path,
    name: str,
    until: str | int | None = None,
    profile: str | None = None,
) -> list[Stage]:
    limit = chapter_no(until)
    folders = [root / name]
    if profile:
        folders.append(root / "profiles" / profile / name)
    merged: dict[str, dict[str, Any]] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for base, path in _files(folder):
            data = _read(path)
            if int(data.get("chapter", 0)) > limit:
                continue
            _merge(merged.setdefault(base, {}), data)
    return [
        Stage(
            name=key,
            chapter=int(value["chapter"]),
            callable=str(value["callable"]),
            params=dict(value.get("params", {})),
        )
        for key, value in sorted(merged.items())
        if "callable" in value
    ]


# endregion


def policy(root: Path, until: str | int | None = None) -> Policy:
    limit = chapter_no(until)
    merged: dict[str, Any] = {}
    for _, path in _files(root / "policies"):
        data = _read(path)
        if int(data.get("chapter", 0)) > limit:
            continue
        for key, value in data.items():
            if key == "schedules":  # merged by pipeline name
                merged.setdefault(key, {}).update(value)
            elif key != "chapter":
                merged[key] = value
    return Policy(**merged)
