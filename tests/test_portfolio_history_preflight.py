from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_history_preflight import run_portfolio_history_preflight
from backend.portfolio_snapshots import PortfolioSnapshot


NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)


def position(
    institution="UBS", value="100", owner=PortfolioOwner.JOLIKA, resolved=True
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class="Cash",
        asset_subclass=None,
        asset_name=f"{institution} asset",
        identifier=f"{institution}-1",
        identifier_type="INTERNAL",
        quantity=None,
        unit_price=None,
        market_value=None if value is None else Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution.lower()}.csv",
        economic_asset_class=EconomicAssetClass.CASH if resolved else None,
    )


def payload(positions=None, files=None, warnings=(), dashboard=True):
    positions = tuple(positions or (position(), position("Santander", "200")))
    if files is None:
        files = (
            {"name": "ubs.csv", "institution": "UBS", "position_count": 1},
            {"name": "san.xlsx", "institution": "Santander", "position_count": 1},
        )
    totals = {}
    for item in positions:
        totals[item.currency or ""] = totals.get(item.currency or "", Decimal("0")) + (
            item.market_value or Decimal("0")
        )
    return {
        "positions": positions,
        "files": list(files),
        "diagnostics": [
            {"institution": "UBS", "position_count": 1, "warnings": list(warnings)},
            {"institution": "Santander", "position_count": 1, "warnings": []},
        ],
        "dashboard": (
            {"consolidated": {"totals_by_currency": {k: str(v) for k, v in totals.items()}}}
            if dashboard
            else None
        ),
    }


def run(data=None, **kwargs):
    with patch(
        "backend.portfolio_history_preflight.import_portfolios",
        return_value=payload() if data is None else data,
    ):
        return run_portfolio_history_preflight(
            ubs_path=Path("ubs.csv"), santander_path=Path("san.xlsx"), **kwargs
        )


def snapshot(count, captured_at=NOW):
    positions = tuple(position(value=str(index)) for index in range(count))
    return PortfolioSnapshot(1, "baseline", PortfolioOwner.JOLIKA, captured_at, positions, (), ("UBS",), ())


def test_valid_preflight_and_frozen_result():
    result = run()
    assert result.approved
    assert result.total_position_count == 2
    assert result.ubs.position_count == result.santander.position_count == 1
    with pytest.raises(FrozenInstanceError):
        result.approved = False
    with pytest.raises(FrozenInstanceError):
        result.ubs.position_count = 3


@pytest.mark.parametrize(
    ("positions", "blocker"),
    [
        ((position("Santander"),), "missing UBS positions"),
        ((position(),), "missing Santander positions"),
        ((), "no positions"),
        ((position(owner=PortfolioOwner.NEI), position("Santander")), "non-JOLIKA positions: 1"),
        ((position(resolved=False), position("Santander")), "unresolved JOLIKA assets: 1"),
    ],
)
def test_position_blockers(positions, blocker):
    data = payload(positions=positions) if positions else payload()
    if not positions:
        data["positions"] = ()
        data["dashboard"] = {"consolidated": {"totals_by_currency": {}}}
    result = run(data)
    assert not result.approved
    assert blocker in result.blockers


@pytest.mark.parametrize(
    "files",
    [
        ({"institution": "Santander"}, {"institution": "Santander"}),
        ({"institution": "UBS"}, {"institution": "UBS"}),
    ],
)
def test_source_institution_mismatch_blocks(files):
    result = run(payload(files=files))
    assert "source file institution mismatch" in result.blockers
    assert any("source file institution mismatch:" in warning for warning in result.warnings)


def test_decimal_totals_and_none_market_value_without_inference():
    result = run(payload((position(value=None), position("Santander", "2.5"))))
    assert result.totals_by_currency == (("USD", Decimal("2.5")),)
    assert result.ubs.totals_by_currency == (("USD", Decimal("0")),)
    assert isinstance(result.totals_by_currency[0][1], Decimal)


def test_non_finite_total_returns_structured_blocker():
    data = payload()
    data["positions"] = (position(value="NaN"), position("Santander"))
    data["dashboard"] = None
    result = run(data)
    assert not result.approved
    assert result.totals_by_currency == ()
    assert "non-finite totals_by_currency" in result.blockers


def test_dashboard_totals_consistent_and_divergent():
    assert run().approved
    data = payload()
    data["dashboard"]["consolidated"]["totals_by_currency"]["USD"] = "999"
    assert "dashboard totals mismatch" in run(data).blockers


def test_official_warnings_are_preserved():
    result = run(payload(warnings=("official warning",)))
    assert result.ubs.warnings == ("official warning",)
    assert "official warning" in result.warnings


def test_baseline_absent_and_later_baseline_not_used():
    with patch("backend.portfolio_history_preflight.list_portfolio_snapshots", return_value=()), patch(
        "backend.portfolio_history_preflight.select_previous_portfolio_snapshot", return_value=None
    ) as select:
        result = run(snapshot_directory="snapshots", before=NOW)
    assert result.baseline_snapshot_id is None
    select.assert_called_once_with((), before=NOW)


@pytest.mark.parametrize(("current", "baseline_count", "change"), [(2, 3, -1), (2, 1, 1)])
def test_baseline_change_and_drop_warning_only(current, baseline_count, change):
    data = payload(tuple(position("UBS" if i % 2 == 0 else "Santander", str(i)) for i in range(current)))
    prior = snapshot(baseline_count)
    with patch("backend.portfolio_history_preflight.import_portfolios", return_value=data), patch(
        "backend.portfolio_history_preflight.list_portfolio_snapshots", return_value=(prior,)
    ), patch("backend.portfolio_history_preflight.select_previous_portfolio_snapshot", return_value=prior):
        result = run_portfolio_history_preflight(ubs_path="ubs.csv", santander_path="san.xlsx", snapshot_directory="snapshots", before=NOW)
    assert result.baseline_snapshot_id == "baseline"
    assert result.baseline_position_count == baseline_count
    assert result.position_count_change == change
    drop = [warning for warning in result.warnings if "below baseline" in warning]
    assert bool(drop) is (change < 0)
    assert not any("baseline" in blocker for blocker in result.blockers)


def test_position_order_does_not_change_factual_result():
    first = run(payload((position(), position("Santander", "200"))))
    second = run(payload((position("Santander", "200"), position())))
    assert first.totals_by_currency == second.totals_by_currency
    assert first.total_position_count == second.total_position_count
    assert first.unresolved_keys == second.unresolved_keys


def test_preflight_never_calls_persistence(tmp_path):
    target = tmp_path / "does-not-exist"
    run()
    assert not target.exists()


def test_import_module_has_no_filesystem_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = tuple(tmp_path.iterdir())
    __import__("backend.portfolio_history_preflight")
    assert tuple(tmp_path.iterdir()) == before
