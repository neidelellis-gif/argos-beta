"""Official interface implemented by every market-data provider."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from backend.important_facts import MarketFact
from backend.market_agenda import MarketAgendaEvent


class MarketConnector(ABC):
    """Acquire data and expose only ARGOS canonical market models."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the provider can currently be used."""

    @abstractmethod
    def load_facts(self) -> tuple[MarketFact, ...]:
        """Load canonical market facts."""

    @abstractmethod
    def load_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        """Load canonical market-agenda events."""

    @abstractmethod
    def metadata(self) -> Mapping[str, object]:
        """Describe the provider without exposing provider payloads."""
