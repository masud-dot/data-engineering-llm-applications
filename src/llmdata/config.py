"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOCAL = "postgresql://llmdata@localhost:55432/"


@dataclass(frozen=True)
class Settings:
    dsn: str
    source_dsn: str
    data_dir: Path
    pipelines_dir: Path
    model_dir: Path


def settings() -> Settings:
    env = os.environ.get
    return Settings(
        dsn=env("LLMDATA_DSN", LOCAL + "llmdata"),
        source_dsn=env("LLMDATA_SOURCE_DSN", LOCAL + "source"),
        data_dir=Path(env("LLMDATA_DATA_DIR", "data")),
        pipelines_dir=Path(env("LLMDATA_PIPELINES_DIR", "pipelines")),
        model_dir=Path(env("LLMDATA_MODEL_DIR", "models")),
    )
