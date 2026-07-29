"""Connector for TipRanks portfolio CSV exports."""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.models import PortfolioOwner, PortfolioPosition


def _normalize_header(value):
    return " ".join(
        str(value or "").lstrip("\ufeff").strip().lower()
        .replace(".", " ").replace("_", " ").replace("-", " ").split()
    )


def _parse_number(value):
    text = str(value or "").strip()
    if not text or text == "-":
        return None

    negative = text.startswith("(") and text.endswith(")")
    normalized = "".join(character for character in text if character not in "$,%() ")
    try:
        number = Decimal(normalized)
    except InvalidOperation:
        return None
    return -number if negative else number


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
        institution=position["institution"],
        owner=PortfolioOwner.JOLIKA,
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


def load_positions(file_path):
    path = Path(file_path)
    if path.suffix.lower() != ".csv":
        raise ValueError("O arquivo TipRanks deve estar em CSV.")
    if not path.exists():
        raise ValueError(f"Arquivo TipRanks não encontrado: {path.name}")

    return [
        _to_portfolio_position(position, path.name)
        for position in _read_positions(path)
    ]
