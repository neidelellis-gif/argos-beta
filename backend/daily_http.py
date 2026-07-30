"""HTTP boundary for the official ARGOS daily API facade."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum, IntEnum
import json
from types import MappingProxyType
from typing import TypeVar

from backend.daily_api import (
    DailyApiFacade,
    daily_api_response_to_dict,
)
from backend.daily_contract import (
    CONTRACT_VERSION,
    DailyApiErrorCode,
    DailyApiRequest,
    DailyApiResponse,
    DailyApiStatus,
)
from backend.important_facts import FactCandidate, FactCategory, FactImportance
from backend.models import PortfolioOwner, PortfolioPosition
from backend.market_agenda import MarketAgendaEvent
from backend.decision_context import DecisionProfile


MAX_DAILY_REQUEST_BYTES = 1_048_576
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_POSITION_FIELDS = frozenset(
    {
        "institution", "owner", "account", "asset_class", "asset_subclass",
        "asset_name", "identifier", "identifier_type", "quantity", "unit_price",
        "market_value", "currency", "portfolio_weight", "reference_date",
        "source_file",
    }
)
_FACT_REQUIRED_FIELDS = frozenset(
    {"id", "title", "description", "source", "published_at", "importance", "category"}
)
_FACT_FIELDS = _FACT_REQUIRED_FIELDS | {
    "urgency", "related_assets", "related_sectors", "related_currencies",
    "related_institutions",
}
_EnumValue = TypeVar("_EnumValue", bound=Enum)


class DailyHttpStatus(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    PAYLOAD_TOO_LARGE = 413
    METHOD_NOT_ALLOWED = 405
    UNSUPPORTED_MEDIA_TYPE = 415
    INTERNAL_SERVER_ERROR = 500


class DailyHttpRequestError(Exception):
    """Safe validation error raised while translating an external request."""

    def __init__(self, message: str, field: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.field = field
        self.status_code = status_code


@dataclass(frozen=True)
class DailyHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")
        if not isinstance(self.body, bytes):
            raise TypeError("body must be bytes")
        headers = MappingProxyType(dict(self.headers))
        content_type = headers.get("Content-Type")
        if content_type != _JSON_CONTENT_TYPE:
            raise ValueError("Content-Type must declare JSON encoded as UTF-8")
        try:
            self.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("body must use UTF-8") from error
        object.__setattr__(self, "headers", headers)


class DailyHttpAdapter:
    """Receive, translate, execute the facade, and return a safe JSON response."""

    def __init__(self, facade: DailyApiFacade | None = None) -> None:
        self._facade = facade if facade is not None else DailyApiFacade()

    def handle(
        self,
        method: str,
        headers: Mapping[str, str],
        body: bytes,
        agenda_events: tuple[MarketAgendaEvent, ...] = (),
        decision_profile: DecisionProfile | None = None,
    ) -> DailyHttpResponse:
        try:
            if method != "POST":
                return self._error(
                    DailyHttpStatus.METHOD_NOT_ALLOWED,
                    "METHOD_NOT_ALLOWED",
                    "Método HTTP não permitido.",
                    {"Allow": "POST"},
                )
            if len(body) > MAX_DAILY_REQUEST_BYTES:
                return self._error(
                    DailyHttpStatus.PAYLOAD_TOO_LARGE,
                    "PAYLOAD_TOO_LARGE",
                    "O conteúdo da requisição excede o limite permitido.",
                )
            if self._header(headers, "Content-Type").partition(";")[0].strip().lower() != "application/json":
                return self._error(
                    DailyHttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "UNSUPPORTED_MEDIA_TYPE",
                    "O conteúdo deve ser enviado em formato JSON.",
                )
            request = replace(self._request(body), agenda_events=agenda_events, decision_profile=decision_profile)
            response = self._facade.execute(request)
            return self._facade_response(response)
        except DailyHttpRequestError as error:
            return self._error(error.status_code, self._error_code(error), error.message)
        except Exception:
            return self._error(
                DailyHttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "Ocorreu uma falha interna ao processar a requisição.",
            )

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        return next(
            (value for key, value in headers.items() if key.lower() == name.lower()),
            "",
        )

    def _request(self, body: bytes) -> DailyApiRequest:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DailyHttpRequestError(
                "O conteúdo da requisição deve utilizar UTF-8.", "encoding"
            ) from error
        if not text.strip():
            raise DailyHttpRequestError(
                "Não foi possível interpretar a requisição JSON.", "json"
            )
        try:
            payload: object = json.loads(text, parse_constant=self._reject_json_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise DailyHttpRequestError(
                "Não foi possível interpretar a requisição JSON.", "json"
            ) from error
        if not isinstance(payload, dict):
            raise DailyHttpRequestError("A requisição possui formato inválido.")
        request_data: dict[object, object] = payload
        if any(not isinstance(key, str) for key in request_data):
            raise DailyHttpRequestError("A requisição possui formato inválido.")
        for field in ("positions", "fact_candidates"):
            if field not in request_data:
                raise DailyHttpRequestError(f"O campo {field} é obrigatório.", field)
        if request_data.get("validation_reports") is not None:
            raise DailyHttpRequestError(
                "O campo validation_reports ainda não é aceito por esta rota.",
                "validation_reports",
            )
        positions_value = request_data["positions"]
        candidates_value = request_data["fact_candidates"]
        if not isinstance(positions_value, list):
            raise DailyHttpRequestError("O campo positions deve ser um array.", "positions")
        if not isinstance(candidates_value, list):
            raise DailyHttpRequestError(
                "O campo fact_candidates deve ser um array.", "fact_candidates"
            )
        positions = tuple(self._position(item) for item in positions_value)
        candidates = tuple(self._candidate(item) for item in candidates_value)
        reference_date = self._date(request_data.get("reference_date"), "reference_date")
        return DailyApiRequest(positions, candidates, reference_date, None)

    def _position(self, value: object) -> PortfolioPosition:
        data = self._object(value, "positions")
        self._exact_fields(data, _POSITION_FIELDS, _POSITION_FIELDS, "positions")
        return PortfolioPosition(
            institution=self._required_string(data["institution"], "institution"),
            owner=self._enum(data["owner"], PortfolioOwner, "owner"),
            account=self._string(data["account"], "account"),
            asset_class=self._string(data["asset_class"], "asset_class"),
            asset_subclass=self._string(data["asset_subclass"], "asset_subclass"),
            asset_name=self._string(data["asset_name"], "asset_name"),
            identifier=self._string(data["identifier"], "identifier"),
            identifier_type=self._string(data["identifier_type"], "identifier_type"),
            quantity=self._decimal(data["quantity"], "quantity"),
            unit_price=self._decimal(data["unit_price"], "unit_price"),
            market_value=self._decimal(data["market_value"], "market_value"),
            currency=self._string(data["currency"], "currency"),
            portfolio_weight=self._decimal(data["portfolio_weight"], "portfolio_weight"),
            reference_date=self._date(data["reference_date"], "reference_date"),
            source_file=self._required_string(data["source_file"], "source_file"),
        )

    def _candidate(self, value: object) -> FactCandidate:
        data = self._object(value, "fact_candidates")
        self._exact_fields(data, _FACT_REQUIRED_FIELDS, _FACT_FIELDS, "fact_candidates")
        return FactCandidate(
            id=self._required_string(data["id"], "id"),
            title=self._required_string(data["title"], "title"),
            description=self._required_string(data["description"], "description"),
            source=self._required_string(data["source"], "source"),
            published_at=self._datetime(data["published_at"], "published_at"),
            importance=self._enum(data["importance"], FactImportance, "importance"),
            category=self._enum(data["category"], FactCategory, "category"),
            urgency=self._enum(
                data.get("urgency", FactImportance.LOW.value), FactImportance, "urgency"
            ),
            related_assets=self._strings(data.get("related_assets", []), "related_assets"),
            related_sectors=self._strings(data.get("related_sectors", []), "related_sectors"),
            related_currencies=self._strings(
                data.get("related_currencies", []), "related_currencies"
            ),
            related_institutions=self._strings(
                data.get("related_institutions", []), "related_institutions"
            ),
        )

    @staticmethod
    def _object(value: object, field: str) -> dict[str, object]:
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise DailyHttpRequestError(f"O campo {field} possui item inválido.", field)
        return value

    @staticmethod
    def _exact_fields(
        data: Mapping[str, object], required: frozenset[str], allowed: frozenset[str], field: str
    ) -> None:
        missing = required - set(data)
        if missing:
            raise DailyHttpRequestError(f"O campo {min(missing)} é obrigatório.", min(missing))
        if set(data) - allowed:
            raise DailyHttpRequestError(f"O campo {field} possui campos desconhecidos.", field)

    @staticmethod
    def _string(value: object, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field)
        return value

    @staticmethod
    def _required_string(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field)
        return value

    @staticmethod
    def _decimal(value: object, field: str) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise DailyHttpRequestError(f"O campo {field} deve ser uma string decimal.", field)
        try:
            result = Decimal(value)
        except InvalidOperation as error:
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field) from error
        if not result.is_finite():
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field)
        return result

    @staticmethod
    def _date(value: object, field: str) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str) or "T" in value:
            raise DailyHttpRequestError(f"O campo {field} possui data inválida.", field)
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise DailyHttpRequestError(f"O campo {field} possui data inválida.", field) from error

    @staticmethod
    def _datetime(value: object, field: str) -> datetime:
        if not isinstance(value, str):
            raise DailyHttpRequestError(f"O campo {field} possui data e hora inválidas.", field)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise DailyHttpRequestError(
                f"O campo {field} possui data e hora inválidas.", field
            ) from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise DailyHttpRequestError(
                f"O campo {field} deve informar o fuso horário.", field
            )
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _enum(
        value: object, enum_type: type[_EnumValue], field: str
    ) -> _EnumValue:
        if not isinstance(value, str):
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field)
        try:
            return enum_type(value)
        except ValueError as error:
            raise DailyHttpRequestError(f"O campo {field} possui valor inválido.", field) from error

    @staticmethod
    def _strings(value: object, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise DailyHttpRequestError(f"O campo {field} deve ser um array de strings.", field)
        return tuple(value)

    @staticmethod
    def _reject_json_constant(value: str) -> object:
        raise ValueError("invalid JSON constant")

    def _facade_response(self, response: DailyApiResponse) -> DailyHttpResponse:
        status = DailyHttpStatus.OK
        if response.status is DailyApiStatus.ERROR:
            status = (
                DailyHttpStatus.BAD_REQUEST
                if response.error is not None
                and response.error.code is DailyApiErrorCode.INVALID_REQUEST
                else DailyHttpStatus.INTERNAL_SERVER_ERROR
            )
        return self._json_response(status, daily_api_response_to_dict(response))

    @staticmethod
    def _error_code(error: DailyHttpRequestError) -> str:
        if error.field == "encoding":
            return "INVALID_ENCODING"
        if error.field == "json":
            return "INVALID_JSON"
        return "INVALID_REQUEST"

    def _error(
        self,
        status: int,
        code: str,
        message: str,
        extra_headers: Mapping[str, str] | None = None,
    ) -> DailyHttpResponse:
        payload: dict[str, object] = {
            "contract_version": CONTRACT_VERSION,
            "status": DailyApiStatus.ERROR.value, "generated_at": None, "experience_status": None,
            "header": None, "message": None, "facts": [], "priorities": [],
            "analyses": [], "blocks": [], "market_agenda": [], "impact_assessments": [], "summary": None,
            "error": {"code": code, "message": message, "stage": "HTTP"},
        }
        return self._json_response(status, payload, extra_headers)

    @staticmethod
    def _json_response(
        status: int,
        payload: Mapping[str, object],
        extra_headers: Mapping[str, str] | None = None,
    ) -> DailyHttpResponse:
        headers = {"Content-Type": _JSON_CONTENT_TYPE, "Cache-Control": "no-store"}
        headers.update(extra_headers or {})
        body = json.dumps(
            payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        return DailyHttpResponse(int(status), headers, body)
