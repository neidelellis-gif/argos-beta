from dataclasses import fields

from backend.models import PortfolioPosition


def test_portfolio_position_has_only_mpu_v1_fields():
    assert [field.name for field in fields(PortfolioPosition)] == [
        "institution",
        "account",
        "asset_class",
        "asset_subclass",
        "asset_name",
        "identifier",
        "identifier_type",
        "quantity",
        "unit_price",
        "market_value",
        "currency",
        "portfolio_weight",
        "reference_date",
        "source_file",
    ]
