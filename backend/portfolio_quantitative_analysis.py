"""Core quantitative calculations for ARGOS portfolio analysis."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable


def _validated_prices(prices: Iterable[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in prices)

    if any(value <= 0 for value in values):
        raise ValueError("prices must be positive")

    return values


def calculate_returns(
    prices: Iterable[float],
) -> tuple[float, ...]:
    """Calculate simple period-over-period returns from a price series."""

    values = _validated_prices(prices)

    if len(values) < 2:
        return ()

    return tuple(
        (current / previous) - 1.0
        for previous, current in zip(values, values[1:])
    )


def calculate_volatility(
    returns: Iterable[float],
    *,
    periods_per_year: int = 252,
) -> float | None:
    """Calculate annualized sample volatility from periodic returns."""

    values = tuple(float(value) for value in returns)

    if len(values) < 2:
        return None

    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, int)
        or periods_per_year <= 0
    ):
        raise ValueError("periods_per_year must be a positive integer")

    return statistics.stdev(values) * math.sqrt(periods_per_year)


def calculate_drawdown(
    prices: Iterable[float],
) -> float | None:
    """Calculate maximum peak-to-trough drawdown from a price series."""

    values = _validated_prices(prices)

    if not values:
        return None

    peak = values[0]
    maximum_drawdown = 0.0

    for value in values:
        if value > peak:
            peak = value

        drawdown = (value / peak) - 1.0

        if drawdown < maximum_drawdown:
            maximum_drawdown = drawdown

    return maximum_drawdown


def _validate_confidence_level(confidence_level: float) -> float:
    value = float(confidence_level)

    if not 0.0 < value < 1.0:
        raise ValueError(
            "confidence_level must be between 0 and 1"
        )

    return value


def _historical_tail(
    returns: Iterable[float],
    *,
    confidence_level: float,
) -> tuple[float, ...]:
    values = tuple(float(value) for value in returns)

    if not values:
        return ()

    confidence = _validate_confidence_level(confidence_level)
    ordered = tuple(sorted(values))

    tail_fraction = len(ordered) * (1.0 - confidence)

    tail_count = max(
        1,
        math.ceil(tail_fraction - 1e-12),
    )

    return ordered[:tail_count]


def calculate_historical_var(
    returns: Iterable[float],
    *,
    confidence_level: float = 0.95,
) -> float | None:
    """Calculate historical Value at Risk as a positive loss magnitude."""

    tail = _historical_tail(
        returns,
        confidence_level=confidence_level,
    )

    if not tail:
        return None

    threshold_return = tail[-1]

    return max(0.0, -threshold_return)


def calculate_historical_cvar(
    returns: Iterable[float],
    *,
    confidence_level: float = 0.95,
) -> float | None:
    """Calculate historical Conditional Value at Risk as average tail loss."""

    tail = _historical_tail(
        returns,
        confidence_level=confidence_level,
    )

    if not tail:
        return None

    average_tail_return = sum(tail) / len(tail)

    return max(0.0, -average_tail_return)
