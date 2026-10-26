"""Check rows at a boundary: fail loudly, or return violations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError


class Violation(NamedTuple):
    key: str
    field: str
    message: str


class ContractError(RuntimeError):
    def __init__(
        self, model: str, violations: list[Violation]
    ) -> None:
        shown = "; ".join(
            f"{v.key} {v.field}: {v.message}" for v in violations[:5]
        )
        super().__init__(
            f"{len(violations)} {model} rows break the contract:"
            f" {shown}"
        )
        self.violations = violations


def validate[M: BaseModel](
    model: type[M], rows: Iterable[Mapping[str, Any]], key: str
) -> tuple[list[M], list[Violation]]:
    good: list[M] = []
    bad: list[Violation] = []
    for row in rows:
        try:
            good.append(model.model_validate(row))
        except ValidationError as exc:
            for error in exc.errors():
                field = (
                    ".".join(str(p) for p in error["loc"]) or "row"
                )
                bad.append(
                    Violation(str(row.get(key)), field, error["msg"])
                )
    return good, bad


def require[M: BaseModel](
    model: type[M], rows: Iterable[Mapping[str, Any]], key: str
) -> list[M]:
    good, bad = validate(model, rows, key)
    if bad:
        raise ContractError(model.__name__, bad)
    return good
