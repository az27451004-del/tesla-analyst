from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYMBOL = "TSLA"
TESLA_CIK = "0001318605"

CIK_BY_SYMBOL = {
    "TSLA": TESLA_CIK,
}


@dataclass(frozen=True)
class AgentConfig:
    symbol: str = DEFAULT_SYMBOL
    data_dir: Path = Path("data")
    report_dir: Path = Path("reports")
    max_events: int = 30
    forecast_horizons: tuple[int, ...] = (1, 5, 20)

    @property
    def normalized_symbol(self) -> str:
        return self.symbol.upper().strip()
