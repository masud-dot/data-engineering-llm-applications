"""Freshness and deletion targets, read from slas.toml."""

from __future__ import annotations

import tomllib
from datetime import timedelta
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field


class Sla(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: str = Field(min_length=3)
    max_lag: timedelta = Field(gt=timedelta(0))
    delete_within: timedelta = Field(gt=timedelta(0))


def load_slas() -> dict[str, Sla]:
    text = (
        files("llmdata.contracts").joinpath("slas.toml").read_text()
    )
    return {
        origin: Sla.model_validate(values)
        for origin, values in tomllib.loads(text).items()
    }
