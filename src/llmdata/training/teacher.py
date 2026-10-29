"""A stand-in teacher that summarises claim notes without a model."""

from __future__ import annotations

import re
from collections import Counter


# region: teacher
class FakeTeacher:
    """Deterministic and offline, like Chapter 9's fake embedder."""

    name, revision = "fake-teacher", "1"

    @property
    def id(self) -> str:
        return f"{self.name}@{self.revision}"

    def summarise(self, note: str) -> str:
        """First words reported, then the most frequent others."""
        said = note.split(" reported ", 1)[-1].lower()
        words = re.findall(r"[a-z]+", said)
        if not words:
            return ""
        common = Counter(words[3:]).most_common(3)
        summary = f"Reported {' '.join(words[:3])}."
        if common:
            also = ", ".join(word for word, _ in common)
            summary += f" Also mentions {also}."
        return summary


def get(name: str) -> FakeTeacher:
    """Only the stand-in is built in; a real model plugs in here."""
    if name != "fake":
        raise ValueError(f"no teacher {name!r} is configured")
    return FakeTeacher()


# endregion
