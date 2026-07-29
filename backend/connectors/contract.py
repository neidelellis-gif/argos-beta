"""Official lightweight contract for ARGOS portfolio connectors."""

from pathlib import Path
from typing import Protocol, Tuple, runtime_checkable

from backend.models import PortfolioOwner, PortfolioPosition


@runtime_checkable
class PortfolioConnector(Protocol):
    connector_id: str
    institution: str
    owner: PortfolioOwner
    supported_extensions: frozenset[str]

    def recognize(self, path: Path) -> bool:
        """Inspect file structure without parsing its portfolio positions."""
        ...

    def load_positions(self, file_path: Path) -> Tuple[PortfolioPosition, ...]:
        """Parse a recognized file into the universal portfolio model."""
        ...
