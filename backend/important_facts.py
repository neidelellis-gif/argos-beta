"""Deterministic selection of important facts for the ARGOS daily opening."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
import unicodedata

from backend.daily_brief import ImportantFact
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshot


class FactImportance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FactCategory(str, Enum):
    MARKETS = "MARKETS"
    ECONOMY = "ECONOMY"
    GEOPOLITICS = "GEOPOLITICS"
    CORPORATE = "CORPORATE"
    REGULATION = "REGULATION"
    OTHER = "OTHER"


@dataclass(frozen=True)
class FactCandidate:
    """A structured fact supplied by a source outside this engine."""

    id: str
    title: str
    description: str
    source: str
    published_at: datetime
    importance: FactImportance
    category: FactCategory
    urgency: FactImportance = FactImportance.LOW
    related_assets: tuple[str, ...] = ()
    related_sectors: tuple[str, ...] = ()
    related_currencies: tuple[str, ...] = ()
    related_institutions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        relation_fields = (
            self.related_assets,
            self.related_sectors,
            self.related_currencies,
            self.related_institutions,
        )
        if any(not isinstance(values, tuple) for values in relation_fields):
            raise TypeError("fact relations must be tuples")
        if any(
            not isinstance(value, str)
            for values in relation_fields
            for value in values
        ):
            raise TypeError("fact relations accept only strings")

    @property
    def fact_id(self) -> str:
        """Official market-data name retained without changing engine compatibility."""
        return self.id

    @property
    def reference_date(self):
        """Calendar date represented by the source publication timestamp."""
        return self.published_at.date()


# The official repository and the legacy analytical contract share one immutable
# representation.  Keeping the alias avoids a translation model inside engines.
MarketFact = FactCandidate


@dataclass(frozen=True)
class FactRelevance:
    """Traceable explanation of the score assigned to one selected fact."""

    candidate_id: str
    score: int
    portfolio_related: bool
    matched_portfolio_terms: tuple[str, ...]


@dataclass(frozen=True)
class ImportantFactsResult:
    important_facts: tuple[ImportantFact, ...]
    relevance: tuple[FactRelevance, ...]
    rejected_ids: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImportantFactsEngine:
    """Validate, rank and deduplicate supplied facts without external access."""

    _IMPORTANCE_SCORE = {
        FactImportance.LOW: 10,
        FactImportance.MEDIUM: 30,
        FactImportance.HIGH: 60,
        FactImportance.CRITICAL: 90,
    }
    _CATEGORY_SCORE = {
        FactCategory.GEOPOLITICS: 12,
        FactCategory.ECONOMY: 10,
        FactCategory.MARKETS: 10,
        FactCategory.REGULATION: 8,
        FactCategory.CORPORATE: 6,
        FactCategory.OTHER: 0,
    }

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def select(
        self,
        candidates: Iterable[FactCandidate],
        snapshot: DailyPortfolioSnapshot,
    ) -> ImportantFactsResult:
        if not isinstance(snapshot, DailyPortfolioSnapshot):
            raise TypeError("important facts accepts only a DailyPortfolioSnapshot")
        items = tuple(candidates)
        if any(not isinstance(item, FactCandidate) for item in items):
            raise TypeError("candidates accepts only FactCandidate instances")

        now = self._aware_utc(self._clock(), "engine clock")
        portfolio_terms = self._portfolio_terms(snapshot)
        ranked: list[tuple[tuple[object, ...], FactCandidate, FactRelevance]] = []
        rejected: list[str] = []
        for item in items:
            if not self._valid(item, now):
                rejected.append(item.id if isinstance(item.id, str) else "")
                continue
            matched = tuple(sorted(self._candidate_terms(item) & portfolio_terms))
            age = now - item.published_at.astimezone(timezone.utc)
            freshness = max(0, 24 - int(age.total_seconds() // 3600))
            score = (
                self._IMPORTANCE_SCORE[item.importance]
                + self._IMPORTANCE_SCORE[item.urgency] // 3
                + self._CATEGORY_SCORE[item.category]
                + freshness
                + (35 if matched else 0)
            )
            relevance = FactRelevance(item.id, score, bool(matched), matched)
            ranked.append((self._rank_key(item, score), item, relevance))

        selected: list[tuple[FactCandidate, FactRelevance]] = []
        duplicate_ids: set[str] = set()
        duplicate_titles: set[str] = set()
        for _, item, relevance in sorted(ranked, key=lambda value: value[0]):
            identifier = self._normalize(item.id)
            title = self._normalize(item.title)
            if identifier in duplicate_ids or title in duplicate_titles:
                rejected.append(item.id)
                continue
            duplicate_ids.add(identifier)
            duplicate_titles.add(title)
            selected.append((item, relevance))
            if len(selected) == 5:
                break

        return ImportantFactsResult(
            important_facts=tuple(self._important_fact(item) for item, _ in selected),
            relevance=tuple(relevance for _, relevance in selected),
            rejected_ids=tuple(sorted(rejected, key=self._text_key)),
        )

    # ``build`` follows the naming used by the other daily engines.
    build = select

    def _valid(self, item: FactCandidate, now: datetime) -> bool:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (item.id, item.title, item.description, item.source)
        ):
            return False
        if not isinstance(item.importance, FactImportance):
            return False
        if not isinstance(item.urgency, FactImportance):
            return False
        if not isinstance(item.category, FactCategory):
            return False
        try:
            published_at = self._aware_utc(item.published_at, "published_at")
        except (TypeError, ValueError):
            return False
        return now - timedelta(hours=24) <= published_at <= now

    @staticmethod
    def _aware_utc(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include timezone information")
        return value.astimezone(timezone.utc)

    @classmethod
    def _portfolio_terms(cls, snapshot: DailyPortfolioSnapshot) -> set[str]:
        values: set[str] = set(snapshot.institutions) | set(snapshot.currencies)
        values.update(snapshot.consolidated.positions_by_class)
        values.update(snapshot.consolidated.positions_by_category)
        return {cls._normalize(value) for value in values if value}

    @classmethod
    def _candidate_terms(cls, item: FactCandidate) -> set[str]:
        values = (
            item.related_assets
            + item.related_sectors
            + item.related_currencies
            + item.related_institutions
        )
        return {cls._normalize(value) for value in values if isinstance(value, str)}

    @classmethod
    def _rank_key(cls, item: FactCandidate, score: int) -> tuple[object, ...]:
        return (
            -score,
            -item.published_at.timestamp(),
            cls._text_key(item.title),
            cls._text_key(item.source),
            cls._text_key(item.id),
        )

    @staticmethod
    def _important_fact(item: FactCandidate) -> ImportantFact:
        return ImportantFact(
            id=item.id,
            priority=item.importance.value,
            category=item.category.value,
            title=item.title,
            description=item.description,
            source=item.source,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()

    @staticmethod
    def _text_key(value: str) -> tuple[str, str]:
        return value.casefold(), value
