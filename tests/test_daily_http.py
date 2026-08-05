"""Contract and routing tests for the official daily HTTP adapter."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
from collections.abc import Iterator
from types import MappingProxyType
from typing import cast

import pytest

import backend.server as server_module
from backend.daily_api import (
    DailyApiError,
    DailyApiErrorCode,
    DailyApiFacade,
    DailyApiRequest,
    DailyApiResponse,
    DailyApiStatus,
)
from backend.daily_experience import DailyExperienceComposer
from backend.daily_http import (
    MAX_DAILY_REQUEST_BYTES,
    DailyHttpAdapter,
    DailyHttpResponse,
)
from backend.daily_orchestrator import DailyOrchestrator
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityEngine
from backend.important_facts import ImportantFactsEngine
from backend.portfolio_impact import PortfolioImpactEngine
from backend.server import ArgosRequestHandler


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def _position(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "institution": "UBS", "owner": "JOLIKA", "account": "test",
        "asset_class": "Equities", "asset_subclass": "Technology",
        "asset_name": "ARGOS1", "identifier": "ARGOS1",
        "identifier_type": "TICKER", "quantity": "2", "unit_price": "10.25",
        "market_value": "20.50", "currency": "USD", "portfolio_weight": None,
        "reference_date": "2026-07-30", "source_file": "private.csv",
    }
    value.update(changes)
    return value


def _fact(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "fact-1", "title": "Market fact", "description": "Evidence",
        "source": "Source", "published_at": "2026-07-30T11:00:00+00:00",
        "importance": "HIGH", "category": "MARKETS", "urgency": "HIGH",
        "related_assets": [], "related_sectors": [], "related_currencies": ["USD"],
        "related_institutions": ["UBS"],
    }
    value.update(changes)
    return value


def _payload(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "positions": [_position()], "fact_candidates": [_fact()],
        "reference_date": "2026-07-30",
    }
    value.update(changes)
    return value


def _body(payload: object | None = None) -> bytes:
    return json.dumps(_payload() if payload is None else payload).encode()


def _facade() -> DailyApiFacade:
    orchestrator = DailyOrchestrator(
        DailyPortfolioSnapshotBuilder(clock=lambda: NOW),
        ImportantFactsEngine(clock=lambda: NOW),
        PortfolioImpactEngine(clock=lambda: NOW),
        DailyPriorityEngine(clock=lambda: NOW),
        clock=lambda: NOW,
    )
    return DailyApiFacade(
        orchestrator, DailyExperienceComposer(clock=lambda: NOW), lambda: NOW
    )


def _adapter() -> DailyHttpAdapter:
    return DailyHttpAdapter(_facade())


def _post(adapter: DailyHttpAdapter, body: bytes | None = None, content_type: str = "application/json") -> DailyHttpResponse:
    return adapter.handle("POST", {"Content-Type": content_type}, _body() if body is None else body)


def _decoded(response: DailyHttpResponse) -> dict[str, object]:
    value = json.loads(response.body.decode("utf-8"))
    assert isinstance(value, dict)
    return value


def _error_code(response: DailyHttpResponse) -> object:
    error = _decoded(response)["error"]
    assert isinstance(error, dict)
    return error["code"]


def test_valid_post_executes_real_complete_flow() -> None:
    response = _post(_adapter())
    payload = _decoded(response)

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store"
    assert payload["status"] == "SUCCESS"
    assert payload["generated_at"] == "2026-07-30T12:00:00+00:00"
    assert payload["experience_status"] == "DECISION_REQUIRED"
    assert payload["contract_version"] == "1.5"
    assert payload["experience"] == {"status": "READY"}
    assert payload["error"] is None
    priorities = cast(list[dict[str, object]], payload["priorities"])
    analyses = cast(list[dict[str, object]], payload["analyses"])
    assert len(priorities) <= 2
    analysis_ids = {item["fact_id"] for item in analyses}
    assert analysis_ids
    assert all(item["fact_id"] in analysis_ids for item in priorities)


def test_null_reference_date_executes_real_complete_flow() -> None:
    response = _post(_adapter(), _body(_payload(reference_date=None)))
    payload = _decoded(response)

    assert response.status_code == 200
    assert payload["status"] == "SUCCESS"
    header = cast(dict[str, object], payload["header"])
    assert header["display_date"] == "quinta-feira, 30 de julho de 2026"
    assert payload["error"] is None


@pytest.mark.parametrize("method", ("GET", "PUT"))
def test_non_post_methods_are_rejected_without_facade_execution(method: str) -> None:
    class FailingFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            raise AssertionError("facade must not execute")

    response = DailyHttpAdapter(FailingFacade()).handle(method, {}, b"")
    assert response.status_code == 405
    assert response.headers["Allow"] == "POST"
    assert _decoded(response)["error"] == {
        "code": "METHOD_NOT_ALLOWED", "message": "Método HTTP não permitido.",
        "stage": "HTTP",
    }


@pytest.mark.parametrize("headers", ({}, {"Content-Type": "text/plain"}))
def test_missing_or_non_json_content_type_is_rejected(headers: dict[str, str]) -> None:
    response = _adapter().handle("POST", headers, _body())
    assert response.status_code == 415
    assert _error_code(response) == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.parametrize("content_type", ("application/json", "application/json; charset=utf-8", "Application/JSON; Charset=UTF-8"))
def test_json_content_types_are_accepted(content_type: str) -> None:
    assert _post(_adapter(), content_type=content_type).status_code == 200


@pytest.mark.parametrize(
    ("body", "code"),
    ((b"", "INVALID_JSON"), (b"  \n", "INVALID_JSON"), (b"\xff", "INVALID_ENCODING"), (b"{", "INVALID_JSON"), (b'{"positions":NaN}', "INVALID_JSON")),
)
def test_invalid_encoded_or_json_bodies_are_safe(body: bytes, code: str) -> None:
    response = _post(_adapter(), body)
    assert response.status_code == 400
    assert _error_code(response) == code
    assert "traceback" not in response.body.decode().lower()


@pytest.mark.parametrize("root", ([], "text", 1, True, None))
def test_json_root_must_be_an_object(root: object) -> None:
    response = _post(_adapter(), json.dumps(root).encode())
    assert response.status_code == 400
    assert _error_code(response) == "INVALID_REQUEST"


@pytest.mark.parametrize("field", ("positions", "fact_candidates"))
def test_required_fields(field: str) -> None:
    payload = _payload()
    del payload[field]
    response = _post(_adapter(), _body(payload))
    assert response.status_code == 400
    assert f"campo {field}" in response.body.decode()


def test_unknown_request_field_is_ignored_without_changing_behavior() -> None:
    plain = _decoded(_post(_adapter()))
    with_extra = _decoded(_post(_adapter(), _body(_payload(secret=True))))
    assert with_extra == plain


@pytest.mark.parametrize(
    "changes",
    ({"positions": {}}, {"fact_candidates": {}}, {"positions": ["bad"]}, {"fact_candidates": ["bad"]}),
)
def test_collections_and_items_require_json_arrays_and_objects(changes: dict[str, object]) -> None:
    assert _post(_adapter(), _body(_payload(**changes))).status_code == 400


@pytest.mark.parametrize(
    ("field", "value"),
    (("owner", "jolika"), ("owner", "OTHER"), ("quantity", 1.5),
     ("quantity", "bad"), ("quantity", "NaN"), ("reference_date", "30/07/2026")),
)
def test_invalid_position_values_are_rejected(field: str, value: object) -> None:
    response = _post(_adapter(), _body(_payload(positions=[_position(**{field: value})])))
    assert response.status_code == 400


def test_decimal_strings_and_dates_are_converted_exactly() -> None:
    class InspectingFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            position = request.positions[0]
            assert position.unit_price == Decimal("10.25")
            assert position.reference_date == date(2026, 7, 30)
            return _facade().execute(request)

    assert _post(DailyHttpAdapter(InspectingFacade())).status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    (("published_at", "2026-07-30T11:00:00"), ("importance", "URGENT"),
     ("category", 2), ("urgency", "urgent"), ("related_currencies", "USD"),
     ("related_institutions", ["UBS", 2])),
)
def test_invalid_fact_values_are_rejected(field: str, value: object) -> None:
    response = _post(_adapter(), _body(_payload(fact_candidates=[_fact(**{field: value})])))
    assert response.status_code == 400


def test_fact_timestamp_is_normalized_to_utc_and_arrays_become_tuples() -> None:
    class InspectingFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            fact = request.fact_candidates[0]
            assert fact.published_at == NOW
            assert fact.related_institutions == ("UBS",)
            return _facade().execute(request)

    payload = _payload(fact_candidates=[_fact(published_at="2026-07-30T09:00:00-03:00")])
    assert _post(DailyHttpAdapter(InspectingFacade()), _body(payload)).status_code == 200


@pytest.mark.parametrize("value", (None,))
def test_null_validation_reports_is_accepted(value: object) -> None:
    assert _post(_adapter(), _body(_payload(validation_reports=value))).status_code == 200


def test_absent_validation_reports_is_accepted() -> None:
    assert _post(_adapter()).status_code == 200


def test_non_null_validation_reports_is_rejected() -> None:
    response = _post(_adapter(), _body(_payload(validation_reports={})))
    assert response.status_code == 400
    assert "ainda não é aceito" in response.body.decode()


def test_payload_limit_is_checked_before_parsing_or_facade() -> None:
    response = _post(_adapter(), b"x" * (MAX_DAILY_REQUEST_BYTES + 1))
    assert response.status_code == 413
    assert _error_code(response) == "PAYLOAD_TOO_LARGE"


def test_facade_invalid_request_maps_to_400() -> None:
    invalid_request = DailyApiRequest((), (), None)
    object.__setattr__(invalid_request, "positions", [])

    class InvalidFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            return _facade().execute(invalid_request)

    assert _post(DailyHttpAdapter(InvalidFacade())).status_code == 400


@pytest.mark.parametrize(
    "code",
    (
        DailyApiErrorCode.ORCHESTRATION_ERROR,
        DailyApiErrorCode.EXPERIENCE_ERROR,
        DailyApiErrorCode.INTERNAL_ERROR,
    ),
)
def test_facade_operational_errors_map_to_500(code: DailyApiErrorCode) -> None:
    class ErrorFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            return DailyApiResponse(
                DailyApiStatus.ERROR, NOW, None, None, None, (), (), (), (), None,
                DailyApiError(code, "Mensagem segura.", "INTERNAL"),
            )

    response = _post(DailyHttpAdapter(ErrorFacade()))
    assert response.status_code == 500
    assert _error_code(response) == code.value


def test_unexpected_adapter_failure_returns_safe_500() -> None:
    class FailingFacade(DailyApiFacade):
        def execute(self, request: DailyApiRequest) -> DailyApiResponse:
            raise RuntimeError("traceback source_file=/private market_value=999")

    response = _post(DailyHttpAdapter(FailingFacade()))
    assert response.status_code == 500
    text = response.body.decode()
    assert "INTERNAL_ERROR" in text
    for forbidden in ("traceback", "source_file", "/private", "market_value"):
        assert forbidden not in text


def test_response_is_frozen_bytes_with_immutable_headers() -> None:
    response = _post(_adapter())
    assert isinstance(response.body, bytes)
    assert type(response.headers) is type(MappingProxyType({}))
    with pytest.raises(FrozenInstanceError):
        setattr(response, "body", b"changed")


def test_determinism_and_no_input_mutation() -> None:
    adapter = _adapter()
    headers = {"Content-Type": "application/json"}
    body = _body()
    before = (dict(headers), body)
    assert adapter.handle("POST", headers, body) == adapter.handle("POST", headers, body)
    assert (headers, body) == before


def test_no_internal_or_financial_data_leaks_across_owners_and_currencies() -> None:
    positions = [
        _position(owner="JOLIKA", currency="USD", institution="UBS"),
        _position(owner="JOLIKA", currency="BRL", institution="Santander"),
        _position(owner="NEI", currency="BRL", institution="Bradesco"),
    ]
    response = _post(_adapter(), _body(_payload(positions=positions, fact_candidates=[])))
    value = repr(response) + response.body.decode()
    for forbidden in (
        "PortfolioPosition", "FactCandidate", "DailyPortfolioSnapshot",
        "DailyOrchestrationResult", "source_file", "quantity", "unit_price",
        "market_value", "traceback", "private.csv", "JOLIKA", "NEI",
    ):
        assert forbidden not in value


@pytest.fixture
def server() -> Iterator[ThreadingHTTPServer]:
    instance = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    yield instance
    instance.shutdown()
    thread.join()
    instance.server_close()


def test_real_server_routes_daily_post_and_rejects_get(server: ThreadingHTTPServer) -> None:
    for method, expected in (("POST", 200), ("GET", 405), ("PUT", 405)):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            method, "/api/daily-experience", body=_body(),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read()
        assert response.status == expected
        assert response.getheader("Content-Type") == "application/json; charset=utf-8"
        json.loads(body.decode())
        connection.close()


def test_real_server_uses_confirmed_session_positions(
    server: ThreadingHTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    class RecordingAdapter:
        received_positions = None

        def handle(
            self, method, headers, body, agenda_events, decision_profile,
            received_positions, official_facts,
        ):
            self.received_positions = received_positions
            return DailyHttpResponse(
                200,
                {"Content-Type": "application/json; charset=utf-8"},
                b'{"status":"SUCCESS"}',
            )

    adapter = RecordingAdapter()
    monkeypatch.setattr(server_module, "DAILY_HTTP_ADAPTER", adapter)

    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        "POST", "/api/daily-experience",
        body=_body(_payload(positions=[_position(identifier="CLIENT-ONLY")])),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    response.read()
    connection.close()

    assert response.status == 200
    assert adapter.received_positions == ()
