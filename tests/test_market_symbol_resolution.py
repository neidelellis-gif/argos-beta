import json
from decimal import Decimal

import pytest

from backend.market_symbol_resolution import (
    load_market_symbol_registry,
    market_symbol_stable_key,
    resolve_market_symbol,
)
from backend.models import PortfolioOwner, PortfolioPosition


def position(
    *,
    institution="Santander",
    identifier="US45866F1049",
    identifier_type="ISIN",
):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name="Test Asset",
        identifier=identifier,
        identifier_type=identifier_type,
        quantity=Decimal("1"),
        unit_price=Decimal("1"),
        market_value=Decimal("1"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="test.csv",
        economic_asset_class=None,
    )


def write_registry(tmp_path, resolutions):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "resolutions": resolutions,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_ticker_passes_through_without_registry():
    p = position(
        identifier="ice",
        identifier_type="ticker",
    )

    assert resolve_market_symbol(p, registry={}) == "ICE"


def test_stable_key_preserves_original_identity():
    p = position()

    assert market_symbol_stable_key(p) == (
        "JOLIKA|SANTANDER|ISIN:US45866F1049"
    )


def test_confirmed_isin_resolution_returns_symbol(tmp_path):
    p = position()
    key = market_symbol_stable_key(p)

    path = write_registry(
        tmp_path,
        [
            {
                "stable_key": key,
                "market_symbol": "ICE",
                "status": "confirmed",
                "resolution_source": "human_review",
                "note": "Confirmed listed equity",
            }
        ],
    )

    registry = load_market_symbol_registry(path)

    assert resolve_market_symbol(
        p,
        registry=registry,
    ) == "ICE"


def test_unknown_isin_fails_closed():
    assert resolve_market_symbol(
        position(),
        registry={},
    ) is None


def test_registry_rejects_unconfirmed_resolution(tmp_path):
    path = write_registry(
        tmp_path,
        [
            {
                "stable_key": (
                    "JOLIKA|SANTANDER|"
                    "ISIN:US45866F1049"
                ),
                "market_symbol": "ICE",
                "status": "proposed",
                "resolution_source": "human_review",
            }
        ],
    )

    with pytest.raises(ValueError):
        load_market_symbol_registry(path)


def test_registry_rejects_duplicate_key(tmp_path):
    record = {
        "stable_key": (
            "JOLIKA|SANTANDER|"
            "ISIN:US45866F1049"
        ),
        "market_symbol": "ICE",
        "status": "confirmed",
        "resolution_source": "human_review",
    }

    path = write_registry(
        tmp_path,
        [record, record],
    )

    with pytest.raises(ValueError):
        load_market_symbol_registry(path)
