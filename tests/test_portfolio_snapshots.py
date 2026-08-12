from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_changes import PositionChangeType, position_instance_identity
from backend.portfolio_snapshots import (
    PORTFOLIO_SNAPSHOT_SCHEMA_VERSION,
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
    identifier_type="ticker",
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
        identifier_type=identifier_type,
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
        pos(institution="UBS", source_file="folder/ubs.csv"),
        pos(
            name="B",
            identifier="BBB",
            institution="Santander",
            source_file=r"C:\exports\santander.xlsx",
        ),
    )
    assert snapshot.schema_version == PORTFOLIO_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.owner is PortfolioOwner.JOLIKA
    assert snapshot.institutions == ("SANTANDER", "UBS")
    assert snapshot.source_files == ("santander.xlsx", "ubs.csv")
    assert snapshot.reference_dates == ("2026-08-12",)
    assert snapshot.snapshot_id.startswith("JOLIKA|20260812T120000Z|")


def test_nei_mixed_empty_and_naive_rejected():
    with pytest.raises(ValueError):
        build(pos(owner=PortfolioOwner.NEI))
    with pytest.raises(ValueError):
        build(pos(), pos(identifier="B", owner=PortfolioOwner.NEI))
    with pytest.raises(ValueError):
        build_portfolio_snapshot((), captured_at=captured())
    with pytest.raises(ValueError):
        build_portfolio_snapshot((pos(),), captured_at=datetime(2026, 8, 12, 12))


def test_positions_sorted_by_instance_identity_and_input_not_mutated():
    original = [pos(identifier="A", account="2"), pos(identifier="A", account="1")]
    snapshot = build_portfolio_snapshot(original, captured_at=captured())
    assert [p.account for p in original] == ["2", "1"]
    assert [p.account for p in snapshot.positions] == ["1", "2"]


def test_multi_account_is_valid_and_same_instance_is_duplicate():
    a = pos(identifier="A", account="1")
    b = pos(identifier="A", account="2")
    snapshot = build(a, b)
    assert len(snapshot.positions) == 2
    with pytest.raises(ValueError, match="Duplicate"):
        build(a, replace(a, market_value=Decimal("2000")))


def test_account_none_policy():
    none = pos(identifier="A", account=None)
    known = pos(identifier="A", account="1")
    assert len(build(none, known).positions) == 2
    with pytest.raises(ValueError, match="Duplicate"):
        build(none, replace(none, market_value=Decimal("1")))


def test_order_independent_snapshot_id_and_serialization():
    a = pos(identifier="A", account="1")
    b = pos(identifier="A", account="2")
    first = build(a, b)
    second = build(b, a)
    assert first == second
    assert serialize_portfolio_snapshot(first) == serialize_portfolio_snapshot(second)


@pytest.mark.parametrize(
    "replacement",
    [
        {"quantity": Decimal("11")},
        {"market_value": Decimal("1100")},
        {"unit_price": Decimal("110")},
        {"account": "2"},
        {"economic_asset_class": EconomicAssetClass.FIXED_INCOME},
        {"asset_class": "Bond"},
        {"identifier": "DIFFERENT"},
        {"identifier_type": "CUSIP"},
        {"source_file": "other.csv"},
        {"reference_date": date(2026, 8, 13)},
        {"portfolio_weight": Decimal("2")},
    ],
)
def test_material_change_changes_snapshot_id(replacement):
    baseline = pos()
    assert build(baseline).snapshot_id != build(replace(baseline, **replacement)).snapshot_id


def test_captured_at_normalizes_utc_and_changes_id():
    offset = timezone(timedelta(hours=-3))
    local = datetime(2026, 8, 12, 9, 0, tzinfo=offset)
    assert build(pos(), at=local).captured_at == captured(12)
    assert build(pos(), at=captured(12)).snapshot_id != build(pos(), at=captured(13)).snapshot_id


