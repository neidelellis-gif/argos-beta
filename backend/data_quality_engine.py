"""Deterministic diagnostics for canonical daily inputs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from backend.decision_context import DecisionProfile, PortfolioScope
from backend.market_agenda import MarketAgendaEvent
from backend.models import PortfolioOwner, PortfolioPosition


class DataQualitySeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class DataQualityCategory(str, Enum):
    PORTFOLIO = "PORTFOLIO"
    MARKET_AGENDA = "MARKET_AGENDA"
    DECISION_CONTEXT = "DECISION_CONTEXT"
    CROSS_VALIDATION = "CROSS_VALIDATION"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class _Diagnostic:
    id: str
    severity: DataQualitySeverity
    category: DataQualityCategory
    title: str
    description: str
    affected_items: tuple[str, ...] = ()
    can_continue: bool = True

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "affected_items": list(self.affected_items),
            "can_continue": self.can_continue,
        }


class DataQualityEngine:
    """Inspect inputs without mutating them or making analytical decisions."""

    def diagnose(
        self,
        carteira: Iterable[PortfolioPosition],
        agenda: Iterable[MarketAgendaEvent],
        contexto: DecisionProfile | None,
        reference_date: date,
    ) -> dict[str, object]:
        if not isinstance(reference_date, date):
            raise TypeError("reference_date must be a date")
        raw_positions, raw_events = tuple(carteira), tuple(agenda)
        positions = tuple(item for item in raw_positions if isinstance(item, PortfolioPosition))
        events = tuple(item for item in raw_events if isinstance(item, MarketAgendaEvent))
        diagnostics: list[_Diagnostic] = []
        invalid_positions = [str(index + 1) for index, item in enumerate(raw_positions)
                             if not isinstance(item, PortfolioPosition)]
        invalid_events = [str(index + 1) for index, item in enumerate(raw_events)
                          if not isinstance(item, MarketAgendaEvent)]
        if invalid_positions:
            diagnostics.append(self._add(DataQualitySeverity.ERROR, DataQualityCategory.PORTFOLIO,
                "portfolio.invalid", "Posições inválidas", "Há posições fora do modelo canônico.",
                invalid_positions, can_continue=False))
        if invalid_events:
            diagnostics.append(self._add(DataQualitySeverity.ERROR, DataQualityCategory.MARKET_AGENDA,
                "agenda.invalid_dates", "Eventos ou datas inválidos",
                "Há eventos fora do modelo canônico validado.", invalid_events, can_continue=False))
        diagnostics.extend(self._portfolio(positions))
        diagnostics.extend(self._agenda(events, reference_date))
        valid_context = contexto if isinstance(contexto, DecisionProfile) else None
        if contexto is not None and valid_context is None:
            diagnostics.append(self._add(DataQualitySeverity.ERROR, DataQualityCategory.DECISION_CONTEXT,
                "context.invalid", "Contexto inválido", "O contexto não segue o modelo canônico.",
                can_continue=False))
        diagnostics.extend(self._context(valid_context, reference_date))
        diagnostics.extend(self._cross(positions, events, valid_context))
        public = [item.public() for item in diagnostics]
        counts = {
            "errors": sum(item.severity is DataQualitySeverity.ERROR for item in diagnostics),
            "warnings": sum(item.severity is DataQualitySeverity.WARNING for item in diagnostics),
            "infos": sum(item.severity is DataQualitySeverity.INFO for item in diagnostics),
        }
        status = "ERROR" if counts["errors"] else "WARNING" if counts["warnings"] else "HEALTHY"
        return {"status": status, "diagnostics": public, "summary": counts}

    @staticmethod
    def _add(
        severity: DataQualitySeverity, category: DataQualityCategory, identifier: str,
        title: str, description: str, affected: Iterable[str] = (), *, can_continue: bool = True,
    ) -> _Diagnostic:
        return _Diagnostic(identifier, severity, category, title, description,
                           tuple(sorted(set(affected))), can_continue)

    def _portfolio(self, positions: tuple[PortfolioPosition, ...]) -> list[_Diagnostic]:
        if not positions:
            return [self._add(DataQualitySeverity.ERROR, DataQualityCategory.PORTFOLIO,
                "portfolio.missing", "Carteira não informada",
                "Nenhuma posição canônica está disponível para validação.", can_continue=False)]
        result: list[_Diagnostic] = []
        missing_ids = [str(index + 1) for index, item in enumerate(positions) if not item.identifier]
        missing_currencies = [item.identifier or str(index + 1) for index, item in enumerate(positions) if not item.currency]
        missing_institutions = [item.identifier or str(index + 1) for index, item in enumerate(positions) if not item.institution.strip()]
        keys: dict[tuple[object, ...], list[str]] = {}
        for index, item in enumerate(positions):
            key = (item.owner, item.institution.casefold(), item.account, item.identifier, item.asset_name)
            keys.setdefault(key, []).append(item.identifier or str(index + 1))
        duplicates = [value for values in keys.values() if len(values) > 1 for value in values]
        for condition, identifier, title, description, affected in (
            (duplicates, "portfolio.duplicates", "Posições duplicadas", "Há posições com a mesma identidade canônica.", duplicates),
            (missing_ids, "portfolio.missing_identifier", "Ativos sem identificador", "Há posições sem identificador de ativo.", missing_ids),
            (missing_currencies, "portfolio.missing_currency", "Moedas ausentes", "Há posições sem moeda informada.", missing_currencies),
            (missing_institutions, "portfolio.missing_institution", "Instituições ausentes", "Há posições sem instituição informada.", missing_institutions),
        ):
            if condition:
                result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.PORTFOLIO,
                                        identifier, title, description, affected))
        return result

    def _agenda(self, events: tuple[MarketAgendaEvent, ...], reference: date) -> list[_Diagnostic]:
        if not events:
            return [self._add(DataQualitySeverity.INFO, DataQualityCategory.MARKET_AGENDA,
                "agenda.empty", "Agenda vazia", "Nenhum evento de mercado foi informado.")]
        result: list[_Diagnostic] = []
        expired = [item.event_id for item in events if item.event_date < reference]
        no_source = [item.event_id for item in events if not item.source_name.strip()]
        ids: dict[str, int] = {}
        for item in events:
            ids[item.event_id] = ids.get(item.event_id, 0) + 1
        duplicates = [identifier for identifier, count in ids.items() if count > 1]
        for condition, identifier, title, description, affected in (
            (expired, "agenda.expired", "Eventos expirados", "Há eventos anteriores à data de referência.", expired),
            (duplicates, "agenda.duplicates", "Eventos duplicados", "Há identificadores de evento repetidos.", duplicates),
            (no_source, "agenda.missing_source", "Eventos sem fonte", "Há eventos sem fonte rastreável.", no_source),
        ):
            if condition:
                result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.MARKET_AGENDA,
                                        identifier, title, description, affected))
        return result

    def _context(self, profile: DecisionProfile | None, reference: date) -> list[_Diagnostic]:
        if profile is None:
            return [self._add(DataQualitySeverity.WARNING, DataQualityCategory.DECISION_CONTEXT,
                "context.missing", "Perfil inexistente", "Nenhum contexto decisório foi informado.")]
        result = []
        if not profile.primary_objectives and not profile.secondary_objectives:
            result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.DECISION_CONTEXT,
                "context.empty_objectives", "Objetivos vazios", "O perfil não contém objetivos declarados.", [profile.profile_id]))
        if not profile.base_currency.strip():
            result.append(self._add(DataQualitySeverity.ERROR, DataQualityCategory.DECISION_CONTEXT,
                "context.missing_base_currency", "Moeda-base ausente", "O perfil não informa uma moeda-base.",
                [profile.profile_id], can_continue=False))
        if profile.review_date < reference:
            result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.DECISION_CONTEXT,
                "context.review_overdue", "Revisão vencida", "A data de revisão do perfil já passou.", [profile.profile_id]))
        return result

    def _cross(self, positions: tuple[PortfolioPosition, ...], events: tuple[MarketAgendaEvent, ...],
               profile: DecisionProfile | None) -> list[_Diagnostic]:
        result: list[_Diagnostic] = []
        identifiers = {item.identifier.casefold() for item in positions if item.identifier}
        unrelated = [event.event_id for event in events if event.asset_identifiers
                     and not identifiers.intersection(value.casefold() for value in event.asset_identifiers)]
        impossible = [event.event_id for event in events if not any((event.asset_identifiers,
            event.asset_names, event.asset_classes, event.currencies, event.institution))]
        if unrelated:
            result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.CROSS_VALIDATION,
                "cross.agenda_assets_missing", "Ativos da agenda fora da carteira",
                "Há eventos relacionados a identificadores inexistentes na carteira.", unrelated))
        if impossible:
            result.append(self._add(DataQualitySeverity.INFO, DataQualityCategory.CROSS_VALIDATION,
                "cross.events_unrelated", "Eventos sem relacionamento possível",
                "Há eventos sem atributos que permitam relacioná-los à carteira.", impossible))
        if profile is not None and positions:
            owners = {item.owner for item in positions}
            if profile.portfolio_scope is PortfolioScope.COMPANY and owners == {PortfolioOwner.NEI}:
                result.append(self._add(DataQualitySeverity.ERROR, DataQualityCategory.CROSS_VALIDATION,
                    "cross.company_personal", "Contexto incompatível com a carteira",
                    "Um contexto empresarial foi associado a uma carteira pessoal.",
                    [profile.profile_id], can_continue=False))
            currencies = {item.currency.upper() for item in positions if item.currency}
            if currencies and profile.base_currency and profile.base_currency.upper() not in currencies:
                result.append(self._add(DataQualitySeverity.WARNING, DataQualityCategory.CROSS_VALIDATION,
                    "cross.base_currency", "Moeda-base incompatível",
                    "A moeda-base do contexto não aparece nas posições da carteira.", [profile.base_currency]))
        return result


DIAGNOSTIC_FIELDS = frozenset({
    "id", "severity", "category", "title", "description", "affected_items", "can_continue",
})
