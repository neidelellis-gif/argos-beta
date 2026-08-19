from __future__ import annotations

import math

import pytest

from backend.portfolio_quantitative_analysis import (
    calculate_drawdown,
    calculate_returns,
    calculate_volatility,
)


def test_calculates_simple_daily_returns():
    prices = [100.0, 102.0, 101.0, 104.0]

    returns = calculate_returns(prices)

    assert returns == pytest.approx([
        0.02,
        -0.00980392156862745,
        0.0297029702970297,
    ])


def test_calculates_annualized_volatility_from_daily_returns():
    returns = [
        0.01,
        -0.02,
        0.015,
        -0.005,
        0.012,
    ]

    volatility = calculate_volatility(
        returns,
        periods_per_year=252,
    )

    expected = (
        sum(
            (value - sum(returns) / len(returns)) ** 2
            for value in returns
        )
        / (len(returns) - 1)
    ) ** 0.5 * math.sqrt(252)

    assert volatility == pytest.approx(expected)


def test_calculates_maximum_drawdown():
    prices = [
        100.0,
        110.0,
        105.0,
        90.0,
        95.0,
        120.0,
    ]

    drawdown = calculate_drawdown(prices)

    assert drawdown == pytest.approx(
        (90.0 / 110.0) - 1.0
    )


def test_returns_empty_when_fewer_than_two_prices():
    assert calculate_returns([]) == ()
    assert calculate_returns([100.0]) == ()


def test_volatility_is_unavailable_with_insufficient_returns():
    assert calculate_volatility([]) is None
    assert calculate_volatility([0.01]) is None


def test_drawdown_is_unavailable_without_prices():
    assert calculate_drawdown([]) is None


def test_rejects_non_positive_prices():
    with pytest.raises(
        ValueError,
        match="prices must be positive",
    ):
        calculate_returns([100.0, 0.0, 102.0])

    with pytest.raises(
        ValueError,
        match="prices must be positive",
    ):
        calculate_drawdown([100.0, -1.0, 102.0])


from backend.portfolio_quantitative_analysis import (
    calculate_historical_cvar,
    calculate_historical_var,
)


def test_calculates_historical_var_at_95_percent():
    returns = [
        -0.10,
        -0.05,
        -0.03,
        -0.02,
        -0.01,
        0.00,
        0.01,
        0.02,
        0.03,
        0.04,
        0.05,
        0.06,
        0.07,
        0.08,
        0.09,
        0.10,
        0.11,
        0.12,
        0.13,
        0.14,
    ]

    value_at_risk = calculate_historical_var(
        returns,
        confidence_level=0.95,
    )

    assert value_at_risk == pytest.approx(0.10)


def test_calculates_historical_cvar_at_95_percent():
    returns = [
        -0.10,
        -0.05,
        -0.03,
        -0.02,
        -0.01,
        0.00,
        0.01,
        0.02,
        0.03,
        0.04,
        0.05,
        0.06,
        0.07,
        0.08,
        0.09,
        0.10,
        0.11,
        0.12,
        0.13,
        0.14,
    ]

    conditional_var = calculate_historical_cvar(
        returns,
        confidence_level=0.95,
    )

    assert conditional_var == pytest.approx(0.10)


def test_var_and_cvar_are_unavailable_without_returns():
    assert calculate_historical_var([]) is None
    assert calculate_historical_cvar([]) is None


def test_var_and_cvar_reject_invalid_confidence_level():
    with pytest.raises(
        ValueError,
        match="confidence_level must be between 0 and 1",
    ):
        calculate_historical_var(
            [0.01, -0.02],
            confidence_level=1.0,
        )

    with pytest.raises(
        ValueError,
        match="confidence_level must be between 0 and 1",
    ):
        calculate_historical_cvar(
            [0.01, -0.02],
            confidence_level=0.0,
        )