def test_round_trip_preserves_types_and_newline(tmp_path):
    original = build(pos())
    text = serialize_portfolio_snapshot(original)
    assert text.endswith("\n")
    path = tmp_path / portfolio_snapshot_filename(original)
    path.write_text(text, encoding="utf-8")
    loaded = load_portfolio_snapshot(path)
    assert loaded == original
    p = loaded.positions[0]
    assert isinstance(p.quantity, Decimal)
    assert p.owner is PortfolioOwner.JOLIKA
    assert p.economic_asset_class is EconomicAssetClass.EQUITIES
    assert isinstance(p.reference_date, date)
    assert loaded.captured_at.tzinfo is not None


def _write_payload(tmp_path, data, name="jolika_20260812T120000Z_0000000000000000.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loader_fail_closed_for_json_schema_owner_decimal_enum_and_extra(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_portfolio_snapshot(bad)
    base = payload(build(pos()))
    mutations = []
    data = json.loads(json.dumps(base)); data["schema_version"] = 99; mutations.append(data)
    data = json.loads(json.dumps(base)); data["owner"] = "NEI"; mutations.append(data)
    data = json.loads(json.dumps(base)); data["positions"][0]["quantity"] = "NaN"; mutations.append(data)
    data = json.loads(json.dumps(base)); data["positions"][0]["economic_asset_class"] = "INVALID"; mutations.append(data)
    data = json.loads(json.dumps(base)); data["extra"] = True; mutations.append(data)
    for index, data in enumerate(mutations):
        with pytest.raises(ValueError):
            load_portfolio_snapshot(
                _write_payload(
                    tmp_path,
                    data,
                    name=f"jolika_20260812T12000{index}Z_{index:016x}.json",
                )
            )


def test_loader_rejects_duplicate_instance_and_tampered_metadata(tmp_path):
    base = payload(build(pos()))
    duplicate = json.loads(json.dumps(base))
    duplicate["positions"].append(dict(duplicate["positions"][0]))
    with pytest.raises(ValueError):
        load_portfolio_snapshot(_write_payload(tmp_path, duplicate))
    for index, (field, value) in enumerate(
        (
            ("snapshot_id", "JOLIKA|20260812T120000Z|0000000000000000"),
            ("source_files", ["fake.csv"]),
            ("institutions", ["SANTANDER"]),
            ("reference_dates", ["2026-08-11"]),
        )
    ):
        data = json.loads(json.dumps(base))
        data[field] = value
        with pytest.raises(ValueError):
            load_portfolio_snapshot(
                _write_payload(
                    tmp_path,
                    data,
                    name=f"jolika_20260812T12001{index}Z_{index + 10:016x}.json",
                )
            )


def test_write_explicit_overwrite_and_parent_creation(tmp_path):
    snapshot = build(pos())
    path = tmp_path / "nested" / portfolio_snapshot_filename(snapshot)
    assert not path.parent.exists()
    write_portfolio_snapshot(snapshot, output_path=path)
    assert load_portfolio_snapshot(path) == snapshot
    with pytest.raises(FileExistsError):
        write_portfolio_snapshot(snapshot, output_path=path)
    write_portfolio_snapshot(snapshot, output_path=path, overwrite=True)
    assert load_portfolio_snapshot(path) == snapshot


def test_filename_and_listing(tmp_path):
    assert list_portfolio_snapshots(tmp_path / "missing") == ()
    earlier = build(pos(), at=captured(10))
    later = build(pos(), at=captured(12))
    for snapshot in (later, earlier):
        write_portfolio_snapshot(
            snapshot,
            output_path=tmp_path / portfolio_snapshot_filename(snapshot),
        )
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    assert list_portfolio_snapshots(tmp_path) == (earlier, later)


def test_listing_candidate_corruption_fails(tmp_path):
    snapshot = build(pos())
    path = tmp_path / portfolio_snapshot_filename(snapshot)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        list_portfolio_snapshots(tmp_path)


def test_select_previous_strict_order_independent_and_ambiguous():
    t1 = build(pos(), at=captured(10))
    t2 = build(pos(), at=captured(11))
    t3 = build(pos(), at=captured(12))
    assert select_previous_portfolio_snapshot((t3, t1, t2), before=captured(12)) == t2
    assert select_previous_portfolio_snapshot((t2, t3, t1), before=captured(13)) == t3
    assert select_previous_portfolio_snapshot((t1, t2, t3), before=captured(10)) is None
    other = build(pos(identifier="B"), at=captured(12))
    with pytest.raises(ValueError, match="Ambiguous"):
        select_previous_portfolio_snapshot((t3, other), before=captured(13))
    with pytest.raises(ValueError):
        select_previous_portfolio_snapshot((t1,), before=datetime(2026, 8, 13))


def test_no_baseline_returns_none():
    assert compare_snapshot_to_positions(None, (pos(),)) is None


def test_multi_institution_integration():
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
    changes = compare_portfolio_snapshot_objects(first, second)
    by_id = {delta.identifier: delta for delta in changes.deltas}
    assert PositionChangeType.QUANTITY_INCREASED in by_id["A"].change_types
    assert PositionChangeType.UNCHANGED in by_id["B"].change_types
    assert PositionChangeType.ADDED in by_id["C"].change_types


def test_account_transfer_price_only_and_quantity_none_survive_round_trip(tmp_path):
    cases = [
        (
            build(pos(account="A"), at=captured(10)),
            build(pos(account="B"), at=captured(11)),
            PositionChangeType.ACCOUNT_CHANGED,
        ),
        (
            build(pos(quantity="10", price="100", value="1000"), at=captured(10)),
            build(pos(quantity="10", price="120", value="1200"), at=captured(11)),
            PositionChangeType.MARKET_VALUE_CHANGED,
        ),
        (
            build(pos(quantity=None, value="1000"), at=captured(10)),
            build(pos(quantity=None, value="1500"), at=captured(11)),
            PositionChangeType.MARKET_VALUE_CHANGED,
        ),
    ]
    for index, (previous, current, expected) in enumerate(cases):
        loaded = []
        for j, snapshot in enumerate((previous, current)):
            path = tmp_path / f"{index}-{j}-{portfolio_snapshot_filename(snapshot)}"
            write_portfolio_snapshot(snapshot, output_path=path)
            loaded.append(load_portfolio_snapshot(path))
        delta = compare_portfolio_snapshot_objects(*loaded).deltas[0]
        assert expected in delta.change_types
        if index == 0:
            assert PositionChangeType.ADDED not in delta.change_types
            assert PositionChangeType.REMOVED not in delta.change_types
        elif index == 1:
            assert delta.unit_price_delta == Decimal("20")
            assert delta.market_value_delta == Decimal("200")
            assert PositionChangeType.QUANTITY_INCREASED not in delta.change_types
        else:
            assert delta.position_flow_unknown is True


def test_multi_account_ambiguity_remains_conservative():
    previous = build(pos(identifier="X", account="A"), pos(identifier="X", account="B"), at=captured(10))
    current = build(pos(identifier="X", account="C"), pos(identifier="X", account="D"), at=captured(11))
    changes = compare_portfolio_snapshot_objects(previous, current)
    assert changes.removed_count == 2
    assert changes.added_count == 2
    assert changes.account_changed_count == 0


def test_real_santander_dda_shape_round_trip(tmp_path):
    accounts = ("115099244", "115111355", "115111444", "115088644")
    values = ("0", "0", "0", "350")
    positions = tuple(
        pos(
            name="DDA CUSTODIAL CASH ACCOUNTS",
            institution="Santander",
            identifier="DDA CUSTODIAL CASH ACCOUNTS",
            identifier_type=None,
            quantity=None,
            price=None,
            value=value,
            account=account,
            source_file="your-positions-4005106-39.xlsx",
        )
        for account, value in zip(accounts, values)
    )
    first = build(*positions)
    second = build(*reversed(positions))
    assert first == second
    assert len(first.positions) == 4
    assert len({position_instance_identity(p).instance_key for p in first.positions}) == 4
    path = tmp_path / portfolio_snapshot_filename(first)
    write_portfolio_snapshot(first, output_path=path)
    loaded = load_portfolio_snapshot(path)
    assert len(loaded.positions) == 4
    changes = compare_portfolio_snapshot_objects(loaded, loaded)
    assert changes.unchanged_count == 4
    assert changes.added_count == 0
    assert changes.removed_count == 0
    assert changes.account_changed_count == 0
