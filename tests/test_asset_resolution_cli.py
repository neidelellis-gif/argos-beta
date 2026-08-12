import json
import subprocess
import sys

from backend.asset_resolution import collect_unresolved_jolika_assets, export_unresolved_jolika_assets
from backend.models import PortfolioOwner, PortfolioPosition
from decimal import Decimal


def position():
    return PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class="ETF",
        asset_subclass=None,
        asset_name="Future Asset",
        identifier="FUTURE-CLI",
        identifier_type="ticker",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="future.csv",
        economic_asset_class=None,
    )


def prepare(tmp_path):
    unresolved = tmp_path / "unresolved.json"
    decisions = tmp_path / "decisions.json"
    registry = tmp_path / "registry.json"
    stable_key = collect_unresolved_jolika_assets((position(),))[0].stable_key
    export_unresolved_jolika_assets(
        collect_unresolved_jolika_assets((position(),)),
        output_path=unresolved,
    )
    decisions.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "decisions": [
                    {
                        "stable_key": stable_key,
                        "economic_asset_class": "Renda Fixa",
                        "status": "confirmed",
                        "resolution_source": "human_review",
                        "note": "reviewed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry.write_text(
        json.dumps({"schema_version": 1, "resolutions": []}),
        encoding="utf-8",
    )
    return unresolved, decisions, registry


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "backend.asset_resolution_cli", *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_validate_returns_zero_and_writes_nothing(tmp_path):
    unresolved, decisions, registry = prepare(tmp_path)
    before = set(tmp_path.iterdir())
    result = run_cli(
        "validate",
        "--unresolved",
        unresolved,
        "--decisions",
        decisions,
        "--registry",
        registry,
    )
    assert result.returncode == 0
    assert set(tmp_path.iterdir()) == before


def test_validate_rejects_invalid_decision(tmp_path):
    unresolved, decisions, registry = prepare(tmp_path)
    payload = json.loads(decisions.read_text())
    payload["decisions"][0]["resolution_source"] = "automatic"
    decisions.write_text(json.dumps(payload), encoding="utf-8")
    result = run_cli(
        "validate",
        "--unresolved",
        unresolved,
        "--decisions",
        decisions,
        "--registry",
        registry,
    )
    assert result.returncode != 0


def test_build_creates_proposed_registry_without_touching_original(tmp_path):
    unresolved, decisions, registry = prepare(tmp_path)
    original = registry.read_bytes()
    output = tmp_path / "proposed.json"
    result = run_cli(
        "build",
        "--unresolved",
        unresolved,
        "--decisions",
        decisions,
        "--registry",
        registry,
        "--output",
        output,
    )
    assert result.returncode == 0
    assert output.exists()
    assert registry.read_bytes() == original
    payload = json.loads(output.read_text())
    assert payload["schema_version"] == 1
    assert len(payload["resolutions"]) == 1


def test_build_refuses_existing_output_without_overwrite(tmp_path):
    unresolved, decisions, registry = prepare(tmp_path)
    output = tmp_path / "proposed.json"
    output.write_text("sentinel", encoding="utf-8")
    result = run_cli(
        "build",
        "--unresolved",
        unresolved,
        "--decisions",
        decisions,
        "--registry",
        registry,
        "--output",
        output,
    )
    assert result.returncode != 0
    assert output.read_text() == "sentinel"


def test_build_allows_explicit_overwrite(tmp_path):
    unresolved, decisions, registry = prepare(tmp_path)
    output = tmp_path / "proposed.json"
    output.write_text("sentinel", encoding="utf-8")
    result = run_cli(
        "build",
        "--unresolved",
        unresolved,
        "--decisions",
        decisions,
        "--registry",
        registry,
        "--output",
        output,
        "--overwrite",
    )
    assert result.returncode == 0
    assert json.loads(output.read_text())["schema_version"] == 1


def test_missing_arguments_fail(tmp_path):
    result = run_cli("validate")
    assert result.returncode != 0
