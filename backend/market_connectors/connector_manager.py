"""Registration, selection and execution of market connectors."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

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
        self._preferred: str | None = None
        self._fallback: str | None = None
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
            self._preferred = normalized
            self._cache.clear()

    def select(self, name: str) -> None:
        normalized = name.strip().upper()
        if normalized not in self._connectors:
            raise KeyError(f"Conector de mercado não registrado: {normalized}.")
        if normalized != self._active:
            self._active = normalized
            self._preferred = normalized
            self._cache.clear()

    def configure_fallback(self, preferred: str, fallback: str) -> None:
        """Prefer one provider and transparently use another when it fails."""
        preferred_name, fallback_name = preferred.strip().upper(), fallback.strip().upper()
        if preferred_name not in self._connectors or fallback_name not in self._connectors:
            raise KeyError("Conector preferencial ou fallback não registrado.")
        self._preferred, self._fallback, self._active = preferred_name, fallback_name, preferred_name
        self._cache.clear()

    def reload(self) -> ConnectorCacheEntry:
        target = self._preferred or self._active
        error: Exception | None = None
        try:
            facts, agenda, metadata = self._load(target)
            selected = cast(str, target)
        except Exception as exc:
            error = exc
            if self._fallback is None or target == self._fallback:
                raise
            facts, agenda, metadata = self._load(self._fallback)
            selected = cast(str, self._fallback)
        self._active = selected
        entry = ConnectorCacheEntry(
            last_reload=self._clock(), facts=facts, agenda=agenda,
            source=str(metadata.get("source", selected)), connector=selected,
            reload_succeeded=error is None, error=str(error) if error else None,
        )
        self._cache.replace(entry)
        return entry

    def load_facts(self) -> tuple[MarketFact, ...]:
        return self._current().facts

    def load_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        return self._current().agenda

    def status(self) -> dict[str, object]:
        entry = self._cache.entry
        return {
            "connector": self._active,
            "active_connector": self._active,
            "available": self._connector().is_available(),
            "fallback_available": self._fallback is not None,
            "last_reload": entry.last_reload.isoformat() if entry else None,
            "facts": len(entry.facts) if entry else 0,
            "agenda": len(entry.agenda) if entry else 0,
            "source": "REMOTE" if self._active == self._preferred and self._fallback else "LOCAL",
            "last_reload_success": entry.reload_succeeded if entry else None,
            "last_error": entry.error if entry else None,
        }

    def _load(self, name: str | None):
        if name is None:
            raise ConnectorUnavailableError("Nenhum conector de mercado está ativo.")
        connector = self._connectors[name]
        if not connector.is_available():
            raise ConnectorUnavailableError(f"Conector de mercado indisponível: {name}.")
        return tuple(connector.load_facts()), tuple(connector.load_agenda()), connector.metadata()

    def _current(self) -> ConnectorCacheEntry:
        return self._cache.entry or self.reload()

    def _connector(self) -> MarketConnector:
        if self._active is None:
            raise ConnectorUnavailableError("Nenhum conector de mercado está ativo.")
        return self._connectors[self._active]
