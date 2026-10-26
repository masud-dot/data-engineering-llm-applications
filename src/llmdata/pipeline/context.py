"""What every stage callable receives."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from llmdata.config import Settings


@dataclass
class Context:
    run_id: str
    pipeline: str
    stage: str
    settings: Settings
    params: dict[str, Any] = field(default_factory=dict)
    conf: dict[str, Any] = field(default_factory=dict)
    try_number: int = 1

    def pause_point(self) -> None:
        """Fault injection for the recovery spike (S-5)."""
        if self.conf.get("pause_at") != self.stage:
            return
        if self.try_number != 1:
            return
        marker = self.settings.data_dir / f".pause-{self.run_id}"
        marker.write_text(self.stage)
        print(f"pausing in {self.stage}", flush=True)
        time.sleep(int(self.conf.get("pause_s", 60)))
