from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_snapshot_cli import main
import backend.portfolio_snapshot_cli as cli
from backend.portfolio_snapshots import (
    build_portfolio_snapshot,
    load_portfolio_snapshot,
    portfolio_snapshot_filename,
    write_portfolio_snapshot,
)


def pos(
    identifier: str,
    *,
    institution: str,
    account: str = "1",
    quantity: str | None = "10",
    value: str = "1000",
    source_file: str,
    economic=EconomicAssetClass.EQUITIES,
):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=account,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type="ticker",
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=Decimal("100"),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=Decimal("1"),
        reference_date=date(2026, 8, 12),
        source_file=source_file,
        economic_asset_class=economic,
    )


def current_positions():
    return (
        pos("A", institution="UBS", source_file="ubs.csv"),
        pos("B", institution="Santander", source_file="santander.xlsx"),
    )


def fake_result(positions=None, *, warnings=()):
    positions = tuple(positions or current_positions())
    total = sum((p.market_value or Decimal("0") for p in positions), Decimal("0"))
    diagnostics = []
    if warnings:
        diagnostics.append({"institution": "UBS", "warnings": list(warnings)})
    return {
        "positions": positions,
        "diagnostics": diagnostics,
        "dashboard": {
            "consolidated": {
                "totals_by_currency": {"USD": str(total)},
            }
        },
    }


def snapshot(at_hour: int, positions=None):
    return build_portfolio_snapshot(
        tuple(positions or current_positions()),
        captured_at=datetime(2026, 8, 12, at_hour, 0, tzinfo=timezone.utc),
    )


def test_capture_creates_loadable_snapshot(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result())
    code = main([
        "capture",
        "--ubs", "ubs.csv",
        "--santander", "s.xlsx",
        "--directory", str(tmp_path),
        "--captured-at", "2026-08-12T12:00:00Z",
    ])
    assert code == 0
    files = list(tmp_path.glob("jolika_*.json"))
    assert len(files) == 1
    loaded = load_portfolio_snapshot(files[0])
    assert len(loaded.positions) == 2
    assert loaded.captured_at.microsecond == 0
    assert "Snapshot created" in capsys.readouterr().out


def test_capture_warns_but_does_not_block(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli,
        "import_portfolios",
        lambda paths: fake_result(warnings=("2 position(s) without symbol",)),
    )
    code = main([
        "capture", "--ubs", "u", "--santander", "s",
        "--directory", str(tmp_path), "--captured-at", "2026-08-12T12:00:00Z",
    ])
    assert code == 0
    assert "warning:" in capsys.readouterr().out


def test_capture_requires_both_institutions(monkeypatch, tmp_path, capsys):
    only_ubs = (pos("A", institution="UBS", source_file="u.csv"),)
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result(only_ubs))
    code = main([
        "capture", "--ubs", "u", "--santander", "s", "--directory", str(tmp_path)
    ])
    assert code == 2
    assert not list(tmp_path.glob("*.json"))
    assert "both UBS and Santander" in capsys.readouterr().err


def test_capture_duplicate_requires_overwrite(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result())
    args = [
        "capture", "--ubs", "u", "--santander", "s",
        "--directory", str(tmp_path), "--captured-at", "2026-08-12T12:00:00Z",
    ]
    assert main(args) == 0
    assert main(args) == 2
    assert "snapshot already exists" in capsys.readouterr().err
    assert main(args + ["--overwrite"]) == 0


