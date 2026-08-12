from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_changes import PositionChangeType
from backend.portfolio_snapshots import (
    PORTFOLIO_SNAPSHOT_SCHEMA_VERSION,
    PortfolioSnapshot,
    build_portfolio_snapshot,
    compare_portfolio_snapshot_objects,
    compare_snapshot_to_positions,
    list_portfolio_snapshots,
    load_portfolio_snapshot,
    portfolio_snapshot_filename,
    select_previous_portfolio_snapshot,
    serialize_portfolio_snapshot,
    write_portfolio_snapshot,
)


def pos(
    name="A",
    institution="UBS",
    identifier="AAA",
    quantity="10",
    price="100",
    value="1000",
    account="1",
    owner=PortfolioOwner.JOLIKA,
    source_file="ubs.csv",
    reference_date=date(2026, 8, 12),
    economic=EconomicAssetClass.EQUITIES,
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=account,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=name,
        identifier=identifier,
        identifier_type="ticker",
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=None if price is None else Decimal(price),
        market_value=None if value is None else Decimal(value),
        currency="USD",
        portfolio_weight=Decimal("1"),
        reference_date=reference_date,
        source_file=source_file,
        economic_asset_class=economic,
    )


def captured(hour=12):
    return datetime(2026, 8, 12, hour, 0, tzinfo=timezone.utc)


def build(*positions, at=None):
    return build_portfolio_snapshot(positions, captured_at=at or captured())


def payload(snapshot):
    return json.loads(serialize_portfolio_snapshot(snapshot))


def test_build_valid_snapshot_and_derived_metadata():
    snapshot = build(
        pos(institution="UBS", source_file="ubs.csv"),
        pos(name="B", identifier="BBB", institution="Santander", source_file="santander.xlsx"),
    )
    assert snapshot.schema_version == PORTFOLIO_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.owner is PortfolioOwner.JOLIKA
    assert snapshot.institutions == ("SANTANDER", "UBS")
    assert snapshot.source_files == ("santander.xlsx", "ubs.csv")
    assert snapshot.reference_dates == ("2026-08-12",)
    assert snapshot.snapshot_id.startswith("JOLIKA|20260812T120000Z|")


def test_nei_and_mixed_rejected():
    with pytest.raises(ValueError):
        build(pos(owner=PortfolioOwner.NEI))
    with pytest.raises(ValueError):
        build(pos(), pos(identifier="B", owner=PortfolioOwner.NEI))


def test_empty_rejected():
    with pytest.raises(ValueError):
        build_portfolio_snapshot((), captured_at=captured())


def test_naive_captured_at_rejected():
    with pytest.raises(ValueError):
        build_portfolio_snapshot((pos(),), captured_at=datetime(2026, 8, 12, 12, 0))


def test_positions_sorted_and_input_not_mutated():
    original = [pos(name="B", identifier="B"), pos(name="A", identifier="A")]
    snapshot = build_portfolio_snapshot(original, captured_at=captured())
    assert [position.identifier for position in original] == ["B", "A"]
    assert [position.identifier for position in snapshot.positions] == ["A", "B"]


def test_duplicate_identity_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        build(pos(), replace(pos(), market_value=Decimal("2000")))


def test_source_file_must_be_basename():
    with pytest.raises(ValueError):
        build(pos(source_file="/tmp/ubs.csv"))
    with pytest.raises(ValueError):
        build(pos(source_file="folder/ubs.csv"))


def test_order_independent_snapshot_id_and_serialization():
    a = pos(identifier="A")
    b = pos(name="B", identifier="B", institution="Santander", source_file="s.xlsx")
    first = build(a, b)
    second = build(b, a)
    assert first == second
    assert serialize_portfolio_snapshot(first) == serialize_portfolio_snapshot(second)


def test_same_content_same_id():
    assert build(pos()).snapshot_id == build(pos()).snapshot_id


@pytest.mark.parametrize(
    "replacement",
    [
        {"quantity": Decimal("11")},
        {"market_value": Decimal("1100")},
        {"account": "2"},
        {"economic_asset_class": EconomicAssetClass.FIXED_INCOME},
        {"identifier": "DIFFERENT"},
        {"source_file": "other.csv"},
        {"portfolio_weight": Decimal("2")},
    ],
)
def test_material_position_change_changes_snapshot_id(replacement):
    baseline = pos()
    assert build(baseline).snapshot_id != build(replace(baseline, **replacement)).snapshot_id


def test_captured_at_changes_snapshot_id():
    assert build(pos(), at=captured(12)).snapshot_id != build(pos(), at=captured(13)).snapshot_id


