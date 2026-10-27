"""Near-duplicate detection with MinHash signatures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

# region: minhash
K = 5  # words per shingle
SIZE = 64  # hash functions in a signature
SEEDS = np.random.default_rng(2027).integers(
    1, 2**63, size=SIZE, dtype=np.uint64
) | np.uint64(1)


def shingles(text: str) -> np.ndarray:
    """Every run of K words, hashed to a 64-bit integer."""
    words = text.lower().split()
    grams = {
        " ".join(words[i : i + K])
        for i in range(max(1, len(words) - K + 1))
    }
    return np.array(
        [
            int.from_bytes(
                hashlib.blake2b(g.encode(), digest_size=8).digest()
            )
            for g in grams
        ],
        dtype=np.uint64,
    )


def signature(text: str) -> list[int]:
    """For each hash function, the smallest hash of any shingle."""
    hashes = (SEEDS[:, None] * shingles(text)) >> np.uint64(32)
    return [int(v) for v in hashes.min(axis=1)]


def similarity(a: list[int], b: list[int]) -> float:
    """The share of positions that agree: an estimate of Jaccard."""
    return sum(x == y for x, y in zip(a, b, strict=True)) / SIZE


# endregion


# region: near-duplicates
@dataclass(frozen=True)
class Doc:
    key: str
    version: str
    scope: str  # origin, region and roles; copies never cross it
    sig: list[int]


def duplicates(
    new: list[Doc], known: list[Doc], threshold: float
) -> dict[str, Doc]:
    """Map each new document that copies an earlier one to it."""
    seen: dict[str, list[Doc]] = {}
    for doc in known:
        seen.setdefault(doc.scope, []).append(doc)
    found: dict[str, Doc] = {}
    for doc in sorted(new, key=lambda d: d.key):
        peers = seen.setdefault(doc.scope, [])
        twin = next(
            (
                p
                for p in peers
                if similarity(p.sig, doc.sig) >= threshold
            ),
            None,
        )
        if twin is None:
            peers.append(doc)
        else:
            found[doc.key] = twin
    return found


# endregion
