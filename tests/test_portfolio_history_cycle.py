from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_change_reports import (
    build_portfolio_change_report,
    portfolio_change_report_filename,
    validate_portfolio_change_report_lineage,
    write_portfolio_change_report,
)
from backend.portfolio_changes import PositionChangeType
from backend.portfolio_history_cycle import (
    PortfolioHistoryCycleStatus,
    run_portfolio_history_cycle,
)
from backend.portfolio_snapshots import (
    build_portfolio_snapshot,
    portfolio_snapshot_filename,
    write_portfolio_snapshot,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)


def position(institution="UBS", account="A", identifier="X", quantity="1", value="10", currency="USD", economic=EconomicAssetClass.CASH):
    return PortfolioPosition(
        institution=institution, owner=PortfolioOwner.JOLIKA, account=account,
        asset_class="Cash", asset_subclass=None, asset_name=identifier,
        identifier=identifier, identifier_type="TICKER",
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=Decimal("10"),
        market_value=None if value is None else Decimal(value), currency=currency,
        portfolio_weight=None, reference_date=None,
        source_file=f"{institution.lower()}.csv", economic_asset_class=economic,
    )


def positions():
    return (position(), position("Santander", identifier="Y", value="20"))


def imported(items=None, totals=None):
    items = positions() if items is None else tuple(items)
    if totals is None:
        totals = {}
        for item in items:
            currency = item.currency or "UNKNOWN"
            totals[currency] = str(
                Decimal(totals.get(currency, "0"))
                + (item.market_value or Decimal("0"))
            )
    return {
        "positions": items,
        "diagnostics": [{"institution": "UBS", "warnings": ["review"]}],
        "dashboard": {"consolidated": {"totals_by_currency": totals}},
    }


def run(tmp_path, *, data=None, at=NOW, generated_at=None, overwrite=False):
    snapshots = tmp_path / "snapshots"
    reports = tmp_path / "reports"
    with patch("backend.portfolio_history_cycle.import_portfolios", return_value=data or imported()):
        result = run_portfolio_history_cycle(
            ubs_path="ubs.csv", santander_path="santander.xlsx",
            snapshot_directory=snapshots, report_directory=reports,
            captured_at=at, generated_at=generated_at, overwrite=overwrite,
        )
    return result, snapshots, reports


def baseline(directory, at=NOW - timedelta(days=1), items=None):
    snapshot = build_portfolio_snapshot(items or positions(), captured_at=at)
    path = directory / portfolio_snapshot_filename(snapshot)
    write_portfolio_snapshot(snapshot, output_path=path)
    return snapshot


def test_initial_snapshot_without_baseline_and_no_report(tmp_path):
    result, snapshots, reports = run(tmp_path)
    assert result.status is PortfolioHistoryCycleStatus.INITIAL_SNAPSHOT
    assert result.previous_snapshot is result.change_report is result.report_path is None
    assert result.snapshot_path.exists()
    assert not reports.exists()
    assert list(snapshots.iterdir()) == [result.snapshot_path]


def test_historical_update_selects_latest_previous_and_has_valid_lineage(tmp_path):
    snapshots = tmp_path / "snapshots"
    older = baseline(snapshots, NOW - timedelta(days=2))
    latest = baseline(snapshots, NOW - timedelta(days=1))
    result, _, _ = run(tmp_path)
    assert result.status is PortfolioHistoryCycleStatus.HISTORICAL_UPDATE
    assert result.previous_snapshot == latest and result.previous_snapshot != older
    assert result.change_report is not None and result.report_path.exists()
    validate_portfolio_change_report_lineage(result.change_report, latest, result.current_snapshot)


def test_naive_captured_at_rejected_before_import(tmp_path):
    with patch("backend.portfolio_history_cycle.import_portfolios") as importer:
        with pytest.raises(ValueError, match="timezone-aware"):
            run_portfolio_history_cycle(ubs_path="u", santander_path="s", snapshot_directory=tmp_path, report_directory=tmp_path, captured_at=NOW.replace(tzinfo=None))
    importer.assert_not_called()


@pytest.mark.parametrize(("items", "message"), [
    ((position("Santander"),), "UBS"),
    ((position(),), "Santander"),
    ((replace(position(), economic_asset_class=None), position("Santander")), "unresolved"),
])
def test_invalid_operational_import_blocks(items, message, tmp_path):
    with pytest.raises(ValueError, match=message):
        run(tmp_path, data=imported(items))
    assert not (tmp_path / "snapshots").exists()


def test_decimal_totals_warnings_and_dashboard_divergence(tmp_path):
    items = (position(value="10.25"), position("Santander", value="2.75", currency="EUR"))
    result, _, _ = run(tmp_path, data=imported(items))
    assert result.totals_by_currency == {"EUR": Decimal("2.75"), "USD": Decimal("10.25")}
    assert all(isinstance(value, Decimal) for value in result.totals_by_currency.values())
    assert result.warnings == ("UBS: review",)
    with pytest.raises(ValueError, match="totals"):
        run(tmp_path / "bad", data=imported(items, {"USD": "99"}))


def test_snapshot_conflict_detected_before_any_write(tmp_path):
    first, _, _ = run(tmp_path)
    report_dir = tmp_path / "reports"
    with patch("backend.portfolio_history_cycle.write_portfolio_snapshot") as snap_write, patch("backend.portfolio_history_cycle.write_portfolio_change_report") as report_write:
        with pytest.raises(FileExistsError):
            run(tmp_path)
    snap_write.assert_not_called(); report_write.assert_not_called()
    assert first.snapshot_path.exists() and not report_dir.exists()


