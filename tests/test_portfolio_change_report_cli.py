from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import backend.portfolio_change_report_cli as cli
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_change_report_cli import main
from backend.portfolio_change_reports import (
    build_portfolio_change_report,
    load_portfolio_change_report,
    portfolio_change_report_filename,
    write_portfolio_change_report,
)
from backend.portfolio_snapshots import (
    build_portfolio_snapshot,
    portfolio_snapshot_filename,
    write_portfolio_snapshot,
)


UTC = timezone.utc


def position(
    name="X",
    *,
    account="A",
    quantity="1",
    value="10",
    institution="UBS",
):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=account,
        asset_class="Cash",
        asset_subclass=None,
        asset_name=name,
        identifier=name,
        identifier_type="NAME",
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=Decimal("10"),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=None,
        reference_date=date(2026, 1, 1),
        source_file=f"{institution.lower()}.csv",
        economic_asset_class=EconomicAssetClass.CASH,
    )


def snapshot(day: int, positions=(position(),)):
    return build_portfolio_snapshot(
        tuple(positions),
        captured_at=datetime(2026, 1, day, tzinfo=UTC),
    )


def write_snapshot(root, item):
    path = root / portfolio_snapshot_filename(item)
    write_portfolio_snapshot(item, output_path=path)
    return path


def make_report(root, old, new, generated=None):
    item = build_portfolio_change_report(
        old,
        new,
        generated_at=generated or new.captured_at,
    )
    path = root / portfolio_change_report_filename(item)
    write_portfolio_change_report(item, output_path=path)
    return item, path


def test_parser_exposes_all_commands():
    parser = cli._parser()
    for command in ("generate", "list", "show", "validate", "validate-sequence"):
        if command == "generate":
            args = parser.parse_args([
                command, "--previous", "a", "--current", "b"
            ])
        elif command == "show":
            args = parser.parse_args([command, "--report", "r"])
        elif command == "validate":
            args = parser.parse_args([
                command, "--report", "r", "--previous", "a", "--current", "b"
            ])
        else:
            args = parser.parse_args([command])
        assert args.command == command


def test_generate_valid_default_and_aware_timestamp(tmp_path, capsys):
    old, new = snapshot(1), snapshot(2)
    p1, p2 = write_snapshot(tmp_path, old), write_snapshot(tmp_path, new)
    out = tmp_path / "reports"

    assert main([
        "generate", "--previous", str(p1), "--current", str(p2),
        "--directory", str(out),
    ]) == 0
    created = list(out.glob("jolika_change_*.json"))
    assert len(created) == 1
    loaded = load_portfolio_change_report(created[0])
    assert loaded.generated_at.tzinfo is not None
    assert "Report created" in capsys.readouterr().out

    out2 = tmp_path / "aware"
    assert main([
        "generate", "--previous", str(p1), "--current", str(p2),
        "--directory", str(out2),
        "--generated-at", "2026-01-03T03:00:00-03:00",
    ]) == 0
    loaded2 = load_portfolio_change_report(next(out2.glob("*.json")))
    assert loaded2.generated_at == datetime(2026, 1, 3, 6, tzinfo=UTC)


def test_generate_rejects_naive_and_invalid_temporal_order(tmp_path, capsys):
    old, new = snapshot(1), snapshot(2)
    p1, p2 = write_snapshot(tmp_path, old), write_snapshot(tmp_path, new)

    assert main([
        "generate", "--previous", str(p1), "--current", str(p2),
        "--directory", str(tmp_path / "r"),
        "--generated-at", "2026-01-03T00:00:00",
    ]) == 2
    assert "timezone-aware" in capsys.readouterr().err

    assert main([
        "generate", "--previous", str(p2), "--current", str(p1),
        "--directory", str(tmp_path / "r2"),
    ]) == 2
    assert "must be earlier" in capsys.readouterr().err


def test_generate_overwrite_policy(tmp_path, capsys):
    old, new = snapshot(1), snapshot(2)
    p1, p2 = write_snapshot(tmp_path, old), write_snapshot(tmp_path, new)
    args = [
        "generate", "--previous", str(p1), "--current", str(p2),
        "--directory", str(tmp_path / "reports"),
        "--generated-at", "2026-01-03T00:00:00Z",
    ]
    assert main(args) == 0
    assert main(args) == 2
    assert "already exists" in capsys.readouterr().err
    assert main(args + ["--overwrite"]) == 0


