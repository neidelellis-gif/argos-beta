"""Quantitative, read-only market intelligence for the JOLIKA portfolio held at Santander."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.market.market_connector import MarketConnector
from backend.market_symbol_resolution import resolve_market_symbol
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_quantitative_analysis import (
    calculate_drawdown,
    calculate_historical_cvar,
    calculate_historical_var,
    calculate_returns,
    calculate_volatility,
)


@dataclass(frozen=True)
class SantanderPositionQuantitativeMetrics:
    """Historical market-risk metrics for one Santander/JOLIKA position."""

    asset_label: str
    identifier: str | None
    identifier_type: str | None
    currency: str | None

    status: str
    provider: str | None

    observation_count: int
    first_date: str | None
    last_date: str | None

    annualized_volatility: float | None
    maximum_drawdown: float | None
    historical_var_95: float | None
    historical_cvar_95: float | None

    attention_level: str
    attention_reasons: tuple[str, ...]

    error: str | None


@dataclass(frozen=True)
class SantanderQuantitativeAssessment:
    """Aggregated quantitative assessment for the Santander/JOLIKA portfolio."""

    level: str
    reasons: tuple[str, ...]
    analyzed_position_count: int
    elevated_position_count: int
    high_attention_position_count: int


@dataclass(frozen=True)
class SantanderQuantitativeIntelligence:
    """Immutable quantitative intelligence for Santander/JOLIKA positions."""

    institution: str
    owner: PortfolioOwner
    lookback_days: int

    position_count: int
    ticker_position_count: int
    analyzed_position_count: int
    unavailable_position_count: int

    positions: tuple[SantanderPositionQuantitativeMetrics, ...]

    assessment: SantanderQuantitativeAssessment
    attention_positions: tuple[SantanderPositionQuantitativeMetrics, ...]
    portfolio_reading: str


def _asset_label(position: PortfolioPosition) -> str:
    return (
        position.asset_name
        or position.identifier
        or "<unnamed asset>"
    )


def _normalized_identifier(
    position: PortfolioPosition,
) -> str | None:
    value = (position.identifier or "").strip().upper()
    return value or None


def _normalized_identifier_type(
    position: PortfolioPosition,
) -> str | None:
    value = (position.identifier_type or "").strip().upper()
    return value or None


def _is_ticker(position: PortfolioPosition) -> bool:
    return _normalized_identifier_type(position) in {
        "TICKER",
        "SYMBOL",
    }


def _position_sort_key(
    position: PortfolioPosition,
) -> tuple:
    return (
        _normalized_identifier(position) or "",
        _asset_label(position),
        position.currency or "",
        position.source_file,
        position.account or "",
    )


def _at_least(
    value: float,
    threshold: float,
    *,
    tolerance: float = 1e-12,
) -> bool:
    """Compare floating-point risk metrics safely at explicit thresholds."""
    return value + tolerance >= threshold


def _risk_attention(
    *,
    annualized_volatility: float | None,
    maximum_drawdown: float | None,
    historical_var_95: float | None,
    historical_cvar_95: float | None,
) -> tuple[str, tuple[str, ...]]:
    """Classify attention from objective historical risk metrics."""

    high_reasons: list[str] = []
    medium_reasons: list[str] = []

    if annualized_volatility is not None:
        if _at_least(annualized_volatility, 0.50):
            high_reasons.append("high_volatility")
        elif _at_least(annualized_volatility, 0.30):
            medium_reasons.append("elevated_volatility")

    if maximum_drawdown is not None:
        drawdown_magnitude = abs(maximum_drawdown)

        if _at_least(drawdown_magnitude, 0.35):
            high_reasons.append("deep_drawdown")
        elif _at_least(drawdown_magnitude, 0.20):
            medium_reasons.append("relevant_drawdown")

    if historical_var_95 is not None:
        if _at_least(historical_var_95, 0.05):
            high_reasons.append("high_var")
        elif _at_least(historical_var_95, 0.03):
            medium_reasons.append("elevated_var")

    if historical_cvar_95 is not None:
        if _at_least(historical_cvar_95, 0.07):
            high_reasons.append("high_cvar")
        elif _at_least(historical_cvar_95, 0.04):
            medium_reasons.append("elevated_cvar")

    if high_reasons:
        return (
            "Alta",
            tuple(dict.fromkeys(high_reasons + medium_reasons)),
        )

    if medium_reasons:
        return (
            "Média",
            tuple(dict.fromkeys(medium_reasons)),
        )

    return ("Baixa", ())


def _unavailable_position(
    position: PortfolioPosition,
    *,
    error: str,
    provider: str | None = None,
) -> SantanderPositionQuantitativeMetrics:
    return SantanderPositionQuantitativeMetrics(
        asset_label=_asset_label(position),
        identifier=_normalized_identifier(position),
        identifier_type=_normalized_identifier_type(position),
        currency=position.currency,
        status="unavailable",
        provider=provider,
        observation_count=0,
        first_date=None,
        last_date=None,
        annualized_volatility=None,
        maximum_drawdown=None,
        historical_var_95=None,
        historical_cvar_95=None,
        attention_level="Indisponível",
        attention_reasons=(),
        error=error,
    )


def _analyze_position(
    position: PortfolioPosition,
    *,
    market_connector: MarketConnector,
    lookback_days: int,
) -> SantanderPositionQuantitativeMetrics:
    identifier = _normalized_identifier(position)
    market_symbol = resolve_market_symbol(position)

    if identifier is None:
        return _unavailable_position(
            position,
            error="market identifier required",
        )

    if market_symbol is None:
        return _unavailable_position(
            position,
            error="market symbol unavailable",
        )

    history = market_connector.get_history(
        market_symbol,
        days=lookback_days,
    )

    if history.status != "ok" or not history.points:
        return _unavailable_position(
            position,
            provider=history.provider,
            error=history.error or "historical market data unavailable",
        )

    prices = tuple(
        point.close
        for point in history.points
    )
    returns = calculate_returns(prices)

    annualized_volatility = calculate_volatility(returns)
    maximum_drawdown = calculate_drawdown(prices)
    historical_var_95 = calculate_historical_var(
        returns,
        confidence_level=0.95,
    )
    historical_cvar_95 = calculate_historical_cvar(
        returns,
        confidence_level=0.95,
    )

    attention_level, attention_reasons = _risk_attention(
        annualized_volatility=annualized_volatility,
        maximum_drawdown=maximum_drawdown,
        historical_var_95=historical_var_95,
        historical_cvar_95=historical_cvar_95,
    )

    return SantanderPositionQuantitativeMetrics(
        asset_label=_asset_label(position),
        identifier=identifier,
        identifier_type=_normalized_identifier_type(position),
        currency=position.currency,
        status="ok",
        provider=history.provider,
        observation_count=len(history.points),
        first_date=history.points[0].date,
        last_date=history.points[-1].date,
        annualized_volatility=annualized_volatility,
        maximum_drawdown=maximum_drawdown,
        historical_var_95=historical_var_95,
        historical_cvar_95=historical_cvar_95,
        attention_level=attention_level,
        attention_reasons=attention_reasons,
        error=None,
    )


def _assessment(
    positions: tuple[SantanderPositionQuantitativeMetrics, ...],
) -> SantanderQuantitativeAssessment:
    analyzed = tuple(
        item
        for item in positions
        if item.status == "ok"
    )

    high = tuple(
        item
        for item in analyzed
        if item.attention_level == "Alta"
    )

    medium = tuple(
        item
        for item in analyzed
        if item.attention_level == "Média"
    )

    reasons = tuple(
        dict.fromkeys(
            reason
            for item in high + medium
            for reason in item.attention_reasons
        )
    )

    if high:
        level = "Alta"
    elif medium:
        level = "Média"
    else:
        level = "Baixa"

    return SantanderQuantitativeAssessment(
        level=level,
        reasons=reasons,
        analyzed_position_count=len(analyzed),
        elevated_position_count=len(medium),
        high_attention_position_count=len(high),
    )


def _attention_sort_key(
    item: SantanderPositionQuantitativeMetrics,
) -> tuple:
    level_rank = {
        "Alta": 0,
        "Média": 1,
        "Baixa": 2,
        "Indisponível": 3,
    }

    return (
        level_rank.get(item.attention_level, 9),
        -(
            item.annualized_volatility
            if item.annualized_volatility is not None
            else -1.0
        ),
        -(
            abs(item.maximum_drawdown)
            if item.maximum_drawdown is not None
            else -1.0
        ),
        item.identifier or "",
        item.asset_label,
    )


def _attention_positions(
    positions: tuple[SantanderPositionQuantitativeMetrics, ...],
) -> tuple[SantanderPositionQuantitativeMetrics, ...]:
    return tuple(
        sorted(
            (
                item
                for item in positions
                if item.status == "ok"
                and item.attention_level in {"Alta", "Média"}
            ),
            key=_attention_sort_key,
        )
    )


def _portfolio_reading(
    assessment: SantanderQuantitativeAssessment,
    *,
    unavailable_position_count: int,
) -> str:
    """Produce a concise executive reading without transaction language."""

    if assessment.analyzed_position_count == 0:
        return (
            "Ainda não há histórico de mercado suficiente para produzir "
            "uma leitura quantitativa da carteira Santander."
        )

    if assessment.level == "Alta":
        reading = (
            "A leitura quantitativa da Santander mostra risco histórico elevado "
            "em pelo menos uma posição e isso merece atenção prioritária."
        )
    elif assessment.level == "Média":
        reading = (
            "A leitura quantitativa da Santander mostra alguns pontos de risco "
            "histórico acima do nível mais confortável e que merecem acompanhamento."
        )
    else:
        reading = (
            "A leitura quantitativa da Santander não mostra, neste momento, "
            "nenhum ponto dominante de risco histórico entre as posições analisadas."
        )

    if unavailable_position_count:
        reading += (
            f" Há {unavailable_position_count} posição(ões) sem histórico "
            "quantitativo disponível."
        )

    return reading


def build_santander_quantitative_intelligence(
    positions: Iterable[PortfolioPosition],
    *,
    market_connector: MarketConnector,
    lookback_days: int = 365,
) -> SantanderQuantitativeIntelligence:
    """Build historical market-risk intelligence for Santander/JOLIKA positions."""

    if (
        isinstance(lookback_days, bool)
        or not isinstance(lookback_days, int)
        or lookback_days <= 0
    ):
        raise ValueError(
            "lookback_days must be a positive integer"
        )

    canonical_positions = tuple(positions)

    for position in canonical_positions:
        if position.institution != "Santander":
            raise ValueError(
                "all positions must belong to Santander"
            )

        if position.owner is not PortfolioOwner.JOLIKA:
            raise ValueError(
                "all positions must belong to JOLIKA"
            )

    ordered_positions = tuple(
        sorted(
            canonical_positions,
            key=_position_sort_key,
        )
    )

    quantitative_positions = tuple(
        _analyze_position(
            position,
            market_connector=market_connector,
            lookback_days=lookback_days,
        )
        for position in ordered_positions
    )

    ticker_position_count = sum(
        resolve_market_symbol(position) is not None
        for position in ordered_positions
    )

    analyzed_position_count = sum(
        item.status == "ok"
        for item in quantitative_positions
    )

    unavailable_position_count = (
        len(ordered_positions)
        - analyzed_position_count
    )

    assessment = _assessment(
        quantitative_positions
    )

    return SantanderQuantitativeIntelligence(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        lookback_days=lookback_days,
        position_count=len(ordered_positions),
        ticker_position_count=ticker_position_count,
        analyzed_position_count=analyzed_position_count,
        unavailable_position_count=unavailable_position_count,
        positions=quantitative_positions,
        assessment=assessment,
        attention_positions=_attention_positions(
            quantitative_positions
        ),
        portfolio_reading=_portfolio_reading(
            assessment,
            unavailable_position_count=unavailable_position_count,
        ),
    )