def test_round_trip_preserves_types(tmp_path):
    original = build(pos())
    path = tmp_path / portfolio_snapshot_filename(original)
    path.write_text(serialize_portfolio_snapshot(original), encoding="utf-8")
    loaded = load_portfolio_snapshot(path)
    assert loaded == original
    position = loaded.positions[0]
    assert isinstance(position.quantity, Decimal)
    assert position.owner is PortfolioOwner.JOLIKA
    assert position.economic_asset_class is EconomicAssetClass.EQUITIES
    assert isinstance(position.reference_date, date)
    assert loaded.captured_at.tzinfo is not None


def test_serialization_is_deterministic_and_has_newline():
    snapshot = build(pos())
    first = serialize_portfolio_snapshot(snapshot)
    assert first == serialize_portfolio_snapshot(snapshot)
    assert first.endswith("\n")


def _write_payload(tmp_path, data, name="jolika_20260812T120000Z_0000000000000000.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_invalid_json_and_schema_fail_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_portfolio_snapshot(bad)
    data = payload(build(pos()))
    data["schema_version"] = 99
    with pytest.raises(ValueError):
        load_portfolio_snapshot(_write_payload(tmp_path, data))


def test_invalid_owner_decimal_enum_and_date_fail_closed(tmp_path):
    base = payload(build(pos()))
    for field, value in (
        ("owner", "NEI"),
        ("quantity", "NaN"),
        ("economic_asset_class", "INVALID"),
        ("reference_date", "not-a-date"),
    ):
        data = json.loads(json.dumps(base))
        if field == "owner":
            data[field] = value
        else:
            data["positions"][0][field] = value
        with pytest.raises(ValueError):
            load_portfolio_snapshot(_write_payload(tmp_path, data, name=f"jolika_20260812T120000Z_{field[:16].ljust(16, '0')}.json"))


def test_duplicate_identity_in_loaded_snapshot_rejected(tmp_path):
    data = payload(build(pos()))
    data["positions"].append(dict(data["positions"][0]))
    with pytest.raises(ValueError):
        load_portfolio_snapshot(_write_payload(tmp_path, data))


def test_tampered_snapshot_id_source_files_and_institutions_rejected(tmp_path):
    base = payload(build(pos()))
    mutations = (
        ("snapshot_id", "JOLIKA|20260812T120000Z|0000000000000000"),
        ("source_files", ["fake.csv"]),
        ("institutions", ["SANTANDER"]),
    )
    for index, (field, value) in enumerate(mutations):
        data = json.loads(json.dumps(base))
        data[field] = value
        with pytest.raises(ValueError):
            load_portfolio_snapshot(_write_payload(tmp_path, data, name=f"jolika_20260812T12000{index}Z_{index:016x}.json"))


def test_unexpected_root_and_position_fields_rejected(tmp_path):
    data = payload(build(pos()))
    data["extra"] = True
    with pytest.raises(ValueError):
        load_portfolio_snapshot(_write_payload(tmp_path, data))
    data = payload(build(pos()))
    data["positions"][0]["extra"] = True
    with pytest.raises(ValueError):
        load_portfolio_snapshot(_write_payload(tmp_path, data, name="jolika_20260812T120001Z_1111111111111111.json"))


def test_write_explicit_creates_parent_and_round_trips(tmp_path):
    snapshot = build(pos())
    directory = tmp_path / "nested"
    path = directory / portfolio_snapshot_filename(snapshot)
    assert not directory.exists()
    write_portfolio_snapshot(snapshot, output_path=path)
    assert directory.is_dir()
    assert load_portfolio_snapshot(path) == snapshot


def test_write_refuses_overwrite_unless_explicit(tmp_path):
    snapshot = build(pos())
    path = tmp_path / portfolio_snapshot_filename(snapshot)
    write_portfolio_snapshot(snapshot, output_path=path)
    with pytest.raises(FileExistsError):
        write_portfolio_snapshot(snapshot, output_path=path)
    write_portfolio_snapshot(snapshot, output_path=path, overwrite=True)
    assert load_portfolio_snapshot(path) == snapshot


def test_filename_is_safe_deterministic_basename():
    snapshot = build(pos())
    filename = portfolio_snapshot_filename(snapshot)
    assert filename.startswith("jolika_20260812T120000Z_")
    assert filename.endswith(".json")
    assert "/" not in filename and "\\" not in filename


def test_list_empty_missing_and_ignores_unrelated(tmp_path):
    assert list_portfolio_snapshots(tmp_path / "missing") == ()
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    assert list_portfolio_snapshots(tmp_path) == ()


def test_list_multiple_sorted_and_immutable(tmp_path):
    later = build(pos(), at=captured(14))
    earlier = build(pos(), at=captured(12))
    for snapshot in (later, earlier):
        write_portfolio_snapshot(snapshot, output_path=tmp_path / portfolio_snapshot_filename(snapshot))
    listed = list_portfolio_snapshots(tmp_path)
    assert isinstance(listed, tuple)
    assert listed == (earlier, later)


def test_list_candidate_corruption_fails(tmp_path):
    snapshot = build(pos())
    path = tmp_path / portfolio_snapshot_filename(snapshot)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        list_portfolio_snapshots(tmp_path)


def test_select_previous_strict_and_order_independent():
    t1 = build(pos(), at=captured(10))
    t2 = build(pos(), at=captured(11))
    t3 = build(pos(), at=captured(12))
    assert select_previous_portfolio_snapshot((t3, t1, t2), before=captured(12)) == t2
    assert select_previous_portfolio_snapshot((t2, t3, t1), before=captured(13)) == t3
    assert select_previous_portfolio_snapshot((t1, t2, t3), before=captured(10)) is None


def test_select_previous_rejects_naive_before():
    with pytest.raises(ValueError):
        select_previous_portfolio_snapshot((build(pos()),), before=datetime(2026, 8, 13))


def test_select_previous_rejects_ambiguous_timestamp():
    first = build(pos(identifier="A"), at=captured())
    second = build(pos(identifier="B"), at=captured())
    with pytest.raises(ValueError, match="Ambiguous"):
        select_previous_portfolio_snapshot((first, second), before=captured() + timedelta(hours=1))


def test_no_baseline_returns_none():
    assert compare_snapshot_to_positions(None, (pos(),)) is None


def test_persisted_integration_with_phase_24(tmp_path):
    first = build(
        pos(identifier="A", quantity="10", institution="UBS", source_file="ubs.csv"),
        pos(identifier="B", quantity="20", institution="Santander", source_file="s.xlsx"),
        at=captured(10),
    )
    second = build(
        pos(identifier="A", quantity="15", institution="UBS", source_file="ubs.csv"),
        pos(identifier="B", quantity="20", institution="Santander", source_file="s.xlsx"),
        pos(identifier="C", quantity="5", institution="Santander", source_file="s.xlsx"),
        at=captured(11),
    )
    for snapshot in (first, second):
        write_portfolio_snapshot(snapshot, output_path=tmp_path / portfolio_snapshot_filename(snapshot))
    loaded = list_portfolio_snapshots(tmp_path)
    baseline = select_previous_portfolio_snapshot(loaded, before=second.captured_at)
    changes = compare_portfolio_snapshot_objects(baseline, loaded[-1])
    by_id = {delta.identifier: delta for delta in changes.deltas}
    assert PositionChangeType.QUANTITY_INCREASED in by_id["A"].change_types
    assert PositionChangeType.UNCHANGED in by_id["B"].change_types
    assert PositionChangeType.ADDED in by_id["C"].change_types


def test_account_transfer_survives_round_trip(tmp_path):
    previous = build(pos(account="A"), at=captured(10))
    current = build(pos(account="B"), at=captured(11))
    paths = []
    for snapshot in (previous, current):
        path = tmp_path / portfolio_snapshot_filename(snapshot)
        write_portfolio_snapshot(snapshot, output_path=path)
        paths.append(path)
    changes = compare_portfolio_snapshot_objects(
        load_portfolio_snapshot(paths[0]), load_portfolio_snapshot(paths[1])
    )
    assert PositionChangeType.ACCOUNT_CHANGED in changes.deltas[0].change_types
    assert PositionChangeType.ADDED not in changes.deltas[0].change_types
    assert PositionChangeType.REMOVED not in changes.deltas[0].change_types


def test_price_only_change_survives_round_trip(tmp_path):
    previous = build(pos(quantity="10", price="100", value="1000"), at=captured(10))
    current = build(pos(quantity="10", price="120", value="1200"), at=captured(11))
    paths = []
    for snapshot in (previous, current):
        path = tmp_path / portfolio_snapshot_filename(snapshot)
        write_portfolio_snapshot(snapshot, output_path=path)
        paths.append(path)
    changes = compare_portfolio_snapshot_objects(
        load_portfolio_snapshot(paths[0]), load_portfolio_snapshot(paths[1])
    )
    delta = changes.deltas[0]
    assert PositionChangeType.QUANTITY_INCREASED not in delta.change_types
    assert PositionChangeType.QUANTITY_DECREASED not in delta.change_types
    assert delta.market_value_delta == Decimal("200")
    assert delta.unit_price_delta == Decimal("20")