def test_list_empty_and_latest_first(tmp_path, capsys):
    assert main(["list", "--directory", str(tmp_path / "missing")]) == 0
    assert "no change reports" in capsys.readouterr().out

    s1, s2, s3 = snapshot(1), snapshot(2), snapshot(3)
    r12, _ = make_report(tmp_path, s1, s2)
    r23, _ = make_report(tmp_path, s2, s3)
    assert main(["list", "--directory", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert r23.report_id in lines[0]
    assert r12.report_id in lines[1]


def test_show_metadata_without_positions_or_accounts(tmp_path, capsys):
    old = snapshot(1, (position(account="SECRET-ACCOUNT"),))
    new = snapshot(2, (position(account="SECRET-ACCOUNT"),))
    item, path = make_report(tmp_path, old, new)
    assert main(["show", "--report", str(path)]) == 0
    output = capsys.readouterr().out
    assert f"report_id: {item.report_id}" in output
    assert "unchanged: 1" in output
    assert "SECRET-ACCOUNT" not in output
    assert "change_set" not in output
    assert "identifier" not in output


def test_validate_lineage_valid_and_invalid(tmp_path, capsys):
    old, new, other = snapshot(1), snapshot(2), snapshot(3)
    p1 = write_snapshot(tmp_path, old)
    p2 = write_snapshot(tmp_path, new)
    p3 = write_snapshot(tmp_path, other)
    _, report_path = make_report(tmp_path / "reports", old, new)

    assert main([
        "validate", "--report", str(report_path),
        "--previous", str(p1), "--current", str(p2),
    ]) == 0
    assert "lineage valid" in capsys.readouterr().out

    assert main([
        "validate", "--report", str(report_path),
        "--previous", str(p1), "--current", str(p3),
    ]) == 2
    assert "lineage" in capsys.readouterr().err.lower()


def test_validate_sequence_empty_and_continuous(tmp_path, capsys):
    empty = tmp_path / "empty"
    assert main(["validate-sequence", "--directory", str(empty)]) == 0
    output = capsys.readouterr().out
    assert "sequence valid" in output and "reports: 0" in output

    s1, s2, s3 = snapshot(1), snapshot(2), snapshot(3)
    make_report(tmp_path, s1, s2)
    make_report(tmp_path, s2, s3)
    assert main(["validate-sequence", "--directory", str(tmp_path)]) == 0
    assert "reports: 2" in capsys.readouterr().out


def test_validate_sequence_gap_and_branch(tmp_path, capsys):
    s1, s2, s3, s4 = snapshot(1), snapshot(2), snapshot(3), snapshot(4)

    gap = tmp_path / "gap"
    make_report(gap, s1, s2)
    make_report(gap, s3, s4)
    assert main(["validate-sequence", "--directory", str(gap)]) == 2
    assert "Gap" in capsys.readouterr().err

    branch = tmp_path / "branch"
    make_report(branch, s1, s2)
    make_report(branch, s1, s3)
    assert main(["validate-sequence", "--directory", str(branch)]) == 2
    assert "Branched" in capsys.readouterr().err


def test_validate_sequence_duplicate_is_operational_error(monkeypatch, capsys):
    s1, s2 = snapshot(1), snapshot(2)
    item = build_portfolio_change_report(s1, s2, generated_at=s2.captured_at)
    monkeypatch.setattr(cli, "list_portfolio_change_reports", lambda directory: (item, item))
    assert main(["validate-sequence", "--directory", "ignored"]) == 2
    assert "Duplicate" in capsys.readouterr().err


def test_dda_multi_account_remains_domain_delegated(tmp_path, capsys):
    accounts = ("115088644", "115099244", "115111355", "115111444")
    positions = tuple(
        position(
            "DDA CUSTODIAL CASH ACCOUNTS",
            account=account,
            quantity=None,
            value="350" if account == "115088644" else "0",
            institution="Santander",
        )
        for account in accounts
    )
    old = snapshot(1, positions)
    new = snapshot(2, positions)
    p1, p2 = write_snapshot(tmp_path, old), write_snapshot(tmp_path, new)
    out = tmp_path / "reports"

    assert main([
        "generate", "--previous", str(p1), "--current", str(p2),
        "--directory", str(out),
        "--generated-at", "2026-01-03T00:00:00Z",
    ]) == 0
    report = load_portfolio_change_report(next(out.glob("*.json")))
    assert report.summary.unchanged == 4
    assert len({delta.current_instance_key for delta in report.change_set.deltas}) == 4
    assert "unchanged: 4" in capsys.readouterr().out
