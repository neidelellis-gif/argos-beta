"""Official consolidation engine for validated MPU portfolio positions.

This layer only consumes :class:`PortfolioPosition` instances.  It neither
knows how they were imported nor changes the original positions.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Tuple

from backend.models import PortfolioOwner, PortfolioPosition


@dataclass(frozen=True)
class PositionOrigin:
    """Traceable origin of one position included in a consolidated asset."""

    institution: str
    owner: PortfolioOwner
    original_identifier: Optional[str]
    source_file: str
    original_position: PortfolioPosition


@dataclass(frozen=True)
class ConsolidatedPosition:
    """Economic asset totals accompanied by every untouched source row."""

    owner: PortfolioOwner
    asset_name: Optional[str]
    identifier: Optional[str]
    identifier_type: Optional[str]
    asset_class: Optional[str]
    asset_category: Optional[str]
    currency: Optional[str]
    market_value: Decimal
    quantity: Optional[Decimal]
    origins: Tuple[PositionOrigin, ...]


@dataclass(frozen=True)
class DuplicatePosition:
    """A repeated economic position; originals remain available in ``origins``."""

    owner: PortfolioOwner
    asset_key: str
    institutions: Tuple[str, ...]
    within_same_institution: bool
    across_institutions: bool
    origins: Tuple[PositionOrigin, ...]


@dataclass(frozen=True)
class ConsolidationStatistics:
    """Standard counters and financial totals for a consolidation."""

    consolidated_value_by_currency: Mapping[str, Decimal]
    positions_by_institution: Mapping[str, int]
    positions_by_owner: Mapping[str, int]
    positions_by_class: Mapping[str, int]
    positions_by_category: Mapping[str, int]
    unique_assets: int
    original_positions: int


@dataclass(frozen=True)
class ConsolidationReport:
    """Auditable report produced together with every consolidated portfolio."""

    statistics: ConsolidationStatistics
    alerts: Tuple[str, ...]
    duplicates: Tuple[DuplicatePosition, ...]
    summary: str


@dataclass(frozen=True)
class ConsolidatedPortfolio:
    """Deterministic consolidated view and its standardized report."""

    positions: Tuple[ConsolidatedPosition, ...]
    report: ConsolidationReport


class PortfolioConsolidationEngine:
    """Consolidate economically equivalent, already validated MPU positions."""

    def consolidate(
        self, *portfolios: Iterable[PortfolioPosition]
    ) -> ConsolidatedPortfolio:
        """Consolidate one or more portfolios without mutating their positions.

        Owners and currencies are part of the economic key.  Consequently,
        JOLIKA and NEI are always kept separate, as are values denominated in
        different currencies.
        """
        originals = self._flatten(portfolios)
        groups = defaultdict(list)
        for position in originals:
            groups[self._economic_key(position)].append(position)

        consolidated = tuple(
            self._consolidate_group(groups[key]) for key in sorted(groups)
        )
        duplicates = tuple(
            self._duplicate(groups[key], key)
            for key in sorted(groups)
            if len(groups[key]) > 1
        )
        statistics = self._statistics(originals, consolidated)
        alerts = self._alerts(duplicates)
        summary = (
            f"{len(originals)} original position(s) consolidated into "
            f"{len(consolidated)} unique asset(s); "
            f"{len(duplicates)} duplicate group(s) recorded."
        )
        return ConsolidatedPortfolio(
            positions=consolidated,
            report=ConsolidationReport(statistics, alerts, duplicates, summary),
        )

    @staticmethod
    def _flatten(
        portfolios: Tuple[Iterable[PortfolioPosition], ...]
    ) -> Tuple[PortfolioPosition, ...]:
        originals = []
        for portfolio in portfolios:
            if isinstance(portfolio, PortfolioPosition):
                candidates = (portfolio,)
            else:
                candidates = portfolio
            for position in candidates:
                if not isinstance(position, PortfolioPosition):
                    raise TypeError("consolidation accepts only PortfolioPosition instances")
                originals.append(position)
        return tuple(originals)

    @classmethod
    def _economic_key(cls, position: PortfolioPosition) -> tuple:
        identifier = cls._normalized(position.identifier)
        name = cls._normalized(position.asset_name)
        identity_kind = "identifier" if identifier else "name"
        identity = identifier or name
        if not identity:
            # Validated inputs normally have a name. This fallback prevents two
            # unidentified source rows from being silently treated as one asset.
            identity_kind = "source"
            identity = "|".join(
                (cls._normalized(position.institution), position.source_file)
            )
        return (
            position.owner.value,
            cls._normalized(position.currency),
            identity_kind,
            cls._normalized(position.identifier_type) if identifier else "",
            identity,
        )

    @staticmethod
    def _normalized(value: Optional[str]) -> str:
        return " ".join(str(value or "").split()).casefold()

    @classmethod
    def _consolidate_group(
        cls, positions: Iterable[PortfolioPosition]
    ) -> ConsolidatedPosition:
        ordered = tuple(sorted(positions, key=cls._source_sort_key))
        first = ordered[0]
        quantities = tuple(position.quantity for position in ordered)
        quantity = (
            sum(quantities, Decimal("0"))
            if all(value is not None for value in quantities)
            else None
        )
        market_value = sum(
            (position.market_value or Decimal("0") for position in ordered),
            Decimal("0"),
        )
        return ConsolidatedPosition(
            owner=first.owner,
            asset_name=cls._representative(ordered, "asset_name"),
            identifier=cls._representative(ordered, "identifier"),
            identifier_type=cls._representative(ordered, "identifier_type"),
            asset_class=cls._representative(ordered, "asset_class"),
            asset_category=cls._representative(ordered, "asset_subclass"),
            currency=cls._representative(ordered, "currency"),
            market_value=market_value,
            quantity=quantity,
            origins=tuple(cls._origin(position) for position in ordered),
        )

    @classmethod
    def _representative(
        cls, positions: Iterable[PortfolioPosition], attribute: str
    ) -> Optional[str]:
        values = {
            str(value).strip()
            for position in positions
            if (value := getattr(position, attribute)) is not None
            and str(value).strip()
        }
        return min(values, key=lambda value: (value.casefold(), value)) if values else None

    @classmethod
    def _source_sort_key(cls, position: PortfolioPosition) -> tuple:
        return (
            position.owner.value,
            cls._normalized(position.institution),
            cls._normalized(position.account),
            position.source_file,
            cls._normalized(position.identifier),
            cls._normalized(position.identifier_type),
            cls._normalized(position.asset_name),
            cls._normalized(position.asset_class),
            cls._normalized(position.asset_subclass),
            cls._normalized(position.currency),
            str(position.market_value),
            str(position.quantity),
            str(position.unit_price),
            str(position.portfolio_weight),
            str(position.reference_date),
        )

    @staticmethod
    def _origin(position: PortfolioPosition) -> PositionOrigin:
        return PositionOrigin(
            institution=position.institution,
            owner=position.owner,
            original_identifier=position.identifier,
            source_file=position.source_file,
            original_position=position,
        )

    @classmethod
    def _duplicate(cls, positions: Iterable[PortfolioPosition], key: tuple) -> DuplicatePosition:
        ordered = tuple(sorted(positions, key=cls._source_sort_key))
        institution_counts = Counter(position.institution for position in ordered)
        institutions = tuple(sorted(institution_counts, key=str.casefold))
        return DuplicatePosition(
            owner=ordered[0].owner,
            asset_key=key[-1],
            institutions=institutions,
            within_same_institution=any(count > 1 for count in institution_counts.values()),
            across_institutions=len(institutions) > 1,
            origins=tuple(cls._origin(position) for position in ordered),
        )

    @staticmethod
    def _statistics(
        originals: Tuple[PortfolioPosition, ...],
        consolidated: Tuple[ConsolidatedPosition, ...],
    ) -> ConsolidationStatistics:
        institutions = Counter(position.institution for position in originals)
        owners = Counter(position.owner.value for position in originals)
        classes = Counter(position.asset_class for position in originals if position.asset_class)
        categories = Counter(
            position.asset_subclass for position in originals if position.asset_subclass
        )
        totals = Counter()
        for position in originals:
            if position.currency and position.market_value is not None:
                totals[position.currency] += position.market_value
        return ConsolidationStatistics(
            consolidated_value_by_currency=dict(sorted(totals.items())),
            positions_by_institution=dict(sorted(institutions.items())),
            positions_by_owner=dict(sorted(owners.items())),
            positions_by_class=dict(sorted(classes.items())),
            positions_by_category=dict(sorted(categories.items())),
            unique_assets=len(consolidated),
            original_positions=len(originals),
        )

    @staticmethod
    def _alerts(duplicates: Tuple[DuplicatePosition, ...]) -> Tuple[str, ...]:
        alerts = []
        if any(item.within_same_institution for item in duplicates):
            alerts.append("Duplicate positions found within the same institution")
        if any(item.across_institutions for item in duplicates):
            alerts.append("Duplicate positions found across institutions")
        return tuple(alerts)


# Backwards-compatible view used by the current dashboard pipeline.  The
# official engine above is intentionally additive and does not change callers.
@dataclass(frozen=True)
class PortfolioConsolidation:
    """Institution views followed by a distinct, currency-safe total view."""

    positions_by_institution: Mapping[str, Tuple[PortfolioPosition, ...]]
    consolidated_positions: Tuple[PortfolioPosition, ...]
    totals_by_currency: Mapping[str, Decimal]


def consolidate_portfolio_positions(
    positions: Iterable[PortfolioPosition],
) -> PortfolioConsolidation:
    """Build the legacy source-position view without changing its contract."""
    original_positions = tuple(positions)
    grouped = defaultdict(list)
    totals = Counter()
    for position in original_positions:
        grouped[position.institution].append(position)
        if position.currency is not None and position.market_value is not None:
            totals[position.currency] += position.market_value
    return PortfolioConsolidation(
        positions_by_institution={key: tuple(value) for key, value in grouped.items()},
        consolidated_positions=original_positions,
        totals_by_currency=dict(totals),
    )
