"""Deterministic hashed bag-of-words vectors for tests."""

from __future__ import annotations

import argparse
import hashlib
import math
import re

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float32]
RECORDED_SAMPLE_HASH = (
    "5ef622a5d6a7fe40c5d09d3b85323de94c28c6ea79def8ebfb7b5ab74e929d95"
)
SAMPLES = [
    "Escape of water from a fixed heating system is covered.",
    "Storm damage to fences and gates is excluded.",
    "Claims notified after 30 days need a written reason.",
]


class FakeEmbedder:
    name = "fake-hash-384"
    revision = "1"  # raise when vector() changes
    languages: frozenset[str] = (
        frozenset()
    )  # any: it only hashes words

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def vector(self, text: str) -> Vector:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            vec[index] += 1.0 if digest[4] & 1 else -1.0
        squares = sum(int(v) ** 2 for v in vec)
        if squares:
            vec /= np.float32(math.sqrt(squares))
        return vec

    def embed(self, texts: list[str]) -> list[Vector]:
        return [self.vector(t) for t in texts]


def sample_hash() -> str:
    digest = hashlib.sha256()
    for vec in FakeEmbedder().embed(SAMPLES):
        digest.update(vec.tobytes())
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llmdata.embed.fake")
    parser.add_argument("--hash", action="store_true", required=True)
    parser.parse_args(argv)
    print(sample_hash())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
