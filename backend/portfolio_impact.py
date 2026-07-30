"""Deterministic structural impact of selected facts on a daily snapshot."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import re
import unicodedata

from backend.daily_portfolio_snapshot import DailyPortfolioSnapshot
from backend.important_facts import FactRelevance, ImportantFactsResult


class ImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class ImpactType(str, Enum):
    NONE = "NONE"
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"


@dataclass(frozen=True)
class PortfolioImpact:
    """One immutable structural assessment for one selected fact.

    The three additional collections retain dimensions that exist in the
    current snapshot without incorrectly calling a category a sector or theme.
    """

    fact_id: str
    impact_level: ImpactLevel
    impact_type: ImpactType
    affected_assets: tuple[str, ...]
    affected_sectors: tuple[str, ...]
    affected_currencies: tuple[str, ...]
    affected_countries: tuple[str, ...]
    affected_themes: tuple[str, ...]
    reason: str
    confidence: Decimal
    affected_institutions: tuple[str, ...] = ()
    affected_asset_classes: tuple[str, ...] = ()
    affected_categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        collections = (
            self.affected_assets,
            self.affected_sectors,
            self.affected_currencies,
            self.affected_countries,
            self.affected_themes,
            self.affected_institutions,
            self.affected_asset_classes,
            self.affected_categories,
        )
        if not isinstance(self.fact_id, str):
            raise TypeError("fact_id must be a string")
        if not isinstance(self.impact_level, ImpactLevel):
            raise TypeError("impact_level must be an ImpactLevel")
        if not isinstance(self.impact_type, ImpactType):
            raise TypeError("impact_type must be an ImpactType")
        if any(not isinstance(values, tuple) for values in collections):
            raise TypeError("affected dimensions must be tuples")
        if any(not isinstance(value, str) for values in collections for value in values):
            raise TypeError("affected dimensions accept only strings")
        if any(
            values != tuple(sorted(set(values), key=lambda value: (value.casefold(), value)))
            for values in collections
        ):
            raise ValueError("affected dimensions must be unique and deterministically sorted")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be a Decimal")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class PortfolioImpactSummary:
    fact_count: int
    impact_count: int
    direct_impact_count: int
    indirect_impact_count: int
    high_impact_count: int
    moderate_impact_count: int
    low_impact_count: int
    no_impact_count: int
    affected_asset_count: int
    affected_sector_count: int
    affected_currency_count: int
    affected_country_count: int
    affected_theme_count: int


@dataclass(frozen=True)
class PortfolioImpactResult:
    reference_date: date | None
    generated_at: datetime
    impacts: tuple[PortfolioImpact, ...]
    summary: PortfolioImpactSummary

    def __post_init__(self) -> None:
        if self.reference_date is not None and not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date or None")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must include timezone information")
        if not isinstance(self.impacts, tuple):
            raise TypeError("impacts must be a tuple")
        if any(not isinstance(item, PortfolioImpact) for item in self.impacts):
            raise TypeError("impacts accepts only PortfolioImpact instances")
        if not isinstance(self.summary, PortfolioImpactSummary):
            raise TypeError("summary must be a PortfolioImpactSummary")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioImpactEngine:
    """Relate facts to explicit snapshot dimensions without external inference.

    Exact institution matches are HIGH direct impacts (confidence 0.95). Exact
    currency matches are MODERATE direct impacts (0.85), or HIGH when at least
    two currencies match (0.90). A single class/category match is LOW indirect
    (0.50); two or more are MODERATE indirect (0.65). No match is NONE (0).
    """

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def build(
        self,
        snapshot: DailyPortfolioSnapshot,
        facts_result: ImportantFactsResult,
    ) -> PortfolioImpactResult:
        if not isinstance(snapshot, DailyPortfolioSnapshot):
            raise TypeError("portfolio impact accepts only a DailyPortfolioSnapshot")
        if not isinstance(facts_result, ImportantFactsResult):
            raise TypeError("portfolio impact accepts only an ImportantFactsResult")
        generated_at = self._aware_datetime(self._clock())
        facts = facts_result.important_facts
        relevance = facts_result.relevance
        if any(not isinstance(item.candidate_id, str) for item in relevance):
            raise TypeError("fact relevance candidate_id must be a string")

        impacts = tuple(
            sorted(
                (self._impact(fact.id, snapshot, relevance) for fact in facts),
                key=lambda item: self._text_key(item.fact_id),
            )
        )
        return PortfolioImpactResult(
            reference_date=snapshot.reference_date,
            generated_at=generated_at,
            impacts=impacts,
            summary=self._summary(impacts, len(facts)),
        )

    @classmethod
    def _impact(
        cls,
        fact_id: str,
        snapshot: DailyPortfolioSnapshot,
        relevance: tuple[FactRelevance, ...],
    ) -> PortfolioImpact:
        if not isinstance(fact_id, str):
            raise TypeError("important fact id must be a string")
        matched_terms: set[str] = set()
        for item in relevance:
            if item.candidate_id == fact_id:
                terms = item.matched_portfolio_terms
                if any(not isinstance(term, str) for term in terms):
                    raise TypeError("matched portfolio terms accept only strings")
                matched_terms.update(cls._normalize(term) for term in terms)

        institutions = cls._matched(snapshot.institutions, matched_terms)
        currencies = cls._matched(snapshot.currencies, matched_terms)
        asset_classes = cls._matched(
            tuple(snapshot.consolidated.positions_by_class), matched_terms
        )
        categories = cls._matched(
            tuple(snapshot.consolidated.positions_by_category), matched_terms
        )
        indirect_count = len(asset_classes) + len(categories)
        direct_count = len(institutions) + len(currencies)

        if direct_count:
            level = (
                ImpactLevel.HIGH
                if institutions or direct_count >= 2
                else ImpactLevel.MODERATE
            )
            confidence = (
                Decimal("0.95")
                if institutions
                else Decimal("0.90") if direct_count >= 2 else Decimal("0.85")
            )
            impact_type = ImpactType.DIRECT
        elif indirect_count:
            level = ImpactLevel.MODERATE if indirect_count >= 2 else ImpactLevel.LOW
            confidence = Decimal("0.65") if indirect_count >= 2 else Decimal("0.50")
            impact_type = ImpactType.INDIRECT
        else:
            return cls._no_impact(fact_id)

        reason_parts = []
        for label, values in (
            ("institutions", institutions),
            ("currencies", currencies),
            ("asset classes", asset_classes),
            ("categories", categories),
        ):
            if values:
                reason_parts.append(f"{label}: {', '.join(values)}")
        return PortfolioImpact(
            fact_id=fact_id,
            impact_level=level,
            impact_type=impact_type,
            affected_assets=(),
            affected_sectors=(),
            affected_currencies=currencies,
            affected_countries=(),
            affected_themes=(),
            reason="Explicit structural match with " + "; ".join(reason_parts) + ".",
            confidence=confidence,
            affected_institutions=institutions,
            affected_asset_classes=asset_classes,
            affected_categories=categories,
        )

    @staticmethod
    def _no_impact(fact_id: str) -> PortfolioImpact:
        return PortfolioImpact(
            fact_id=fact_id,
            impact_level=ImpactLevel.NONE,
            impact_type=ImpactType.NONE,
            affected_assets=(),
            affected_sectors=(),
            affected_currencies=(),
            affected_countries=(),
            affected_themes=(),
            reason="No explicit structural match with the portfolio snapshot.",
            confidence=Decimal("0"),
        )

    @classmethod
    def _matched(cls, values: tuple[str, ...], terms: set[str]) -> tuple[str, ...]:
        selected: dict[str, str] = {}
        for value in values:
            normalized = cls._normalize(value)
            if normalized in terms:
                current = selected.get(normalized)
                if current is None or cls._text_key(value) < cls._text_key(current):
                    selected[normalized] = value
        return tuple(sorted(selected.values(), key=cls._text_key))

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()

    @staticmethod
    def _text_key(value: str) -> tuple[str, str]:
        return value.casefold(), value

    @staticmethod
    def _aware_datetime(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("engine clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("engine clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _summary(
        impacts: tuple[PortfolioImpact, ...], fact_count: int
    ) -> PortfolioImpactSummary:
        affected_assets = {value for item in impacts for value in item.affected_assets}
        affected_sectors = {value for item in impacts for value in item.affected_sectors}
        affected_currencies = {
            value for item in impacts for value in item.affected_currencies
        }
        affected_countries = {value for item in impacts for value in item.affected_countries}
        affected_themes = {value for item in impacts for value in item.affected_themes}
        return PortfolioImpactSummary(
            fact_count=fact_count,
            impact_count=sum(item.impact_type is not ImpactType.NONE for item in impacts),
            direct_impact_count=sum(item.impact_type is ImpactType.DIRECT for item in impacts),
            indirect_impact_count=sum(item.impact_type is ImpactType.INDIRECT for item in impacts),
            high_impact_count=sum(item.impact_level is ImpactLevel.HIGH for item in impacts),
            moderate_impact_count=sum(
                item.impact_level is ImpactLevel.MODERATE for item in impacts
            ),
            low_impact_count=sum(item.impact_level is ImpactLevel.LOW for item in impacts),
            no_impact_count=sum(item.impact_level is ImpactLevel.NONE for item in impacts),
            affected_asset_count=len(affected_assets),
            affected_sector_count=len(affected_sectors),
            affected_currency_count=len(affected_currencies),
            affected_country_count=len(affected_countries),
            affected_theme_count=len(affected_themes),
        )
