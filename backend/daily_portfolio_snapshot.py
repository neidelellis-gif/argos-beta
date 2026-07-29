"""Immutable daily portfolio snapshot built from the official portfolio engines."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Tuple, TypeVar

from backend.import_validation import (
    ImportValidationEngine,
    ImportValidationReport,
    ImportValidationStatus,
)
from backend.models import PortfolioOwner, PortfolioPosition
from backend.portfolio_consolidation import PortfolioConsolidationEngine


class DailyPortfolioStatus(str, Enum):
    """Readiness of the imported portfolio for its daily use."""

    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    EMPTY = "EMPTY"


@dataclass(frozen=True)
class InstitutionPortfolioSnapshot:
    """Validation and distribution view isolated by owner, institution and currency."""

    owner: PortfolioOwner
    institution: str
    currency: Optional[str]
    position_count: int
    gross_value: Decimal
    positions_by_class: Mapping[str, int]
    positions_by_category: Mapping[str, int]
    unique_assets: int
    validation_status: ImportValidationStatus
    validation_errors: Tuple[str, ...]
    validation_warnings: Tuple[str, ...]


@dataclass(frozen=True)
class ConsolidatedPortfolioSnapshot:
    """Currency-safe global figures produced after all institution views."""

    position_count: int
    unique_assets: int
    gross_value_by_currency: Mapping[str, Decimal]
    positions_by_owner: Mapping[str, int]
    positions_by_institution: Mapping[str, int]
    positions_by_class: Mapping[str, int]
    positions_by_category: Mapping[str, int]
    duplicate_count: int
    warnings: Tuple[str, ...]


@dataclass(frozen=True)
class DailyPortfolioSummary:
    """Small operational summary derived from validation and consolidation reports."""

    institution_count: int
    owner_count: int
    original_position_count: int
    consolidated_asset_count: int
    validation_error_count: int
    validation_warning_count: int
    duplicate_count: int


@dataclass(frozen=True)
class DailyPortfolioSnapshot:
    """Official immutable daily representation of normalized portfolio positions."""

    reference_date: Optional[date]
    generated_at: datetime
    owners: Tuple[PortfolioOwner, ...]
    institutions: Tuple[str, ...]
    currencies: Tuple[str, ...]
    institution_snapshots: Tuple[InstitutionPortfolioSnapshot, ...]
    consolidated: ConsolidatedPortfolioSnapshot
    status: DailyPortfolioStatus
    summary: DailyPortfolioSummary


ValidationReportKey = Tuple[PortfolioOwner, str, Optional[str]]
MapValue = TypeVar("MapValue")


class DailyPortfolioSnapshotBuilder:
    """Build institution diagnostics first and a consolidated snapshot second.

    Supplied reports are keyed by ``(owner, institution, currency)``. A key with
    ``currency=None`` is also accepted for a single-currency institution. Missing
    reports are produced by :class:`ImportValidationEngine`.
    """

    def __init__(
        self,
        validation_engine: Optional[ImportValidationEngine] = None,
        consolidation_engine: Optional[PortfolioConsolidationEngine] = None,
    ) -> None:
        self._validation_engine = validation_engine or ImportValidationEngine()
        self._consolidation_engine = consolidation_engine or PortfolioConsolidationEngine()

    def build(
        self,
        positions: Iterable[PortfolioPosition],
        reference_date: Optional[date] = None,
        validation_reports: Optional[Mapping[ValidationReportKey, ImportValidationReport]] = None,
    ) -> DailyPortfolioSnapshot:
        originals = tuple(positions)
        self._ensure_positions(originals)
        reports = validation_reports or {}
        groups = self._group_positions(originals)

        institution_snapshots = []
        reports_used = []
        for key in sorted(groups, key=self._group_sort_key):
            group = tuple(groups[key])
            report = self._report_for(key, group, reports)
            reports_used.append(report)
            institution_consolidation = self._consolidation_engine.consolidate(group)
            validation_statistics = report.statistics
            institution_snapshots.append(
                InstitutionPortfolioSnapshot(
                    owner=key[0],
                    institution=key[1],
                    currency=key[2],
                    position_count=validation_statistics.total_positions,
                    gross_value=validation_statistics.gross_value,
                    positions_by_class=self._frozen_map(
                        validation_statistics.positions_by_class
                    ),
                    positions_by_category=self._frozen_map(
                        validation_statistics.positions_by_category
                    ),
                    unique_assets=institution_consolidation.report.statistics.unique_assets,
                    validation_status=report.status,
                    validation_errors=tuple(sorted(report.errors)),
                    validation_warnings=tuple(sorted(report.warnings)),
                )
            )

        # The global view is deliberately built only after every isolated view.
        consolidated_portfolio = self._consolidation_engine.consolidate(originals)
        consolidation_report = consolidated_portfolio.report
        consolidation_statistics = consolidation_report.statistics
        warnings = tuple(sorted(consolidation_report.alerts))
        duplicate_count = len(consolidation_report.duplicates)
        consolidated = ConsolidatedPortfolioSnapshot(
            position_count=consolidation_statistics.original_positions,
            unique_assets=consolidation_statistics.unique_assets,
            gross_value_by_currency=self._frozen_map(
                consolidation_statistics.consolidated_value_by_currency
            ),
            positions_by_owner=self._frozen_map(
                consolidation_statistics.positions_by_owner
            ),
            positions_by_institution=self._frozen_map(
                consolidation_statistics.positions_by_institution
            ),
            positions_by_class=self._frozen_map(
                consolidation_statistics.positions_by_class
            ),
            positions_by_category=self._frozen_map(
                consolidation_statistics.positions_by_category
            ),
            duplicate_count=duplicate_count,
            warnings=warnings,
        )
        error_count = sum(report.statistics.error_count for report in reports_used)
        warning_count = sum(report.statistics.alert_count for report in reports_used)
        status = self._status(originals, reports_used, warnings)
        return DailyPortfolioSnapshot(
            reference_date=reference_date,
            generated_at=datetime.now(timezone.utc),
            owners=tuple(sorted({item.owner for item in originals}, key=lambda item: item.value)),
            institutions=tuple(sorted({item.institution for item in originals}, key=self._text_key)),
            currencies=tuple(
                sorted(
                    {item.currency for item in originals if item.currency},
                    key=self._text_key,
                )
            ),
            institution_snapshots=tuple(institution_snapshots),
            consolidated=consolidated,
            status=status,
            summary=DailyPortfolioSummary(
                institution_count=len({(item.owner, item.institution) for item in originals}),
                owner_count=len({item.owner for item in originals}),
                original_position_count=consolidation_statistics.original_positions,
                consolidated_asset_count=consolidation_statistics.unique_assets,
                validation_error_count=error_count,
                validation_warning_count=warning_count,
                duplicate_count=duplicate_count,
            ),
        )

    @staticmethod
    def _ensure_positions(positions: Tuple[PortfolioPosition, ...]) -> None:
        if any(not isinstance(item, PortfolioPosition) for item in positions):
            raise TypeError("snapshot accepts only PortfolioPosition instances")

    @staticmethod
    def _group_positions(
        positions: Tuple[PortfolioPosition, ...],
    ) -> dict[ValidationReportKey, list[PortfolioPosition]]:
        groups: dict[ValidationReportKey, list[PortfolioPosition]] = defaultdict(list)
        for position in positions:
            groups[(position.owner, position.institution, position.currency)].append(position)
        return groups

    def _report_for(
        self,
        key: ValidationReportKey,
        positions: Tuple[PortfolioPosition, ...],
        reports: Mapping[ValidationReportKey, ImportValidationReport],
    ) -> ImportValidationReport:
        report = reports.get(key)
        if report is None:
            report = reports.get((key[0], key[1], None))
        if report is None:
            return self._validation_engine.validate(positions)
        if not isinstance(report, ImportValidationReport):
            raise TypeError("validation reports must be ImportValidationReport instances")
        return report

    @staticmethod
    def _status(
        positions: Tuple[PortfolioPosition, ...],
        reports: Iterable[ImportValidationReport],
        consolidation_warnings: Tuple[str, ...],
    ) -> DailyPortfolioStatus:
        if not positions:
            return DailyPortfolioStatus.EMPTY
        if any(report.status is ImportValidationStatus.REJECTED for report in reports):
            return DailyPortfolioStatus.BLOCKED
        if consolidation_warnings or any(
            report.status is ImportValidationStatus.APPROVED_WITH_WARNINGS
            for report in reports
        ):
            return DailyPortfolioStatus.READY_WITH_WARNINGS
        return DailyPortfolioStatus.READY

    @classmethod
    def _group_sort_key(
        cls, key: ValidationReportKey
    ) -> tuple[str, tuple[str, str], tuple[str, str]]:
        owner, institution, currency = key
        return owner.value, cls._text_key(institution), cls._text_key(currency or "")

    @staticmethod
    def _text_key(value: object) -> tuple[str, str]:
        return str(value).casefold(), str(value)

    @classmethod
    def _frozen_map(
        cls, values: Mapping[str, MapValue]
    ) -> Mapping[str, MapValue]:
        return MappingProxyType(dict(sorted(values.items(), key=lambda item: cls._text_key(item[0]))))
