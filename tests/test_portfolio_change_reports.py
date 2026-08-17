from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_change_reports import (
    PortfolioChangeReport, PortfolioChangeSummary,
    build_portfolio_change_report, list_portfolio_change_reports,
    load_portfolio_change_report, portfolio_change_report_filename,
    serialize_portfolio_change_report, validate_portfolio_change_report_lineage,
    validate_portfolio_change_report_sequence, write_portfolio_change_report,
)
from backend.portfolio_changes import PositionChangeType
from backend.portfolio_snapshots import build_portfolio_snapshot


UTC = timezone.utc


def position(name="X", account="A", quantity="1", price="10", value="10"):
    return PortfolioPosition(
        institution="UBS", owner=PortfolioOwner.JOLIKA, account=account,
        asset_class="Cash", asset_subclass=None, asset_name=name,
        identifier=name, identifier_type="NAME",
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=Decimal(price), market_value=Decimal(value), currency="USD",
        portfolio_weight=None, reference_date=None, source_file="ubs.csv",
        economic_asset_class=EconomicAssetClass.CASH,
    )


def snapshots(previous=(position(),), current=(position(),), offset=0):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=offset)
    return (build_portfolio_snapshot(previous, captured_at=start),
            build_portfolio_snapshot(current, captured_at=start + timedelta(days=1)))


def report(previous=(position(),), current=(position(),), offset=0):
    old, new = snapshots(previous, current, offset)
    return build_portfolio_change_report(old, new, generated_at=new.captured_at), old, new


def test_valid_report_owner_summary_and_frozen_dataclasses():
    item, _, _ = report()
    assert item.owner is PortfolioOwner.JOLIKA
    assert item.summary.unchanged == 1
    with pytest.raises(FrozenInstanceError):
        item.report_id = "x"
    with pytest.raises(FrozenInstanceError):
        item.summary.added = 2


def test_temporality_and_generated_at_validation():
    old, new = snapshots()
    with pytest.raises(ValueError):
        build_portfolio_change_report(new, old, generated_at=new.captured_at)
    with pytest.raises(ValueError):
        build_portfolio_change_report(old, new, generated_at=new.captured_at - timedelta(seconds=1))
    with pytest.raises(ValueError):
        build_portfolio_change_report(old, new, generated_at=datetime(2026, 1, 3))
    item = build_portfolio_change_report(old, new, generated_at=new.captured_at + timedelta(microseconds=2))
    assert item.generated_at.microsecond == 0 and item.generated_at.tzinfo is UTC


def test_determinism_and_material_or_generated_changes_change_id():
    first, old, new = report()
    assert first == build_portfolio_change_report(old, new, generated_at=new.captured_at)
    material, _, _ = report(current=(position(quantity="2", value="20"),))
    assert material.report_id != first.report_id
    later = build_portfolio_change_report(old, new, generated_at=new.captured_at + timedelta(seconds=1))
    assert later.report_id != first.report_id


def test_complete_summary_price_quantity_and_unknown():
    item, _, _ = report(
        previous=(position("UP"), position("DOWN", quantity="2"), position("PRICE"), position("NONE", quantity=None)),
        current=(position("UP", quantity="2", value="20"), position("DOWN", quantity="1"), position("PRICE", price="11", value="11"), position("NONE", quantity=None)),
    )
    assert item.summary.quantity_increased == 1
    assert item.summary.quantity_decreased == 1
    assert item.summary.market_value_changed == 2
    assert item.summary.unit_price_changed == 1
    assert item.summary.multiple_changes == 2
    assert item.summary.position_flow_unknown == 1
    price = next(delta for delta in item.change_set.deltas if delta.asset_name == "PRICE")
    assert PositionChangeType.MARKET_VALUE_CHANGED in price.change_types
    assert PositionChangeType.UNIT_PRICE_CHANGED in price.change_types
    assert PositionChangeType.QUANTITY_INCREASED not in price.change_types


def test_round_trip_newline_write_list_and_overwrite(tmp_path):
    item, _, _ = report()
    text = serialize_portfolio_change_report(item)
    assert text.endswith("\n") and ".0" not in text
    path = tmp_path / portfolio_change_report_filename(item)
    write_portfolio_change_report(item, output_path=path)
    assert load_portfolio_change_report(path) == item
    assert list_portfolio_change_reports(tmp_path) == (item,)
    with pytest.raises(FileExistsError):
        write_portfolio_change_report(item, output_path=path)
    write_portfolio_change_report(item, output_path=path, overwrite=True)
    assert list_portfolio_change_reports(tmp_path / "missing") == ()


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=2),
    lambda p: p.update(owner="NEI"),
    lambda p: p.update(current_captured_at=p["previous_captured_at"]),
    lambda p: p["summary"].update(unchanged=99),
    lambda p: p.update(previous_position_count=99),
    lambda p: p.update(report_id="tampered"),
    lambda p: p.update(extra=True),
    lambda p: p["change_set"]["deltas"][0].update(quantity_delta="NaN"),
    lambda p: p["change_set"]["deltas"][0].update(change_types=["bogus"]),
])
def test_loader_rejects_tampering(tmp_path, mutation):
    item, _, _ = report()
    payload = json.loads(serialize_portfolio_change_report(item))
    mutation(payload)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_portfolio_change_report(path)


def test_loader_rejects_invalid_json_missing_and_invalid_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_portfolio_change_report(tmp_path / "missing")
    for index, content in enumerate(("{", "[]")):
        path = tmp_path / str(index)
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            load_portfolio_change_report(path)


def test_lineage_valid_and_divergent():
    item, old, new = report()
    validate_portfolio_change_report_lineage(item, old, new)
    other, _ = snapshots(current=(position(quantity="2"),), offset=4)
    with pytest.raises(ValueError):
        validate_portfolio_change_report_lineage(item, old, other)


def test_sequence_continuous_unordered_gap_branch_and_duplicate():
    s1, s2 = snapshots()
    s3 = build_portfolio_snapshot((position(quantity="2", value="20"),), captured_at=s2.captured_at + timedelta(days=1))
    r12 = build_portfolio_change_report(s1, s2, generated_at=s2.captured_at)
    r23 = build_portfolio_change_report(s2, s3, generated_at=s3.captured_at)
    validate_portfolio_change_report_sequence(())
    validate_portfolio_change_report_sequence((r23, r12))
    with pytest.raises(ValueError):
        validate_portfolio_change_report_sequence((r12, r12))
    with pytest.raises(ValueError):
        validate_portfolio_change_report_sequence((r12, replace(r23, previous_snapshot_id="gap")))
    branch = build_portfolio_change_report(s1, s3, generated_at=s3.captured_at)
    with pytest.raises(ValueError):
        validate_portfolio_change_report_sequence((r12, branch))


def test_dda_multi_account_round_trip(tmp_path):
    positions = tuple(position("DDA CUSTODIAL CASH ACCOUNTS", account=account)
                      for account in ("115088644", "115099244", "115111355", "115111444"))
    item, _, _ = report(positions, positions)
    assert item.summary.unchanged == 4
    assert len({delta.current_instance_key for delta in item.change_set.deltas}) == 4
    path = tmp_path / "dda.json"
    path.write_text(serialize_portfolio_change_report(item), encoding="utf-8")
    assert load_portfolio_change_report(path) == item


def test_account_transfer_is_one_account_changed():
    item, _, _ = report((position(account="A"),), (position(account="B"),))
    assert len(item.change_set.deltas) == 1
    assert item.change_set.deltas[0].change_types == (PositionChangeType.ACCOUNT_CHANGED,)
    assert item.summary.added == item.summary.removed == 0
