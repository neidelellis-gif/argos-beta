"""Immutable daily brief contracts built exclusively from a portfolio snapshot."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import TypeVar

from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshot,
    DailyPortfolioStatus,
)
from backend.import_validation import ImportValidationStatus
from backend.models import PortfolioOwner


BriefItem = TypeVar("BriefItem")


class DailyBriefStatus(str, Enum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    EMPTY = "EMPTY"


class DailyPriorityLevel(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class AnalysisType(str, Enum):
    ANALYZE = "ANALYZE"
    DECIDE = "DECIDE"


@dataclass(frozen=True)
class ImportantFact:
    id: str
    priority: str
    category: str
    title: str
    description: str
    source: str


@dataclass(frozen=True)
class DailyPriority:
    level: DailyPriorityLevel
    title: str
    description: str
    reason: str


@dataclass(frozen=True)
class AnalysisItem:
    title: str
    description: str
    type: AnalysisType
    origin: str


@dataclass(frozen=True)
class MarketAgendaItem:
    date: date
    title: str
    category: str
    importance: str
    source: str


@dataclass(frozen=True)
class PortfolioHealth:
    """Operational state copied from snapshot status and summary data."""

    status: DailyBriefStatus
    validation_status: tuple[ImportValidationStatus, ...]
    institution_count: int
    owner_count: int
    position_count: int
    asset_count: int
    warning_count: int
    error_count: int
    duplicate_count: int


@dataclass(frozen=True)
class DailyBrief:
    reference_date: date | None
    generated_at: datetime
    status: DailyBriefStatus
    owners: tuple[PortfolioOwner, ...]
    institutions: tuple[str, ...]
    currencies: tuple[str, ...]
    portfolio_health: PortfolioHealth
    important_facts: tuple[ImportantFact, ...]
    priorities: tuple[DailyPriority, ...]
    analyses: tuple[AnalysisItem, ...]
    market_agenda: tuple[MarketAgendaItem, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DailyBriefEngine:
    """Organize structured content without consulting portfolio data sources.

    When priorities share a level, the lexicographically smallest complete
    content key is retained. This makes selection independent of input order.
    """

    _STATUS_MAP = {
        DailyPortfolioStatus.READY: DailyBriefStatus.READY,
        DailyPortfolioStatus.READY_WITH_WARNINGS: DailyBriefStatus.READY_WITH_WARNINGS,
        DailyPortfolioStatus.BLOCKED: DailyBriefStatus.BLOCKED,
        DailyPortfolioStatus.EMPTY: DailyBriefStatus.EMPTY,
    }
    _PRIORITY_ORDER = {
        DailyPriorityLevel.HIGH: 0,
        DailyPriorityLevel.MODERATE: 1,
        DailyPriorityLevel.LOW: 2,
    }
    _ANALYSIS_ORDER = {AnalysisType.ANALYZE: 0, AnalysisType.DECIDE: 1}

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def build(
        self,
        snapshot: DailyPortfolioSnapshot,
        *,
        important_facts: Iterable[ImportantFact] = (),
        priorities: Iterable[DailyPriority] = (),
        analyses: Iterable[AnalysisItem] = (),
        market_agenda: Iterable[MarketAgendaItem] = (),
    ) -> DailyBrief:
        if not isinstance(snapshot, DailyPortfolioSnapshot):
            raise TypeError("daily brief accepts only a DailyPortfolioSnapshot")

        facts = self._validated_tuple(important_facts, ImportantFact, "important_facts")
        priority_items = self._validated_tuple(priorities, DailyPriority, "priorities")
        analysis_items = self._validated_tuple(analyses, AnalysisItem, "analyses")
        agenda_items = self._validated_tuple(
            market_agenda, MarketAgendaItem, "market_agenda"
        )
        status = self._STATUS_MAP[snapshot.status]
        summary = snapshot.summary
        validation_status = tuple(
            sorted(
                (item.validation_status for item in snapshot.institution_snapshots),
                key=lambda item: item.value,
            )
        )

        return DailyBrief(
            reference_date=snapshot.reference_date,
            generated_at=self._clock(),
            status=status,
            owners=tuple(sorted(snapshot.owners, key=lambda item: item.value)),
            institutions=tuple(sorted(snapshot.institutions, key=self._text_key)),
            currencies=tuple(sorted(snapshot.currencies, key=self._text_key)),
            portfolio_health=PortfolioHealth(
                status=status,
                validation_status=validation_status,
                institution_count=summary.institution_count,
                owner_count=summary.owner_count,
                position_count=summary.original_position_count,
                asset_count=summary.consolidated_asset_count,
                warning_count=summary.validation_warning_count,
                error_count=summary.validation_error_count,
                duplicate_count=summary.duplicate_count,
            ),
            important_facts=tuple(sorted(facts, key=self._fact_key)[:5]),
            priorities=self._priorities(priority_items),
            analyses=tuple(sorted(analysis_items, key=self._analysis_key)[:2]),
            market_agenda=tuple(sorted(agenda_items, key=self._agenda_key)),
        )

    @staticmethod
    def _validated_tuple(
        values: Iterable[BriefItem], expected: type[BriefItem], name: str
    ) -> tuple[BriefItem, ...]:
        items = tuple(values)
        if any(not isinstance(item, expected) for item in items):
            raise TypeError(f"{name} accepts only {expected.__name__} instances")
        return items

    def _priorities(
        self, priorities: tuple[DailyPriority, ...]
    ) -> tuple[DailyPriority, ...]:
        selected: dict[DailyPriorityLevel, DailyPriority] = {}
        for priority in sorted(priorities, key=self._priority_key):
            selected.setdefault(priority.level, priority)
        return tuple(sorted(selected.values(), key=self._priority_key))

    @staticmethod
    def _text_key(value: str) -> tuple[str, str]:
        return value.casefold(), value

    @staticmethod
    def _fact_key(item: ImportantFact) -> tuple[str, ...]:
        return (
            item.priority.casefold(), item.priority,
            item.category.casefold(), item.category,
            item.title.casefold(), item.title,
            item.description.casefold(), item.description,
            item.source.casefold(), item.source,
            item.id.casefold(), item.id,
        )

    def _priority_key(
        self, item: DailyPriority
    ) -> tuple[int, str, str, str, str, str, str]:
        return (
            self._PRIORITY_ORDER[item.level],
            item.title.casefold(), item.title,
            item.description.casefold(), item.description,
            item.reason.casefold(), item.reason,
        )

    def _analysis_key(
        self, item: AnalysisItem
    ) -> tuple[int, str, str, str, str, str, str]:
        return (
            self._ANALYSIS_ORDER[item.type],
            item.title.casefold(), item.title,
            item.description.casefold(), item.description,
            item.origin.casefold(), item.origin,
        )

    @staticmethod
    def _agenda_key(
        item: MarketAgendaItem,
    ) -> tuple[date, str, str, str, str, str, str, str, str]:
        return (
            item.date,
            item.title.casefold(), item.title,
            item.category.casefold(), item.category,
            item.importance.casefold(), item.importance,
            item.source.casefold(), item.source,
        )
