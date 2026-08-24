from __future__ import annotations

from decimal import Decimal

import pytest

from backend.market.models import (
    PriceHistory,
    PricePoint,
)
from backend.models import (
    EconomicAssetClass,
    PortfolioOwner,
    PortfolioPosition,
)
from backend.portfolio_quantitative_analysis import (
    calculate_drawdown,
    calculate_historical_cvar,
    calculate_historical_var,
    calculate_returns,
    calculate_volatility,
)
from backend.santander_quantitative_intelligence import (
    build_santander_quantitative_intelligence,
)


def position(
    *,
    institution="Santander",
    owner=PortfolioOwner.JOLIKA,
    identifier="AAA",
    identifier_type="ticker",
    name=None,
    currency="USD",
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=name if name is not None else identifier,
        identifier=identifier,
        identifier_type=identifier_type,
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file="santander.csv",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


class FakeMarketConnector:
    def __init__(self, histories=None):
        self.histories = histories or {}
        self.calls = []

    def get_history(self, ticker, *, days):
        self.calls.append((ticker, days))

        return self.histories.get(
            ticker,
            PriceHistory.unavailable(
                ticker,
                provider="Fake",
                error="not found",
            ),
        )


def history(
    ticker,
    prices,
    *,
    provider="Fake",
):
    return PriceHistory(
        ticker=ticker,
        currency="USD",
        provider=provider,
        points=tuple(
            PricePoint(
                date=f"2026-01-{index:02d}",
                close=float(price),
            )
            for index, price in enumerate(
                prices,
                start=1,
            )
        ),
        status="ok",
    )


def test_builds_quantitative_metrics_from_market_history():
    prices = [
        100.0,
        102.0,
        99.0,
        105.0,
        101.0,
        108.0,
    ]

    connector = FakeMarketConnector(
        {
            "AAA": history(
                "AAA",
                prices,
                provider="TestProvider",
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position(identifier="aaa")],
        market_connector=connector,
        lookback_days=180,
    )

    assert result.institution == "Santander"
    assert result.owner is PortfolioOwner.JOLIKA
    assert result.lookback_days == 180
    assert result.position_count == 1
    assert result.ticker_position_count == 1
    assert result.analyzed_position_count == 1
    assert result.unavailable_position_count == 0

    item = result.positions[0]

    returns = calculate_returns(prices)

    assert item.identifier == "AAA"
    assert item.identifier_type == "TICKER"
    assert item.status == "ok"
    assert item.provider == "TestProvider"
    assert item.observation_count == len(prices)
    assert item.first_date == "2026-01-01"
    assert item.last_date == "2026-01-06"

    assert item.annualized_volatility == pytest.approx(
        calculate_volatility(returns)
    )
    assert item.maximum_drawdown == pytest.approx(
        calculate_drawdown(prices)
    )
    assert item.historical_var_95 == pytest.approx(
        calculate_historical_var(
            returns,
            confidence_level=0.95,
        )
    )
    assert item.historical_cvar_95 == pytest.approx(
        calculate_historical_cvar(
            returns,
            confidence_level=0.95,
        )
    )

    assert item.error is None
    assert connector.calls == [("AAA", 180)]


def test_missing_identifier_is_unavailable_without_market_call():
    connector = FakeMarketConnector()

    result = build_santander_quantitative_intelligence(
        [
            position(
                identifier=None,
                identifier_type=None,
                name="Unknown Asset",
            )
        ],
        market_connector=connector,
    )

    item = result.positions[0]

    assert result.ticker_position_count == 0
    assert result.analyzed_position_count == 0
    assert result.unavailable_position_count == 1

    assert item.status == "unavailable"
    assert item.identifier is None
    assert item.error == "ticker identifier required"

    assert connector.calls == []


def test_non_ticker_identifier_is_not_sent_to_market_connector():
    connector = FakeMarketConnector()

    result = build_santander_quantitative_intelligence(
        [
            position(
                identifier="US1234567890",
                identifier_type="ISIN",
            )
        ],
        market_connector=connector,
    )

    item = result.positions[0]

    assert item.status == "unavailable"
    assert item.identifier_type == "ISIN"
    assert item.error == (
        "market history requires a ticker identifier"
    )

    assert connector.calls == []


def test_unavailable_history_is_preserved_without_breaking_analysis():
    connector = FakeMarketConnector(
        {
            "AAA": PriceHistory.unavailable(
                "AAA",
                provider="Finnhub",
                error="no historical data",
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position()],
        market_connector=connector,
    )

    item = result.positions[0]

    assert result.analyzed_position_count == 0
    assert result.unavailable_position_count == 1

    assert item.status == "unavailable"
    assert item.provider == "Finnhub"
    assert item.observation_count == 0
    assert item.annualized_volatility is None
    assert item.maximum_drawdown is None
    assert item.historical_var_95 is None
    assert item.historical_cvar_95 is None
    assert item.error == "no historical data"


def test_mixed_portfolio_keeps_available_and_unavailable_positions():
    connector = FakeMarketConnector(
        {
            "AAA": history(
                "AAA",
                [100.0, 101.0, 99.0, 103.0],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [
            position(identifier="AAA"),
            position(
                identifier="US1234567890",
                identifier_type="ISIN",
            ),
            position(
                identifier=None,
                identifier_type=None,
                name="No Identifier",
            ),
        ],
        market_connector=connector,
    )

    assert result.position_count == 3
    assert result.ticker_position_count == 1
    assert result.analyzed_position_count == 1
    assert result.unavailable_position_count == 2

    assert connector.calls == [("AAA", 365)]


def test_result_order_is_deterministic():
    connector = FakeMarketConnector(
        {
            "AAA": history("AAA", [100.0, 101.0]),
            "BBB": history("BBB", [100.0, 102.0]),
        }
    )

    result = build_santander_quantitative_intelligence(
        [
            position(identifier="BBB"),
            position(identifier="AAA"),
        ],
        market_connector=connector,
    )

    assert [
        item.identifier
        for item in result.positions
    ] == ["AAA", "BBB"]


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        (
            [position(institution="UBS")],
            "Santander",
        ),
        (
            [position(owner=PortfolioOwner.NEI)],
            "JOLIKA",
        ),
    ],
)
def test_rejects_non_santander_or_non_jolika_positions(
    positions,
    message,
):
    connector = FakeMarketConnector()

    with pytest.raises(
        ValueError,
        match=message,
    ):
        build_santander_quantitative_intelligence(
            positions,
            market_connector=connector,
        )


@pytest.mark.parametrize(
    "lookback_days",
    [
        0,
        -1,
        1.5,
        "30",
        True,
        False,
        None,
    ],
)
def test_rejects_invalid_lookback_days(
    lookback_days,
):
    connector = FakeMarketConnector()

    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        build_santander_quantitative_intelligence(
            [],
            market_connector=connector,
            lookback_days=lookback_days,
        )


def synthetic_history_from_returns(
    ticker,
    returns,
    *,
    initial_price=100.0,
):
    prices = [initial_price]

    for value in returns:
        prices.append(
            prices[-1] * (1.0 + value)
        )

    return history(
        ticker,
        prices,
    )


def test_low_risk_position_has_low_attention():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.002,
                    -0.001,
                    0.003,
                    -0.002,
                    0.001,
                    0.002,
                    -0.001,
                    0.001,
                    0.0005,
                    -0.0005,
                ],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position()],
        market_connector=connector,
    )

    item = result.positions[0]

    assert item.attention_level == "Baixa"
    assert item.attention_reasons == ()
    assert result.assessment.level == "Baixa"
    assert result.attention_positions == ()