def test_report_conflict_detected_before_snapshot_write(tmp_path):
    snapshots = tmp_path / "snapshots"
    previous = baseline(snapshots)
    current = build_portfolio_snapshot(positions(), captured_at=NOW)
    report = build_portfolio_change_report(previous, current, generated_at=NOW)
    report_path = tmp_path / "reports" / portfolio_change_report_filename(report)
    write_portfolio_change_report(report, output_path=report_path)
    with patch("backend.portfolio_history_cycle.write_portfolio_snapshot") as writer:
        with pytest.raises(FileExistsError): run(tmp_path)
    writer.assert_not_called()
    assert not (snapshots / portfolio_snapshot_filename(current)).exists()


def test_explicit_overwrite(tmp_path):
    first, _, _ = run(tmp_path)
    second, _, _ = run(tmp_path, overwrite=True)
    assert first.current_snapshot == second.current_snapshot


def test_continuous_sequence_and_gap_or_branch_block_before_persistence(tmp_path):
    snapshots = tmp_path / "snapshots"; reports = tmp_path / "reports"
    s1 = baseline(snapshots, NOW - timedelta(days=2))
    s2 = baseline(snapshots, NOW - timedelta(days=1))
    r12 = build_portfolio_change_report(s1, s2, generated_at=s2.captured_at)
    write_portfolio_change_report(r12, output_path=reports / portfolio_change_report_filename(r12))
    result, _, _ = run(tmp_path)
    assert result.report_path.exists()

    for kind in ("gap", "branch"):
        root = tmp_path / kind; snap_dir = root / "snapshots"; report_dir = root / "reports"
        old = baseline(snap_dir, NOW - timedelta(days=2))
        latest = baseline(snap_dir, NOW - timedelta(days=1))
        endpoint = build_portfolio_snapshot(
            (replace(position(), market_value=Decimal("11")), position("Santander", identifier="Y", value="20")),
            captured_at=(NOW - timedelta(hours=12) if kind == "gap" else NOW + timedelta(days=1)),
        )
        existing = build_portfolio_change_report(old, endpoint, generated_at=endpoint.captured_at)
        write_portfolio_change_report(existing, output_path=report_dir / portfolio_change_report_filename(existing))
        with pytest.raises(ValueError, match="Gap|Branched"):
            run(root)
        assert not (snap_dir / portfolio_snapshot_filename(build_portfolio_snapshot(positions(), captured_at=NOW))).exists()


def test_dda_accounts_quantity_none_and_account_transfer_preserved(tmp_path):
    accounts = ("115088644", "115099244", "115111355", "115111444")
    old_items = tuple(position("Santander", account=a, identifier="DDA CUSTODIAL CASH ACCOUNTS", quantity=None) for a in accounts) + (position(account="OLD", identifier="MOVE"),)
    new_items = tuple(reversed(tuple(position("Santander", account=a, identifier="DDA CUSTODIAL CASH ACCOUNTS", quantity=None) for a in accounts))) + (position(account="NEW", identifier="MOVE"),)
    snapshots = tmp_path / "snapshots"; baseline(snapshots, items=old_items)
    result, _, _ = run(tmp_path, data=imported(new_items))
    dda = [p for p in result.current_snapshot.positions if p.asset_name == "DDA CUSTODIAL CASH ACCOUNTS"]
    assert {p.account for p in dda} == set(accounts) and all(p.quantity is None for p in dda)
    moved = next(delta for delta in result.change_report.change_set.deltas if delta.asset_name == "MOVE")
    assert moved.change_types == (PositionChangeType.ACCOUNT_CHANGED,)


def test_failure_before_persistence_creates_nothing(tmp_path):
    with patch("backend.portfolio_history_cycle.validate_portfolio_change_report_lineage", side_effect=ValueError("bad")):
        baseline(tmp_path / "snapshots")
        with pytest.raises(ValueError, match="bad"): run(tmp_path)
    assert not (tmp_path / "reports").exists()
    assert len(tuple((tmp_path / "snapshots").iterdir())) == 1


def test_second_write_failure_removes_only_new_snapshot(tmp_path):
    baseline(tmp_path / "snapshots")
    with patch("backend.portfolio_history_cycle.write_portfolio_change_report", side_effect=OSError("disk")):
        with pytest.raises(OSError, match="disk"): run(tmp_path)
    assert len(tuple((tmp_path / "snapshots").iterdir())) == 1

    root = tmp_path / "overwrite"; previous = baseline(root / "snapshots")
    current = build_portfolio_snapshot(positions(), captured_at=NOW)
    current_path = root / "snapshots" / portfolio_snapshot_filename(current)
    write_portfolio_snapshot(current, output_path=current_path)
    with patch("backend.portfolio_history_cycle.write_portfolio_change_report", side_effect=OSError("disk")):
        with pytest.raises(OSError): run(root, overwrite=True)
    assert current_path.exists() and previous != current


def test_position_order_does_not_change_canonical_result(tmp_path):
    first, _, _ = run(tmp_path / "a", data=imported(positions()))
    second, _, _ = run(tmp_path / "b", data=imported(reversed(positions())))
    assert first.current_snapshot == second.current_snapshot


def test_import_does_not_create_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import backend.portfolio_history_cycle as module
    importlib.reload(module)
    assert list(tmp_path.iterdir()) == []
