"""Deterministic post-connector economic classification for JOLIKA positions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
import re
from types import MappingProxyType
import unicodedata

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


_EXACT_IDENTIFIERS = MappingProxyType({
    "GLD": EconomicAssetClass.GOLD_AND_COMMODITIES,
    "ARKB": EconomicAssetClass.CRYPTOASSETS,
    "ETHB": EconomicAssetClass.CRYPTOASSETS,
    "ARKQ": EconomicAssetClass.EQUITY_ETFS,
    "JEPI": EconomicAssetClass.EQUITY_ETFS,
    "SMH": EconomicAssetClass.EQUITY_ETFS,
})

_EXACT_NAMES = MappingProxyType({
    "SPDR GOLD TRUST": EconomicAssetClass.GOLD_AND_COMMODITIES,
    "ISHARES BITCOIN TRUST ETF": EconomicAssetClass.CRYPTOASSETS,
    "BNP PARIBAS T-IDN CO1 08/14/2026": EconomicAssetClass.FIXED_INCOME,
})

_EQUITY_EXPOSURE_TERMS = (
    "ACAO",
    "ACOES",
    "EQUITY",
    "MSCI",
    "NASDAQ",
    "RUSSELL",
    "S&P 500",
    "SEMICONDUCTOR",
)


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(character for character in text if not unicodedata.combining(character))
        .upper()
        .split()
    )


def _from_name(position: PortfolioPosition) -> EconomicAssetClass | None:
    name = _normalize(position.asset_name)
    if name in _EXACT_NAMES:
        return _EXACT_NAMES[name]
    if "SPDR GOLD TRUST" in name or "SPDR GOLD SHARES" in name:
        return EconomicAssetClass.GOLD_AND_COMMODITIES
    if "BITCOIN" in name or "ETHEREUM" in name:
        return EconomicAssetClass.CRYPTOASSETS
    return None


def _from_instrument_pattern(position: PortfolioPosition) -> EconomicAssetClass | None:
    name = _normalize(position.asset_name)
    subclass = _normalize(position.asset_subclass)
    evidence = f"{name} {subclass}".strip()

    if "ETF" in evidence and any(term in evidence for term in _EQUITY_EXPOSURE_TERMS):
        return EconomicAssetClass.EQUITY_ETFS
    if any(term in evidence for term in ("GOLD", "OURO", "COMMODITY", "COMMODITIES")):
        return EconomicAssetClass.GOLD_AND_COMMODITIES
    if re.search(r"\b(BOND|NOTE|NOTA|DEBENTURE|TITULO)\b", evidence):
        return EconomicAssetClass.FIXED_INCOME
    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", evidence):
        return EconomicAssetClass.FIXED_INCOME
    return None


def _from_original_class(position: PortfolioPosition) -> EconomicAssetClass | None:
    original = _normalize(position.asset_class)
    if original == "CAIXA":
        return EconomicAssetClass.CASH
    if original == "RENDA FIXA":
        return EconomicAssetClass.FIXED_INCOME
    if original in {"ACAO", "ACOES"}:
        return EconomicAssetClass.EQUITIES
    if original in {"FUNDO", "FUNDOS", "ETF/FUNDO"}:
        return EconomicAssetClass.FUNDS_STRATEGIES
    if original in {"ALTERNATIVO", "ALTERNATIVOS"}:
        return EconomicAssetClass.ALTERNATIVES_PRIVATE_MARKETS
    return None


def classify_jolika_position(position: PortfolioPosition) -> PortfolioPosition:
    """Return an enriched copy of one JOLIKA position without mutating its source."""
    if position.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("JOLIKA economic classification rejects non-JOLIKA positions")

    identifier = _normalize(position.identifier)
    classification = (
        _EXACT_IDENTIFIERS.get(identifier)
        or _from_name(position)
        or _from_instrument_pattern(position)
        or _from_original_class(position)
    )
    return replace(position, economic_asset_class=classification)


def classify_jolika_positions(
    positions: Iterable[PortfolioPosition],
) -> tuple[PortfolioPosition, ...]:
    """Classify an exclusively JOLIKA batch, rejecting mixed-owner input."""
    batch = tuple(positions)
    owners = {position.owner for position in batch}
    if owners - {PortfolioOwner.JOLIKA}:
        raise ValueError("JOLIKA economic classification rejects mixed or non-JOLIKA batches")
    return tuple(classify_jolika_position(position) for position in batch)