def test_high_volatility_creates_high_attention():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.10,
                    -0.09,
                    0.11,
                    -0.08,
                    0.12,
                    -0.10,
                    0.09,
                    -0.11,
                    0.08,
                    -0.07,
                ],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position()],
        market_connector=connector,
    )

    item = result.positions[0]

    assert item.attention_level == "Alta"
    assert "high_volatility" in item.attention_reasons
    assert result.assessment.level == "Alta"
    assert result.assessment.high_attention_position_count == 1
    assert result.attention_positions == (item,)


def test_relevant_drawdown_creates_at_least_medium_attention():
    connector = FakeMarketConnector(
        {
            "AAA": history(
                "AAA",
                [
                    100.0,
                    110.0,
                    108.0,
                    100.0,
                    88.0,
                    90.0,
                    92.0,
                ],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position()],
        market_connector=connector,
    )

    item = result.positions[0]

    assert item.maximum_drawdown is not None
    assert abs(item.maximum_drawdown) == pytest.approx(0.20)
    assert item.attention_level in {"Média", "Alta"}
    assert "relevant_drawdown" in item.attention_reasons


def test_assessment_uses_strongest_position_attention():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.001,
                    -0.001,
                    0.002,
                    -0.001,
                    0.001,
                ],
            ),
            "BBB": synthetic_history_from_returns(
                "BBB",
                [
                    0.10,
                    -0.10,
                    0.12,
                    -0.11,
                    0.09,
                    -0.08,
                ],
            ),
        }
    )

    result = build_santander_quantitative_intelligence(
        [
            position(identifier="AAA"),
            position(identifier="BBB"),
        ],
        market_connector=connector,
    )

    assert result.assessment.level == "Alta"
    assert result.assessment.analyzed_position_count == 2
    assert result.assessment.high_attention_position_count >= 1


