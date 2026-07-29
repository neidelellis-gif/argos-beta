"""Connector for TipRanks portfolio CSV exports."""

import csv
from pathlib import Path

from backend.models import PortfolioOwner, PortfolioPosition
from backend.connectors.errors import (
    ConnectorFileNotFoundError,
    EmptyPortfolioError,
    UnsupportedExtensionError,
)
from backend.connectors.io import parse_decimal

connector_id = "tipranks"
institution = "TipRanks"
owner = PortfolioOwner.JOLIKA
supported_extensions = frozenset({".csv"})


def _normalize_header(value):
    return " ".join(
        str(value or "").lstrip("\ufeff").strip().lower()
        .replace(".", " ").replace("_", " ").replace("-", " ").split()
    )


def _parse_number(value):
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    return parse_decimal(text.replace(" ", ""))


def _parse_text(value):
    text = str(value or "").strip()
    return None if not text or text.upper() == "N/A" or text == "-" else text


def _read_positions(path):
    """Read the existing TipRanks fields without enriching their values."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            headers = next(reader)
        except StopIteration:
            return []

        indexes = {
            _normalize_header(header): index
            for index, header in enumerate(headers)
        }

        def value_for(row, *names):
            for name in names:
                index = indexes.get(name)
                if index is not None and index < len(row):
                    return row[index]
            return ""

        positions = []
        for row in reader:
            if not value_for(row, "ticker", "symbol", "stock"):
                continue
            positions.append({
                "institution": "TipRanks",
                "ticker": _parse_text(
                    value_for(row, "ticker", "symbol", "stock")
                ),
                "name": _parse_text(
                    value_for(row, "name", "company", "company name")
                ),
                "shares": _parse_number(
                    value_for(row, "shares", "quantity", "no of shares")
                ),
                "price": _parse_number(value_for(row, "price")),
                "holding_value": _parse_number(
                    value_for(row, "holding value", "market value")
                ),
            })
        return positions


def _to_portfolio_position(position, source_file):
    """Convert one parsed TipRanks position to the universal portfolio model."""
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=position.get("name"),
        identifier=position.get("ticker"),
        identifier_type="Ticker" if position.get("ticker") is not None else None,
        quantity=position.get("shares"),
        unit_price=position.get("price"),
        market_value=position.get("holding_value"),
        currency=None,
        portfolio_weight=None,
        reference_date=None,
        source_file=source_file,
    )


def load_positions(file_path: Path) -> tuple[PortfolioPosition, ...]:
    path = Path(file_path)
    if path.suffix.lower() != ".csv":
        raise UnsupportedExtensionError("O arquivo TipRanks deve estar em CSV.")
    if not path.exists():
        raise ConnectorFileNotFoundError(
            f"Arquivo TipRanks não encontrado: {path.name}"
        )

    positions = tuple(
        _to_portfolio_position(position, path.name)
        for position in _read_positions(path)
    )
    if not positions:
        raise EmptyPortfolioError("Nenhuma posição TipRanks foi encontrada no arquivo.")
    return positions


def recognize(path: Path) -> bool:
    path = Path(path)
    if path.suffix.lower() not in supported_extensions or not path.exists():
        return False
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            headers = next(csv.reader(file), [])
    except OSError:
        return False
    normalized = {_normalize_header(header) for header in headers}
    return bool(normalized & {"ticker", "symbol", "stock"}) and bool(
        normalized & {"shares", "quantity", "no of shares"}
    )
