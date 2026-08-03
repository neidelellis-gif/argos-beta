"""Real-operation coverage for the official portfolio repository."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import cast

import pytest

from backend.daily_api import DailyApiFacade, DailyApiRequest, DailyApiStatus
from backend.data_quality_engine import DataQualityEngine
from backend.models import PortfolioOwner
from backend.official_portfolios import (
    DEFAULT_PORTFOLIO_ROOT, OfficialPortfolioLoader, OfficialPortfolioValidationError,
)


REFERENCE = date(2026, 7, 30)


def test_loads_personal_official_portfolio() -> None:
    portfolio = OfficialPortfolioLoader().load(DEFAULT_PORTFOLIO_ROOT / "personal" / "bradesco.json")

    assert portfolio.portfolio_type == "PERSONAL"
    assert portfolio.base_currency == "BRL"
    assert {item.owner for item in portfolio.positions} == {PortfolioOwner.NEI}


def test_loads_jolika_institutions_separately() -> None:
    loader = OfficialPortfolioLoader()
    ubs = loader.load(DEFAULT_PORTFOLIO_ROOT / "jolika" / "ubs.json")
    santander = loader.load(DEFAULT_PORTFOLIO_ROOT / "jolika" / "santander.json")

    assert ubs.portfolio_id != santander.portfolio_id
    assert {ubs.institution, santander.institution} == {"UBS", "Santander"}
    assert all(item.owner is PortfolioOwner.JOLIKA for item in ubs.positions + santander.positions)


def test_all_official_portfolios_coexist_without_owner_leakage() -> None:
    portfolios = OfficialPortfolioLoader().load_all()
    personal = tuple(item for item in portfolios if item.portfolio_type == "PERSONAL")
    company = tuple(item for item in portfolios if item.portfolio_type == "COMPANY")

    assert len(personal) == 1
    assert len(company) == 2
    assert {position.owner for item in personal for position in item.positions} == {PortfolioOwner.NEI}
    assert {position.owner for item in company for position in item.positions} == {PortfolioOwner.JOLIKA}


def _write(root: Path, payload: object, name: str = "portfolio.json") -> Path:
    directory = root / "personal"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_payload() -> dict[str, object]:
    return json.loads((DEFAULT_PORTFOLIO_ROOT / "personal" / "bradesco.json").read_text())


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    (
        (lambda value: value.update(base_currency=""), "portfolio.missing_currency"),
        (lambda value: value.update(institution=""), "portfolio.missing_institution"),
        (lambda value: value.update(reference_date="30/07/2026"), "portfolio.invalid_date"),
        (lambda value: value.update(positions=[]), "portfolio.missing"),
    ),
)
def test_rejects_missing_or_invalid_data(tmp_path: Path, mutation: object, diagnostic: str) -> None:
    payload = _valid_payload()
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(OfficialPortfolioValidationError) as caught:
        OfficialPortfolioLoader(tmp_path).load(_write(tmp_path, payload))
    assert caught.value.diagnostic_id == diagnostic


def test_rejects_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(OfficialPortfolioValidationError, match="inválido") as caught:
        OfficialPortfolioLoader(tmp_path).load(path)
    assert caught.value.diagnostic_id == "portfolio.invalid"


def test_rejects_duplicate_portfolio_and_position_identifiers(tmp_path: Path) -> None:
    first = _valid_payload()
    second = _valid_payload()
    _write(tmp_path, first, "first.json")
    _write(tmp_path, second, "second.json")
    with pytest.raises(OfficialPortfolioValidationError) as caught:
        OfficialPortfolioLoader(tmp_path).load_all()
    assert caught.value.diagnostic_id == "portfolio.duplicates"

    duplicate_position = _valid_payload()
    duplicate_position["positions"] = duplicate_position["positions"] * 2  # type: ignore[operator]
    with pytest.raises(OfficialPortfolioValidationError) as position_caught:
        OfficialPortfolioLoader(tmp_path).load(_write(tmp_path / "other", duplicate_position))
    assert position_caught.value.diagnostic_id == "portfolio.duplicates"


def test_official_positions_pass_data_quality_and_complete_daily_flow() -> None:
    positions = OfficialPortfolioLoader().load_positions()
    quality = DataQualityEngine().diagnose(positions, (), None, REFERENCE)
    response = DailyApiFacade(clock=lambda: datetime(2026, 7, 30, 12, tzinfo=timezone.utc)).execute(
        DailyApiRequest(positions=positions, fact_candidates=(), reference_date=REFERENCE)
    )

    diagnostics = cast(list[dict[str, object]], quality["diagnostics"])
    portfolio_errors = [
        item for item in diagnostics
        if item["category"] == "PORTFOLIO" and item["severity"] == "ERROR"
    ]
    assert portfolio_errors == []
    assert response.status is DailyApiStatus.SUCCESS
    assert response.data_quality is not None
