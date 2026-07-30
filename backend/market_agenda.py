"""Canonical, validated market-agenda input model and structured import."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_EVENTS = 1_000
MAX_TITLE = 200
MAX_DESCRIPTION = 1_000
MAX_COLLECTION = 50
COLLECTION_FIELDS = (
    "asset_identifiers", "asset_names", "asset_classes", "sectors",
    "currencies", "markets",
)
CSV_FIELDS = (
    "event_id", "event_type", "title", "event_date", "event_time", "timezone",
    "all_day", "institution", *COLLECTION_FIELDS, "country", "importance",
    "source_name", "source_reference", "description",
)
_SAFE_TEXT = re.compile(r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$")
_SAFE_ID = re.compile(r"^[\w.:/@+\- ]+$", re.UNICODE)


class MarketAgendaEventType(str, Enum):
    EARNINGS = "EARNINGS"
    DIVIDEND = "DIVIDEND"
    CENTRAL_BANK = "CENTRAL_BANK"
    MACROECONOMIC = "MACROECONOMIC"
    REGULATORY = "REGULATORY"
    CORPORATE = "CORPORATE"
    MARKET_HOLIDAY = "MARKET_HOLIDAY"
    OTHER = "OTHER"


class MarketAgendaImportance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class MarketAgendaEvent:
    event_id: str
    event_type: MarketAgendaEventType
    title: str
    event_date: date
    event_time: time | None
    timezone: str | None
    all_day: bool
    institution: str | None
    asset_identifiers: tuple[str, ...]
    asset_names: tuple[str, ...]
    asset_classes: tuple[str, ...]
    sectors: tuple[str, ...]
    currencies: tuple[str, ...]
    markets: tuple[str, ...]
    country: str | None
    importance: MarketAgendaImportance
    source_name: str
    source_reference: str
    description: str | None


class MarketAgendaValidationError(ValueError):
    """Raised when an import cannot be accepted atomically."""


def _text(value: Any, field: str, *, required: bool = False, maximum: int = 500) -> str | None:
    if value is None or value == "":
        if required:
            raise MarketAgendaValidationError(f"O campo {field} é obrigatório.")
        return None
    if not isinstance(value, str):
        raise MarketAgendaValidationError(f"O campo {field} deve ser texto.")
    value = value.strip()
    if not value and required:
        raise MarketAgendaValidationError(f"O campo {field} é obrigatório.")
    if len(value) > maximum or not _SAFE_TEXT.fullmatch(value):
        raise MarketAgendaValidationError(f"O campo {field} é inválido ou excessivo.")
    return value or None


def _collection(value: Any, field: str) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if not isinstance(value, (list, tuple)):
        raise MarketAgendaValidationError(f"O campo {field} deve ser uma coleção.")
    if len(value) > MAX_COLLECTION:
        raise MarketAgendaValidationError(f"O campo {field} excede {MAX_COLLECTION} itens.")
    result = []
    for item in value:
        normalized = _text(item, field, required=True, maximum=200)
        if normalized is None or not _SAFE_ID.fullmatch(normalized):
            raise MarketAgendaValidationError(f"O campo {field} contém identificador inválido.")
        result.append(normalized)
    return tuple(result)


def validate_market_agenda_event(data: Any) -> MarketAgendaEvent:
    if not isinstance(data, dict):
        raise MarketAgendaValidationError("Cada evento deve ser um objeto.")
    missing = set(CSV_FIELDS) - set(data)
    if missing:
        raise MarketAgendaValidationError(f"O campo {min(missing)} é obrigatório.")
    unknown = set(data) - set(CSV_FIELDS)
    if unknown:
        raise MarketAgendaValidationError(f"Campo desconhecido: {min(unknown)}.")
    event_id = _text(data["event_id"], "event_id", required=True, maximum=200)
    if event_id is None or not _SAFE_ID.fullmatch(event_id):
        raise MarketAgendaValidationError("O campo event_id é inválido.")
    try:
        event_type = MarketAgendaEventType(data["event_type"])
    except (ValueError, TypeError) as error:
        raise MarketAgendaValidationError("O tipo de evento é inválido.") from error
    importance_value = {"CRITICAL": "HIGH", "MODERATE": "MEDIUM"}.get(
        data["importance"], data["importance"]
    )
    try:
        importance = MarketAgendaImportance(importance_value)
    except (ValueError, TypeError) as error:
        raise MarketAgendaValidationError("A importância é inválida.") from error
    raw_date = data["event_date"]
    try:
        if not isinstance(raw_date, str) or len(raw_date) != 10:
            raise ValueError
        event_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise MarketAgendaValidationError("A data do evento é inválida.") from error
    all_day = data["all_day"]
    if not isinstance(all_day, bool):
        raise MarketAgendaValidationError("O campo all_day deve ser booleano.")
    raw_time = data["event_time"]
    raw_timezone = data["timezone"]
    if all_day:
        if raw_time not in (None, ""):
            raise MarketAgendaValidationError("Evento de dia inteiro não pode ter horário.")
        event_time, timezone_name = None, _text(raw_timezone, "timezone", maximum=100)
    else:
        try:
            if not isinstance(raw_time, str) or not re.fullmatch(r"\d{2}:\d{2}", raw_time):
                raise ValueError
            event_time = time.fromisoformat(raw_time)
        except ValueError as error:
            raise MarketAgendaValidationError("O horário do evento é inválido.") from error
        timezone_name = _text(raw_timezone, "timezone", required=True, maximum=100)
        try:
            if timezone_name is None or "/" not in timezone_name and timezone_name != "UTC":
                raise ZoneInfoNotFoundError
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise MarketAgendaValidationError("O fuso horário deve ser um identificador IANA válido.") from error
    title = _text(data["title"], "title", required=True, maximum=MAX_TITLE)
    source_name = _text(data["source_name"], "source_name", required=True, maximum=200)
    source_reference = _text(data["source_reference"], "source_reference", required=True, maximum=500)
    assert event_id and title and source_name and source_reference
    return MarketAgendaEvent(
        event_id=event_id, event_type=event_type, title=title, event_date=event_date,
        event_time=event_time, timezone=timezone_name, all_day=all_day,
        institution=_text(data["institution"], "institution", maximum=200),
        asset_identifiers=_collection(data["asset_identifiers"], "asset_identifiers"),
        asset_names=_collection(data["asset_names"], "asset_names"),
        asset_classes=_collection(data["asset_classes"], "asset_classes"),
        sectors=_collection(data["sectors"], "sectors"),
        currencies=_collection(data["currencies"], "currencies"),
        markets=_collection(data["markets"], "markets"),
        country=_text(data["country"], "country", maximum=100), importance=importance,
        source_name=source_name, source_reference=source_reference,
        description=_text(data["description"], "description", maximum=MAX_DESCRIPTION),
    )


def import_market_agenda(file_name: str, content: bytes) -> tuple[MarketAgendaEvent, ...]:
    """Parse and validate exactly one JSON or CSV upload, without partial output."""
    if not content:
        raise MarketAgendaValidationError("O arquivo de agenda está vazio.")
    suffix = Path(file_name).suffix.lower()
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MarketAgendaValidationError("O arquivo deve utilizar UTF-8.") from error
    try:
        if suffix == ".json":
            payload = json.loads(decoded)
            if not isinstance(payload, dict) or set(payload) != {"events"} or not isinstance(payload["events"], list):
                raise MarketAgendaValidationError("JSON deve conter somente a coleção events.")
            rows = payload["events"]
        elif suffix == ".csv":
            reader = csv.DictReader(io.StringIO(decoded))
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise MarketAgendaValidationError("Os cabeçalhos CSV não correspondem ao contrato oficial.")
            rows = list(reader)
            for row in rows:
                for field in COLLECTION_FIELDS:
                    row[field] = [] if not row[field] else row[field].split("|")
                normalized = str(row["all_day"]).strip().lower()
                if normalized not in {"true", "false"}:
                    raise MarketAgendaValidationError("O campo all_day deve ser true ou false.")
                row["all_day"] = normalized == "true"
                row["event_time"] = row["event_time"] or None
                row["timezone"] = row["timezone"] or None
        else:
            raise MarketAgendaValidationError("Envie um arquivo JSON ou CSV.")
    except (json.JSONDecodeError, csv.Error) as error:
        raise MarketAgendaValidationError("O arquivo de agenda é inválido.") from error
    if not rows:
        raise MarketAgendaValidationError("O arquivo deve conter ao menos um evento.")
    if len(rows) > MAX_EVENTS:
        raise MarketAgendaValidationError(f"A importação excede {MAX_EVENTS} eventos.")
    events = tuple(validate_market_agenda_event(row) for row in rows)
    seen_ids: set[str] = set()
    seen_titles: set[tuple[date, time | None, str]] = set()
    seen_sources: set[tuple[str, str]] = set()
    for event in events:
        identifier = event.event_id.casefold()
        title_key = (event.event_date, event.event_time, " ".join(event.title.casefold().split()))
        source_key = (event.source_name.casefold(), event.source_reference.casefold())
        if identifier in seen_ids or title_key in seen_titles or source_key in seen_sources:
            raise MarketAgendaValidationError("O arquivo contém eventos duplicados.")
        seen_ids.add(identifier)
        seen_titles.add(title_key)
        seen_sources.add(source_key)
    return events
