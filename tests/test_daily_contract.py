"""Compatibility tests for the versioned public daily contract."""

from dataclasses import replace
from datetime import date
from typing import Any, cast

import pytest

from backend.daily_contract import (
    CONTRACT_VERSION,
    DailyApiRequest,
    DailyApiResponse,
    validate_daily_api_request,
    validate_daily_api_response_payload,
)


def test_contract_has_one_documented_official_version() -> None:
    assert CONTRACT_VERSION == "1.0"


def test_empty_request_is_valid() -> None:
    assert validate_daily_api_request(DailyApiRequest((), ()))


@pytest.mark.parametrize(
    "candidate",
    (
        object(),
        DailyApiRequest(cast(Any, []), ()),
        DailyApiRequest((), cast(Any, [])),
        DailyApiRequest((), (), cast(Any, "2026-07-30")),
        DailyApiRequest((), (), date(2026, 7, 30), cast(Any, [])),
    ),
)
def test_request_rejects_invalid_types(candidate: object) -> None:
    assert not validate_daily_api_request(candidate)


def _valid_response_payload() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "SUCCESS",
        "generated_at": "2026-07-30T12:00:00+00:00",
        "experience_status": "READY",
        "header": {},
        "message": {},
        "facts": [],
        "priorities": [],
        "analyses": [],
        "blocks": [],
        "summary": {},
        "error": None,
    }


def test_response_payload_is_valid_and_versioned() -> None:
    payload = _valid_response_payload()
    assert payload["contract_version"] == CONTRACT_VERSION
    assert validate_daily_api_response_payload(payload)


def test_response_rejects_missing_required_field() -> None:
    payload = _valid_response_payload()
    del payload["summary"]
    assert not validate_daily_api_response_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    (("status", "UNKNOWN"), ("experience_status", "UNKNOWN")),
)
def test_response_rejects_invalid_enums(field: str, value: object) -> None:
    payload = _valid_response_payload()
    payload[field] = value
    assert not validate_daily_api_response_payload(payload)


def test_response_rejects_an_incompatible_version() -> None:
    payload = _valid_response_payload()
    payload["contract_version"] = "2.0"
    assert not validate_daily_api_response_payload(payload)


def test_response_object_rejects_an_incompatible_version() -> None:
    from backend.daily_api import DailyApiFacade

    response = DailyApiFacade().execute(DailyApiRequest((), ()))
    with pytest.raises(ValueError, match="contract_version"):
        replace(cast(DailyApiResponse, response), contract_version="2.0")
