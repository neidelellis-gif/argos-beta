"""Compatibility imports for the market loader superseded by connectors."""

from backend.market_connectors.local_connector import (
    DEFAULT_MARKET_ROOT,
    MarketDataSource,
    MarketDataValidationError,
    OfficialMarketData,
    LocalMarketConnector,
)

# Retained for callers of the Operation Real 02 public import.
MarketDataLoader = LocalMarketConnector

__all__ = (
    "DEFAULT_MARKET_ROOT",
    "MarketDataLoader",
    "MarketDataSource",
    "MarketDataValidationError",
    "OfficialMarketData",
)
