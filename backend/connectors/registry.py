"""Central registry for portfolio connectors."""

from pathlib import Path
from typing import Dict, Iterable, Tuple

from backend.connectors.contract import PortfolioConnector
from backend.connectors.errors import DuplicateConnectorIdError


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: Dict[str, PortfolioConnector] = {}
        self._active_ids = set()

    def register(self, connector: PortfolioConnector, *, active: bool = True) -> None:
        if connector.connector_id in self._connectors:
            raise DuplicateConnectorIdError(
                f"Connector ID já registrado: {connector.connector_id}"
            )
        self._connectors[connector.connector_id] = connector
        if active:
            self._active_ids.add(connector.connector_id)

    def all(self) -> Tuple[PortfolioConnector, ...]:
        return tuple(self._connectors.values())

    def active(self) -> Tuple[PortfolioConnector, ...]:
        return tuple(
            connector for connector_id, connector in self._connectors.items()
            if connector_id in self._active_ids
        )

    def for_extension(
        self, path_or_extension: Path | str, *, active_only: bool = False
    ) -> Tuple[PortfolioConnector, ...]:
        value = str(path_or_extension)
        extension = (
            value.lower() if value.startswith(".") else Path(value).suffix.lower()
        )
        connectors: Iterable[PortfolioConnector] = (
            self.active() if active_only else self.all()
        )
        return tuple(
            connector for connector in connectors
            if extension in connector.supported_extensions
        )
