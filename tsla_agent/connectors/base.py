from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from tsla_agent.config import AgentConfig
from tsla_agent.models import Event, PricePoint


@dataclass
class CollectionResult:
    events: list[Event] = field(default_factory=list)
    prices: list[PricePoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def extend(self, other: "CollectionResult") -> None:
        self.events.extend(other.events)
        self.prices.extend(other.prices)
        self.warnings.extend(other.warnings)


class Connector(Protocol):
    name: str

    def collect(self, config: AgentConfig) -> CollectionResult:
        ...
