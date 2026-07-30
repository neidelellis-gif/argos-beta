"""Small in-memory cache for the active market connector."""

from dataclasses import dataclass
from datetime import datetime

from backend.important_facts import MarketFact
from backend.market_agenda import MarketAgendaEvent


@dataclass(frozen=True)
class ConnectorCacheEntry:
    last_reload: datetime
    facts: tuple[MarketFact, ...]
    agenda: tuple[MarketAgendaEvent, ...]
    source: str


class ConnectorCache:
    """Keep the last successful, process-local connector load."""

    def __init__(self) -> None:
        self._entry: ConnectorCacheEntry | None = None

    @property
    def entry(self) -> ConnectorCacheEntry | None:
        return self._entry

    def replace(self, entry: ConnectorCacheEntry) -> None:
        self._entry = entry

    def clear(self) -> None:
        self._entry = None
