"""Parse pasted portfolio text into canonical ARGOS portfolio positions."""

from __future__ import annotations

import csv
import io
import unicodedata
from decimal import Decimal

from backend.connectors.io import parse_decimal
from backend.models import PortfolioOwner, PortfolioPosition


_HEADER_ALIASES = {
    "institution": {"INSTITUICAO", "INSTITUTION", "BANCO"},
    "asset_name": {"ATIVO", "ASSET", "ASSET NAME", "NOME DO ATIVO"},
    "identifier": {"IDENTIFICADOR", "IDENTIFIER", "TICKER", "ISIN", "CODIGO"},
    "market_value": {
        "VALOR",
        "VALUE",
        "MARKET VALUE",
        "VALOR DE MERCADO",
        "VALOR DO MERCADO",
        "SALDO",
    },
    "currency": {"MOEDA", "CURRENCY"},
    "asset_class": {"CLASSE", "CLASS", "ASSET CLASS", "CATEGORIA"},
    "account": {"CONTA", "ACCOUNT", "ACCOUNT NUMBER", "NUMERO DE CONTA"},
}


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )
        .upper()
        .split()
    )


def _delimiter(text: str) -> str:
    first_line = next(
        (line for line in text.splitlines() if line.strip()),
        "",
    )

    if "\t" in first_line:
        return "\t"
    if ";" in first_line:
        return ";"
    return ","


def _header_mapping(header: list[str]) -> dict[str, int]:
    normalized = [_normalize(value) for value in header]
    mapping: dict[str, int] = {}

    for field, aliases in _HEADER_ALIASES.items():
        for index, value in enumerate(normalized):
            if value in aliases:
                mapping[field] = index
                break

    required = {"institution", "asset_name", "market_value", "currency"}
    missing = required - set(mapping)

    if missing:
        labels = {
            "institution": "instituição",
            "asset_name": "ativo",
            "market_value": "valor",
            "currency": "moeda",
        }
        missing_text = ", ".join(
            labels[field] for field in sorted(missing)
        )
        raise ValueError(
            f"Não consegui identificar estas colunas no texto colado: {missing_text}."
        )

    return mapping


def parse_pasted_portfolio(
    text: str,
    *,
    owner: PortfolioOwner,
) -> tuple[PortfolioPosition, ...]:
    """Convert pasted tabular text into canonical portfolio positions."""

    if owner is not PortfolioOwner.JOLIKA:
        raise ValueError(
            "Nesta etapa, a leitura de texto colado aceita apenas a carteira JOLIKA."
        )

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Cole uma carteira antes de continuar.")

    reader = csv.reader(
        io.StringIO(text.strip()),
        delimiter=_delimiter(text),
    )
    rows = [
        [str(cell).strip() for cell in row]
        for row in reader
        if any(str(cell).strip() for cell in row)
    ]

    if len(rows) < 2:
        raise ValueError(
            "O texto colado precisa ter uma linha de cabeçalho e ao menos uma posição."
        )

    mapping = _header_mapping(rows[0])
    positions: list[PortfolioPosition] = []

    for row_number, row in enumerate(rows[1:], start=2):
        def value(field: str) -> str | None:
            index = mapping.get(field)
            if index is None or index >= len(row):
                return None
            result = row[index].strip()
            return result or None

        institution = value("institution")
        asset_name = value("asset_name")
        currency = value("currency")
        market_value = parse_decimal(value("market_value"))

        if not institution or not asset_name or not currency:
            continue

        if market_value is None:
            raise ValueError(
                f"Não consegui ler o valor da posição na linha {row_number}."
            )

        identifier = value("identifier")

        positions.append(
            PortfolioPosition(
                institution=institution,
                owner=owner,
                account=value("account"),
                asset_class=value("asset_class"),
                asset_subclass=None,
                asset_name=asset_name,
                identifier=identifier,
                identifier_type=None,
                quantity=None,
                unit_price=None,
                market_value=Decimal(market_value),
                currency=currency.upper(),
                portfolio_weight=None,
                reference_date=None,
                source_file="texto-colado",
            )
        )

    if not positions:
        raise ValueError(
            "Não encontrei nenhuma posição válida no texto colado."
        )

    return tuple(positions)