def test_attention_positions_exclude_low_and_unavailable_positions():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.001,
                    -0.001,
                    0.001,
                    -0.001,
                    0.001,
                ],
            ),
            "BBB": synthetic_history_from_returns(
                "BBB",
                [
                    0.08,
                    -0.07,
                    0.09,
                    -0.08,
                    0.10,
                    -0.09,
                ],
            ),
        }
    )

    result = build_santander_quantitative_intelligence(
        [
            position(identifier="AAA"),
            position(identifier="BBB"),
            position(
                identifier="US1234567890",
                identifier_type="ISIN",
            ),
        ],
        market_connector=connector,
    )

    identifiers = [
        item.identifier
        for item in result.attention_positions
    ]

    assert "BBB" in identifiers
    assert "AAA" not in identifiers
    assert "US1234567890" not in identifiers


def test_portfolio_reading_reports_high_attention():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.10,
                    -0.09,
                    0.11,
                    -0.08,
                    0.12,
                    -0.10,
                ],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [position()],
        market_connector=connector,
    )

    assert "risco histórico elevado" in result.portfolio_reading
    assert "atenção prioritária" in result.portfolio_reading


def test_portfolio_reading_reports_unavailable_positions():
    connector = FakeMarketConnector(
        {
            "AAA": synthetic_history_from_returns(
                "AAA",
                [
                    0.001,
                    -0.001,
                    0.002,
                    -0.001,
                ],
            )
        }
    )

    result = build_santander_quantitative_intelligence(
        [
            position(identifier="AAA"),
            position(
                identifier="US1234567890",
                identifier_type="ISIN",
            ),
        ],
        market_connector=connector,
    )

    assert "1 posição(ões) sem histórico" in result.portfolio_reading


def test_no_market_history_returns_clear_portfolio_reading():
    connector = FakeMarketConnector()

    result = build_santander_quantitative_intelligence(
        [
            position(
                identifier="US1234567890",
                identifier_type="ISIN",
            )
        ],
        market_connector=connector,
    )

    assert result.assessment.level == "Baixa"
    assert result.assessment.analyzed_position_count == 0
    assert (
        result.portfolio_reading
        == "Ainda não há histórico de mercado suficiente para produzir "
        "uma leitura quantitativa da carteira Santander."
    )