def test_list_missing_empty_and_latest_first(tmp_path, capsys):
    missing = tmp_path / "missing"
    assert main(["list", "--directory", str(missing)]) == 0
    assert "no snapshots" in capsys.readouterr().out
    for item in (snapshot(10), snapshot(12)):
        write_portfolio_snapshot(item, output_path=tmp_path / portfolio_snapshot_filename(item))
    assert main(["list", "--directory", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "T12:00:00" in lines[0]
    assert "T10:00:00" in lines[1]


def test_show_displays_metadata_not_accounts(tmp_path, capsys):
    item = snapshot(10)
    path = tmp_path / portfolio_snapshot_filename(item)
    write_portfolio_snapshot(item, output_path=path)
    assert main(["show", "--snapshot", str(path)]) == 0
    output = capsys.readouterr().out
    assert f"snapshot_id: {item.snapshot_id}" in output
    assert "position_count: 2" in output
    assert "totals_by_currency" in output
    assert "account=" not in output


def test_compare_valid_and_temporal_order(tmp_path, capsys):
    first = snapshot(10)
    changed = list(current_positions())
    changed[0] = pos("A", institution="UBS", source_file="ubs.csv", quantity="15")
    second = snapshot(11, changed)
    p1 = tmp_path / portfolio_snapshot_filename(first)
    p2 = tmp_path / portfolio_snapshot_filename(second)
    write_portfolio_snapshot(first, output_path=p1)
    write_portfolio_snapshot(second, output_path=p2)
    assert main(["compare", "--previous", str(p1), "--current", str(p2)]) == 0
    assert "quantity_increased: 1" in capsys.readouterr().out
    assert main(["compare", "--previous", str(p2), "--current", str(p1)]) == 2
    assert "must be earlier" in capsys.readouterr().err


def test_compare_export_is_deterministic_and_no_overwrite(tmp_path, capsys):
    first = snapshot(10)
    second = snapshot(11)
    p1 = tmp_path / portfolio_snapshot_filename(first)
    p2 = tmp_path / portfolio_snapshot_filename(second)
    out = tmp_path / "changes.json"
    write_portfolio_snapshot(first, output_path=p1)
    write_portfolio_snapshot(second, output_path=p2)
    args = ["compare", "--previous", str(p1), "--current", str(p2), "--output", str(out)]
    assert main(args) == 0
    payload = out.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert json.loads(payload)["deltas"]
    assert main(args) == 2
    assert main(args + ["--overwrite"]) == 0


def test_compare_current_without_baseline_does_not_persist(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result())
    assert main([
        "compare-current", "--ubs", "u", "--santander", "s",
        "--directory", str(tmp_path), "--captured-at", "2026-08-12T12:00:00Z",
    ]) == 0
    assert "no historical baseline" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.json"))


def test_compare_current_selects_previous_baseline(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result())
    baseline = snapshot(10)
    write_portfolio_snapshot(
        baseline,
        output_path=tmp_path / portfolio_snapshot_filename(baseline),
    )
    assert main([
        "compare-current", "--ubs", "u", "--santander", "s",
        "--directory", str(tmp_path), "--captured-at", "2026-08-12T12:00:00Z",
    ]) == 0
    output = capsys.readouterr().out
    assert f"baseline_snapshot_id: {baseline.snapshot_id}" in output
    assert "unchanged: 2" in output
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_dda_multi_account_preserved_in_compare(tmp_path, capsys):
    accounts = ("115088644", "115099244", "115111355", "115111444")
    dda = tuple(
        pos(
            "DDA CUSTODIAL CASH ACCOUNTS",
            institution="Santander",
            account=account,
            value="350" if account == "115088644" else "0",
            quantity=None,
            source_file="santander.xlsx",
        )
        for account in accounts
    )
    positions = (pos("A", institution="UBS", source_file="ubs.csv"),) + dda
    first = snapshot(10, positions)
    second = snapshot(11, positions)
    p1 = tmp_path / portfolio_snapshot_filename(first)
    p2 = tmp_path / portfolio_snapshot_filename(second)
    write_portfolio_snapshot(first, output_path=p1)
    write_portfolio_snapshot(second, output_path=p2)
    assert main(["compare", "--previous", str(p1), "--current", str(p2)]) == 0
    assert "unchanged: 5" in capsys.readouterr().out


def test_invalid_captured_at_is_operational_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "import_portfolios", lambda paths: fake_result())
    code = main([
        "capture", "--ubs", "u", "--santander", "s",
        "--directory", str(tmp_path), "--captured-at", "2026-08-12T12:00:00",
    ])
    assert code == 2
    assert "timezone-aware" in capsys.readouterr().err
