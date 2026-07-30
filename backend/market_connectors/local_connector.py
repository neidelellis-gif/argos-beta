"""Local-file market connector migrated from Operation Real 02."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from collections.abc import Mapping

from backend.market_connectors.base import MarketConnector

from backend.important_facts import FactCategory, FactImportance, MarketFact
from backend.market_agenda import MarketAgendaEvent, MarketAgendaValidationError, validate_market_agenda_event


DEFAULT_MARKET_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "market"
SOURCE_TYPES = frozenset({
    "BANCO_CENTRAL", "BOLSA", "EMPRESA", "CALENDARIO_ECONOMICO", "RELATORIO_OFICIAL",
})
_METADATA_FIELDS = {"source_id", "source_name", "source_type", "reference_date", "collected_at", "data_version"}
_FACT_FIELDS = {
    "fact_id", "title", "description", "category", "source", "reference_date",
    "importance", "related_assets", "related_sectors", "related_currencies", "related_institutions",
}
_ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,49}$")


class MarketDataValidationError(ValueError):
    """Atomic validation failure following DataQualityEngine diagnostic identifiers."""

    def __init__(self, diagnostic_id: str, message: str, affected_items: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.diagnostic_id = diagnostic_id
        self.affected_items = affected_items


@dataclass(frozen=True)
class MarketDataSource:
    source_id: str
    source_name: str
    source_type: str
    reference_date: date
    collected_at: datetime
    data_version: str


@dataclass(frozen=True)
class OfficialMarketData:
    facts: tuple[MarketFact, ...]
    agenda: tuple[MarketAgendaEvent, ...]
    sources: tuple[MarketDataSource, ...]


class LocalMarketConnector(MarketConnector):
    """Locate, validate and normalize local files without analysing their content."""

    def __init__(self, root: Path = DEFAULT_MARKET_ROOT) -> None:
        self.root = Path(root)

    def is_available(self) -> bool:
        return self.root.is_dir() and (self.root / "facts").is_dir() and (self.root / "agenda").is_dir()

    def metadata(self) -> Mapping[str, object]:
        return {"connector": "LOCAL", "source": "data/market", "root": str(self.root)}

    def load(self) -> OfficialMarketData:
        fact_files = tuple(sorted((self.root / "facts").glob("*.json")))
        agenda_files = tuple(sorted((self.root / "agenda").glob("*.json")))
        if not fact_files or not agenda_files:
            raise MarketDataValidationError("market.missing", "Fatos e agenda oficiais são obrigatórios.")
        facts: list[MarketFact] = []
        agenda: list[MarketAgendaEvent] = []
        sources: list[MarketDataSource] = []
        for path in fact_files:
            source, rows = self._file(path, "facts")
            sources.append(source)
            facts.extend(self._fact(row, source) for row in rows)
        for path in agenda_files:
            source, rows = self._file(path, "events")
            sources.append(source)
            agenda.extend(self._event(row, source) for row in rows)
        self._duplicates(facts, agenda)
        return OfficialMarketData(tuple(facts), tuple(agenda), tuple(sources))

    def load_facts(self) -> tuple[MarketFact, ...]:
        return self.load().facts

    def load_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        return self.load().agenda

    def _file(self, path: Path, collection: str) -> tuple[MarketDataSource, list[Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MarketDataValidationError("market.invalid", f"Arquivo oficial inválido: {path.name}.") from error
        expected = _METADATA_FIELDS | {collection}
        if not isinstance(payload, dict) or set(payload) != expected or not isinstance(payload[collection], list):
            raise MarketDataValidationError("market.invalid", f"Estrutura inválida em {path.name}.")
        if not payload[collection]:
            raise MarketDataValidationError("market.empty", f"Arquivo oficial vazio: {path.name}.")
        source_id = self._text(payload, "source_id", "market.missing_source")
        source_name = self._text(payload, "source_name", "market.missing_source")
        source_type = self._text(payload, "source_type", "market.missing_source")
        if source_type not in SOURCE_TYPES:
            raise MarketDataValidationError("market.invalid_source", "Tipo de fonte oficial inválido.", (source_type,))
        reference = self._date(payload.get("reference_date"), "market.invalid_date")
        collected = self._datetime(payload.get("collected_at"))
        if collected.date() < reference:
            raise MarketDataValidationError("market.inconsistent_dates", "A coleta antecede a data de referência.")
        version = self._text(payload, "data_version", "market.invalid")
        return MarketDataSource(source_id, source_name, source_type, reference, collected, version), payload[collection]

    def _fact(self, value: Any, metadata: MarketDataSource) -> MarketFact:
        if not isinstance(value, dict) or set(value) != _FACT_FIELDS:
            raise MarketDataValidationError("facts.invalid", "Fato oficial possui estrutura inválida.")
        identifier = self._text(value, "fact_id", "facts.missing_identifier")
        source = self._text(value, "source", "facts.missing_source")
        if source != metadata.source_id:
            raise MarketDataValidationError("facts.missing_source", "A origem do fato não corresponde ao arquivo.", (identifier,))
        reference = self._date(value.get("reference_date"), "facts.invalid_date")
        if reference != metadata.reference_date:
            raise MarketDataValidationError("facts.inconsistent_dates", "Datas do fato e da fonte são inconsistentes.", (identifier,))
        try:
            category = FactCategory(value.get("category"))
        except (TypeError, ValueError) as error:
            raise MarketDataValidationError("facts.invalid_category", "Categoria de fato inválida.", (identifier,)) from error
        try:
            importance = FactImportance(value.get("importance"))
        except (TypeError, ValueError) as error:
            raise MarketDataValidationError("facts.invalid_importance", "Importância de fato inválida.", (identifier,)) from error
        relations = {name: self._assets(value.get(name), name, identifier) for name in (
            "related_assets", "related_sectors", "related_currencies", "related_institutions")}
        return MarketFact(
            id=identifier, title=self._text(value, "title", "facts.invalid"),
            description=self._text(value, "description", "facts.invalid"),
            source=metadata.source_name, published_at=metadata.collected_at,
            importance=importance, urgency=importance, category=category, **relations,
        )

    def _event(self, value: Any, metadata: MarketDataSource) -> MarketAgendaEvent:
        if not isinstance(value, dict):
            raise MarketDataValidationError("agenda.invalid", "Evento oficial possui estrutura inválida.")
        if value.get("source_name") != metadata.source_name:
            raise MarketDataValidationError("agenda.missing_source", "A origem do evento não corresponde ao arquivo.")
        try:
            event = validate_market_agenda_event(value)
        except MarketAgendaValidationError as error:
            message = str(error)
            diagnostic = "agenda.invalid_date" if "data" in message.lower() else "agenda.invalid"
            raise MarketDataValidationError(diagnostic, message) from error
        if event.event_date < metadata.reference_date:
            raise MarketDataValidationError("agenda.inconsistent_dates", "Evento anterior à data de referência.", (event.event_id,))
        for asset in event.asset_identifiers:
            if not _ASSET.fullmatch(asset):
                raise MarketDataValidationError("agenda.invalid_assets", "Ativo malformado na agenda.", (asset,))
        return event

    @staticmethod
    def _duplicates(facts: list[MarketFact], events: list[MarketAgendaEvent]) -> None:
        fact_ids = [item.fact_id.casefold() for item in facts]
        event_ids = [item.event_id.casefold() for item in events]
        if len(fact_ids) != len(set(fact_ids)):
            raise MarketDataValidationError("facts.duplicates", "Há fatos duplicados.")
        if len(event_ids) != len(set(event_ids)):
            raise MarketDataValidationError("agenda.duplicates", "Há eventos duplicados.")

    @staticmethod
    def _text(payload: dict[str, Any], field: str, diagnostic: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise MarketDataValidationError(diagnostic, f"O campo {field} é obrigatório.")
        return value.strip()

    @staticmethod
    def _date(value: Any, diagnostic: str) -> date:
        try:
            if not isinstance(value, str):
                raise ValueError
            return date.fromisoformat(value)
        except ValueError as error:
            raise MarketDataValidationError(diagnostic, "Data de referência inválida.") from error

    @staticmethod
    def _datetime(value: Any) -> datetime:
        try:
            if not isinstance(value, str):
                raise ValueError
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
            return parsed.astimezone(timezone.utc)
        except ValueError as error:
            raise MarketDataValidationError("market.invalid_date", "Data de coleta inválida.") from error

    @staticmethod
    def _assets(value: Any, field: str, identifier: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not _ASSET.fullmatch(item) for item in value):
            raise MarketDataValidationError("facts.invalid_assets", f"{field} contém ativo malformado.", (identifier,))
        return tuple(value)
