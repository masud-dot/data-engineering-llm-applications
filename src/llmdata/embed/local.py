"""Local CPU embedding model (install with the 'local' extra)."""

from __future__ import annotations

import argparse
import os
from typing import Any

import numpy as np

from llmdata.config import settings
from llmdata.embed.fake import SAMPLES, Vector

MODEL = "BAAI/bge-small-en-v1.5"


class LocalEmbedder:
    name = MODEL
    dim = 384

    def __init__(self, threads: int = 2) -> None:
        from fastembed import TextEmbedding

        offline = os.environ.get("HF_HUB_OFFLINE") == "1"
        options: dict[str, Any] = {
            "cache_dir": str(settings().model_dir),
            "threads": threads,
        }
        if offline:
            options["local_files_only"] = True
        self.model = TextEmbedding(MODEL, **options)

    def embed(self, texts: list[str]) -> list[Vector]:
        return [
            np.asarray(v, dtype=np.float32)
            for v in self.model.embed(texts, batch_size=32)
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.embed.local")
    parser.add_argument("action", choices=["warm-cache", "check"])
    args = parser.parse_args(argv)
    vectors = LocalEmbedder().embed(SAMPLES)
    dims = {len(v) for v in vectors}
    print(
        f"{args.action}: {MODEL} dims={sorted(dims)}"
        f" offline={os.environ.get('HF_HUB_OFFLINE') == '1'}"
    )
    return 0 if dims == {LocalEmbedder.dim} else 1


if __name__ == "__main__":
    raise SystemExit(main())
