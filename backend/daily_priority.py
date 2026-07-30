"""Deterministic daily priorities derived from facts and portfolio impacts."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import re
import unicodedata

from backend.daily_brief import DailyPriorityLevel, ImportantFact
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshot
from backend.important_facts import ImportantFactsResult
from backend.portfolio_impact import (
    ImpactLevel,
    ImpactType,
    PortfolioImpact,
    PortfolioImpactResult,
)


class DailyPriorityAction(str, Enum):
    ANALYZE = "ANALYZE"
    DECIDE = "DECIDE"


class AffectedDimensionType(str, Enum):
    INSTITUTION = "institution"
    CURRENCY = "currency"
    ASSET_CLASS = "asset_class"
    CATEGORY = "category"
    ASSET = "asset"
    SECTOR = "sector"
    COUNTRY = "country"
    THEME = "theme"


@dataclass(frozen=True)
class AffectedDimension:
    dimension_type: AffectedDimensionType
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.dimension_type, AffectedDimensionType):
            raise TypeError("dimension_type must be an AffectedDimensionType")
        if not isinstance(self.value, str):
            raise TypeError("dimension value must be a string")
        if not self.value.strip():
            raise ValueError("dimension value must not be empty")


@dataclass(frozen=True)
class DailyPriority:
    priority_id: str
    fact_id: str
    level: DailyPriorityLevel
    action: DailyPriorityAction
    title: str
    reason: str
    impact_type: ImpactType
    impact_level: ImpactLevel
    affected_dimensions: tuple[AffectedDimension, ...]
    confidence: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("priority_id", self.priority_id),
            ("fact_id", self.fact_id),
            ("title", self.title),
            ("reason", self.reason),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.level, DailyPriorityLevel):
            raise TypeError("level must be a DailyPriorityLevel")
        if not isinstance(self.action, DailyPriorityAction):
            raise TypeError("action must be a DailyPriorityAction")
        if not isinstance(self.impact_type, ImpactType):
            raise TypeError("impact_type must be an ImpactType")
        if not isinstance(self.impact_level, ImpactLevel):
            raise TypeError("impact_level must be an ImpactLevel")
        if not isinstance(self.affected_dimensions, tuple):
            raise TypeError("affected_dimensions must be a tuple")
        if any(not isinstance(item, AffectedDimension) for item in self.affected_dimensions):
            raise TypeError("affected_dimensions accepts only AffectedDimension instances")
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be a Decimal")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")
        decide = (
            self.level is DailyPriorityLevel.HIGH
            and self.impact_level is ImpactLevel.HIGH
            and self.impact_type is ImpactType.DIRECT
            and self.confidence >= Decimal("0.90")
        )
        if (self.action is DailyPriorityAction.DECIDE) != decide:
            raise ValueError("DECIDE requires the official HIGH direct impact rule")


@dataclass(frozen=True)
class DailyPrioritySummary:
    fact_count: int
    impact_count: int
    eligible_priority_count: int
    selected_priority_count: int
    high_priority_count: int
    moderate_priority_count: int
    low_priority_count: int
    analyze_count: int
    decide_count: int
    excluded_no_impact_count: int
    excluded_by_limit_count: int

    def __post_init__(self) -> None:
        counts = (
            self.fact_count,
            self.impact_count,
            self.eligible_priority_count,
            self.selected_priority_count,
            self.high_priority_count,
            self.moderate_priority_count,
            self.low_priority_count,
            self.analyze_count,
            self.decide_count,
            self.excluded_no_impact_count,
            self.excluded_by_limit_count,
        )
        if any(not isinstance(value, int) for value in counts):
            raise TypeError("summary counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("summary counts must not be negative")
        if self.selected_priority_count > 3:
            raise ValueError("selected_priority_count must not exceed 3")
        if self.high_priority_count + self.moderate_priority_count + self.low_priority_count != self.selected_priority_count:
            raise ValueError("priority level counts must equal selected_priority_count")
        if self.analyze_count + self.decide_count != self.selected_priority_count:
            raise ValueError("action counts must equal selected_priority_count")
        if self.excluded_by_limit_count != self.eligible_priority_count - self.selected_priority_count:
            raise ValueError("excluded_by_limit_count is inconsistent")


@dataclass(frozen=True)
class DailyPriorityResult:
    reference_date: date | None
    generated_at: datetime
    priorities: tuple[DailyPriority, ...]
    summary: DailyPrioritySummary

    def __post_init__(self) -> None:
        if self.reference_date is not None and not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date or None")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must include timezone information")
        if self.generated_at.utcoffset() != timezone.utc.utcoffset(self.generated_at):
            raise ValueError("generated_at must be normalized to UTC")
        if not isinstance(self.priorities, tuple):
            raise TypeError("priorities must be a tuple")
        if len(self.priorities) > 3:
            raise ValueError("priorities must not contain more than 3 items")
        if any(not isinstance(item, DailyPriority) for item in self.priorities):
            raise TypeError("priorities accepts only DailyPriority instances")
        if not isinstance(self.summary, DailyPrioritySummary):
            raise TypeError("summary must be a DailyPrioritySummary")
        if self.summary.selected_priority_count != len(self.priorities):
            raise ValueError("summary does not match priorities")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DailyPriorityEngine:
    """Select, classify, order, and limit already established impacts."""

    _LEVEL_ORDER = {
        DailyPriorityLevel.HIGH: 0,
        DailyPriorityLevel.MODERATE: 1,
        DailyPriorityLevel.LOW: 2,
    }
    _TYPE_ORDER = {ImpactType.DIRECT: 0, ImpactType.INDIRECT: 1}
    _IMPACT_ORDER = {
        ImpactLevel.HIGH: 0,
        ImpactLevel.MODERATE: 1,
        ImpactLevel.LOW: 2,
    }
    _IMPORTANCE_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    _DIMENSIONS = (
        (AffectedDimensionType.INSTITUTION, "instituições", "affected_institutions"),
        (AffectedDimensionType.CURRENCY, "moedas", "affected_currencies"),
        (AffectedDimensionType.ASSET_CLASS, "classes de ativos", "affected_asset_classes"),
        (AffectedDimensionType.CATEGORY, "categorias", "affected_categories"),
        (AffectedDimensionType.ASSET, "ativos", "affected_assets"),
        (AffectedDimensionType.SECTOR, "setores", "affected_sectors"),
        (AffectedDimensionType.COUNTRY, "países", "affected_countries"),
        (AffectedDimensionType.THEME, "temas", "affected_themes"),
    )

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def build(
        self,
        snapshot: DailyPortfolioSnapshot,
        facts_result: ImportantFactsResult,
        impact_result: PortfolioImpactResult,
    ) -> DailyPriorityResult:
        if not isinstance(snapshot, DailyPortfolioSnapshot):
            raise TypeError("daily priority accepts only a DailyPortfolioSnapshot")
        if not isinstance(facts_result, ImportantFactsResult):
            raise TypeError("daily priority accepts only an ImportantFactsResult")
        if not isinstance(impact_result, PortfolioImpactResult):
            raise TypeError("daily priority accepts only a PortfolioImpactResult")
        if impact_result.reference_date != snapshot.reference_date:
            raise ValueError("impact result reference_date must match snapshot")
        generated_at = self._aware_utc(self._clock())
        facts = self._fact_map(facts_result.important_facts)
        impacts = self._impact_map(impact_result.impacts, facts)

        eligible: list[tuple[DailyPriority, int]] = []
        excluded = 0
        for fact_id, impact in impacts.items():
            dimensions = self._dimensions(impact)
            if not self._eligible(impact, dimensions):
                excluded += 1
                continue
            fact = facts[fact_id]
            eligible.append((self._priority(fact, impact, dimensions), self._importance(fact)))
        eligible.sort(key=lambda item: self._sort_key(item[0], item[1]))
        priorities = tuple(item[0] for item in eligible[:3])
        return DailyPriorityResult(
            reference_date=snapshot.reference_date,
            generated_at=generated_at,
            priorities=priorities,
            summary=self._summary(
                priorities, len(facts_result.important_facts), len(impact_result.impacts),
                len(eligible), excluded,
            ),
        )

    @classmethod
    def _fact_map(cls, facts: tuple[ImportantFact, ...]) -> dict[str, ImportantFact]:
        result: dict[str, ImportantFact] = {}
        for fact in facts:
            if not isinstance(fact, ImportantFact):
                raise TypeError("important_facts accepts only ImportantFact instances")
            if not isinstance(fact.id, str) or not fact.id.strip():
                raise ValueError("fact id must be a non-empty string")
            key = cls._normalize(fact.id)
            if key in result:
                raise ValueError("important fact ids must be unique")
            if not isinstance(fact.title, str) or not fact.title.strip():
                raise ValueError("fact title must be a non-empty string")
            result[key] = fact
        return result

    @classmethod
    def _impact_map(
        cls, impacts: tuple[PortfolioImpact, ...], facts: dict[str, ImportantFact]
    ) -> dict[str, PortfolioImpact]:
        result: dict[str, PortfolioImpact] = {}
        for impact in impacts:
            if not isinstance(impact, PortfolioImpact):
                raise TypeError("impacts accepts only PortfolioImpact instances")
            key = cls._normalize(impact.fact_id)
            if key not in facts:
                raise ValueError("every impact must reference an existing fact_id")
            if key in result:
                raise ValueError("impact fact_ids must be unique")
            result[key] = impact
        return result

    @classmethod
    def _dimensions(cls, impact: PortfolioImpact) -> tuple[AffectedDimension, ...]:
        dimensions: list[AffectedDimension] = []
        for dimension_type, _, field_name in cls._DIMENSIONS:
            values: tuple[str, ...]
            if field_name == "affected_institutions":
                values = impact.affected_institutions
            elif field_name == "affected_currencies":
                values = impact.affected_currencies
            elif field_name == "affected_asset_classes":
                values = impact.affected_asset_classes
            elif field_name == "affected_categories":
                values = impact.affected_categories
            elif field_name == "affected_assets":
                values = impact.affected_assets
            elif field_name == "affected_sectors":
                values = impact.affected_sectors
            elif field_name == "affected_countries":
                values = impact.affected_countries
            else:
                values = impact.affected_themes
            selected: dict[str, str] = {}
            for value in values:
                normalized = cls._normalize(value)
                if not normalized:
                    continue
                current = selected.get(normalized)
                if current is None or cls._text_key(value) < cls._text_key(current):
                    selected[normalized] = value
            dimensions.extend(
                AffectedDimension(dimension_type, value)
                for value in sorted(selected.values(), key=cls._text_key)
            )
        return tuple(dimensions)

    @staticmethod
    def _eligible(
        impact: PortfolioImpact, dimensions: tuple[AffectedDimension, ...]
    ) -> bool:
        return (
            impact.impact_level is not ImpactLevel.NONE
            and impact.impact_type is not ImpactType.NONE
            and impact.confidence > Decimal("0")
            and bool(dimensions)
        )

    @classmethod
    def _priority(
        cls,
        fact: ImportantFact,
        impact: PortfolioImpact,
        dimensions: tuple[AffectedDimension, ...],
    ) -> DailyPriority:
        decide = (
            impact.impact_level is ImpactLevel.HIGH
            and impact.impact_type is ImpactType.DIRECT
            and impact.confidence >= Decimal("0.90")
        )
        if decide:
            level = DailyPriorityLevel.HIGH
            action = DailyPriorityAction.DECIDE
        elif (
            impact.impact_level is ImpactLevel.HIGH
            or (impact.impact_level is ImpactLevel.MODERATE and impact.impact_type is ImpactType.DIRECT)
            or (impact.impact_level is ImpactLevel.MODERATE and impact.confidence >= Decimal("0.65"))
            or len(dimensions) > 1
        ):
            level = DailyPriorityLevel.MODERATE
            action = DailyPriorityAction.ANALYZE
        else:
            level = DailyPriorityLevel.LOW
            action = DailyPriorityAction.ANALYZE
        return DailyPriority(
            priority_id=f"priority:{fact.id}",
            fact_id=fact.id,
            level=level,
            action=action,
            title=fact.title,
            reason=cls._reason(impact, dimensions),
            impact_type=impact.impact_type,
            impact_level=impact.impact_level,
            affected_dimensions=dimensions,
            confidence=impact.confidence,
        )

    @classmethod
    def _reason(
        cls, impact: PortfolioImpact, dimensions: tuple[AffectedDimension, ...]
    ) -> str:
        values: dict[AffectedDimensionType, list[str]] = {}
        for item in dimensions:
            values.setdefault(item.dimension_type, []).append(item.value)
        parts = [
            f"{label}: {', '.join(values[dimension_type])}"
            for dimension_type, label, _ in cls._DIMENSIONS
            if dimension_type in values
        ]
        return (
            f"Impacto {impact.impact_type.value.casefold()} "
            f"{impact.impact_level.value.casefold()} sobre dimensões presentes na carteira: "
            + "; ".join(parts)
            + "."
        )

    @classmethod
    def _sort_key(cls, priority: DailyPriority, importance: int) -> tuple[object, ...]:
        return (
            cls._LEVEL_ORDER[priority.level],
            cls._TYPE_ORDER[priority.impact_type],
            cls._IMPACT_ORDER[priority.impact_level],
            -priority.confidence,
            importance,
            cls._text_key(priority.fact_id),
        )

    @classmethod
    def _importance(cls, fact: ImportantFact) -> int:
        return cls._IMPORTANCE_ORDER.get(fact.priority.strip().upper(), len(cls._IMPORTANCE_ORDER))

    @staticmethod
    def _summary(
        priorities: tuple[DailyPriority, ...], fact_count: int, impact_count: int,
        eligible_count: int, excluded_count: int,
    ) -> DailyPrioritySummary:
        return DailyPrioritySummary(
            fact_count=fact_count,
            impact_count=impact_count,
            eligible_priority_count=eligible_count,
            selected_priority_count=len(priorities),
            high_priority_count=sum(item.level is DailyPriorityLevel.HIGH for item in priorities),
            moderate_priority_count=sum(item.level is DailyPriorityLevel.MODERATE for item in priorities),
            low_priority_count=sum(item.level is DailyPriorityLevel.LOW for item in priorities),
            analyze_count=sum(item.action is DailyPriorityAction.ANALYZE for item in priorities),
            decide_count=sum(item.action is DailyPriorityAction.DECIDE for item in priorities),
            excluded_no_impact_count=excluded_count,
            excluded_by_limit_count=eligible_count - len(priorities),
        )

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("engine clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("engine clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()

    @staticmethod
    def _text_key(value: str) -> tuple[str, str]:
        return value.casefold(), value
