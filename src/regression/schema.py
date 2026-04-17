from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GroupKey:
    scenario: str
    mode: str
    phase: str

    def to_string(self) -> str:
        return f"{self.scenario}|{self.mode}|{self.phase}"

    @staticmethod
    def from_row(row: dict[str, Any]) -> "GroupKey":
        return GroupKey(
            scenario=str(row.get("scenario", "unknown")),
            mode=str(row.get("mode", "unknown")),
            phase=str(row.get("phase", "unknown")),
        )


@dataclass(frozen=True)
class DiffMetric:
    baseline: float | None
    current: float | None
    abs_delta: float | None
    pct_delta: float | None

