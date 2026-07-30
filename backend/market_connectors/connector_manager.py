"""Registration, selection and execution of market connectors."""

from collections.abc import Callable
from datetime import datetime, timezone

from backend.important_facts import MarketFact
from backend.market_agenda import MarketAgendaEvent
from backend.market_connectors.base import MarketConnector
from backend.market_connectors.connector_cache import ConnectorCache, ConnectorCacheEntry


class ConnectorUnavailableError(RuntimeError):
    """Raised when the selected market connector cannot be used."""


class ConnectorManager:
    """Isolate market-data providers from the analytical application."""

    def __init__(
        self,
        cache: ConnectorCache | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connectors: dict[str, MarketConnector] = {}
        self._active: str | None = None
        self._cache = cache or ConnectorCache()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def active_connector(self) -> str | None:
        return self._active

    def register(self, name: str, connector: MarketConnector, *, active: bool = False) -> None:
        normalized = name.strip().upper()
        if not normalized:
            raise ValueError("O nome do conector de mercado é obrigatório.")
        if normalized in self._connectors:
            raise ValueError(f"Conector de mercado já registrado: {normalized}.")
        self._connectors[normalized] = connector
        if active or self._active is None:
            self._active = normalized
            self._cache.clear()

    def select(self, name: str) -> None:
        normalized = name.strip().upper()
        if normalized not in self._connectors:
            raise KeyError(f"Conector de mercado não registrado: {normalized}.")
        if normalized != self._active:
            self._active = normalized
            self._cache.clear()

    def reload(self) -> ConnectorCacheEntry:
        connector = self._connector()
        if not connector.is_available():
            raise ConnectorUnavailableError(f"Conector de mercado indisponível: {self._active}.")
        facts = tuple(connector.load_facts())
        agenda = tuple(connector.load_agenda())
        metadata = connector.metadata()
        entry = ConnectorCacheEntry(
            last_reload=self._clock(), facts=facts, agenda=agenda,
            source=str(metadata.get("source", self._active)),
        )
        self._cache.replace(entry)
        return entry

    def load_facts(self) -> tuple[MarketFact, ...]:
        return self._current().facts

    def load_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        return self._current().agenda

    def status(self) -> dict[str, object]:
        connector = self._connector()
        entry = self._cache.entry
        return {
            "connector": self._active,
            "available": connector.is_available(),
            "last_reload": entry.last_reload.isoformat() if entry else None,
            "facts": len(entry.facts) if entry else 0,
            "agenda": len(entry.agenda) if entry else 0,
        }

    def _current(self) -> ConnectorCacheEntry:
        return self._cache.entry or self.reload()

    def _connector(self) -> MarketConnector:
        if self._active is None:
            raise ConnectorUnavailableError("Nenhum conector de mercado está ativo.")
        return self._connectors[self._active]
