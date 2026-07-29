"""Validation of normalized portfolio imports.

The engine operates exclusively on the universal ``PortfolioPosition`` model.
It therefore remains independent from file formats and connector details.
"""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Tuple

from backend.models import PortfolioOwner, PortfolioPosition


class ImportValidationStatus(str, Enum):
    """Possible outcomes of an import validation."""

    APPROVED = "APPROVED"
    APPROVED_WITH_WARNINGS = "APPROVED_WITH_WARNINGS"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ImportValidationStatistics:
    """Summary figures calculated without changing imported positions."""

    total_positions: int
    gross_value: Decimal
    positions_by_class: Mapping[str, int]
    positions_by_category: Mapping[str, int]
    alert_count: int
    error_count: int


@dataclass(frozen=True)
class ImportValidationReport:
    """Standard result returned for every normalized portfolio import."""

    status: ImportValidationStatus
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    statistics: ImportValidationStatistics


class ImportValidationEngine:
    """Apply bank-agnostic quality checks to connector output."""

    RECOGNIZED_INSTITUTIONS = frozenset({"UBS", "Santander", "Bradesco"})

    def validate(
        self, positions: Iterable[PortfolioPosition]
    ) -> ImportValidationReport:
        imported = tuple(positions)
        errors = []
        warnings = []
        classes: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        gross_value = Decimal("0")
        duplicate_keys: Counter[tuple[str, str, str]] = Counter()

        if not imported:
            errors.append("Import contains no portfolio positions")

        for index, position in enumerate(imported, start=1):
            prefix = f"Position {index}"
            if not isinstance(position, PortfolioPosition):
                errors.append(f"{prefix} is not a PortfolioPosition")
                continue

            if position.institution not in self.RECOGNIZED_INSTITUTIONS:
                errors.append(f"{prefix} has an unrecognized institution")
            if not isinstance(position.owner, PortfolioOwner):
                errors.append(f"{prefix} has an unrecognized owner")
            if not self._filled(position.currency):
                errors.append(f"{prefix} has no currency")
            if not self._filled(position.asset_name):
                errors.append(f"{prefix} has no asset name")
            if not self._filled(position.asset_class):
                warnings.append(f"{prefix} has no asset class")
            else:
                classes[str(position.asset_class).strip()] += 1
            if not self._filled(position.asset_subclass):
                warnings.append(f"{prefix} has no asset category")
            else:
                categories[str(position.asset_subclass).strip()] += 1

            if self._empty(position):
                errors.append(f"{prefix} is empty")

            market_value = position.market_value
            if not self._valid_market_value(market_value):
                errors.append(f"{prefix} has an invalid market value")
            else:
                assert market_value is not None
                gross_value += market_value

            duplicate_key = self._duplicate_key(position)
            if duplicate_key is not None:
                duplicate_keys[duplicate_key] += 1

        duplicate_count = sum(count - 1 for count in duplicate_keys.values() if count > 1)
        if duplicate_count:
            warnings.append(f"Import contains {duplicate_count} duplicate position(s)")

        status = ImportValidationStatus.APPROVED
        if errors:
            status = ImportValidationStatus.REJECTED
        elif warnings:
            status = ImportValidationStatus.APPROVED_WITH_WARNINGS

        statistics = ImportValidationStatistics(
            total_positions=len(imported),
            gross_value=gross_value,
            positions_by_class=MappingProxyType(dict(sorted(classes.items()))),
            positions_by_category=MappingProxyType(dict(sorted(categories.items()))),
            alert_count=len(warnings),
            error_count=len(errors),
        )
        return ImportValidationReport(
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
            statistics=statistics,
        )

    @staticmethod
    def _filled(value: object) -> bool:
        return value is not None and bool(str(value).strip())

    @classmethod
    def _empty(cls, position: PortfolioPosition) -> bool:
        return not any(
            cls._filled(value)
            for value in (
                position.asset_name,
                position.identifier,
                position.asset_class,
                position.asset_subclass,
            )
        ) and position.quantity is None and position.market_value is None

    @staticmethod
    def _valid_market_value(value: object) -> bool:
        if not isinstance(value, Decimal) or not value.is_finite():
            return False
        return value >= 0

    @classmethod
    def _duplicate_key(
        cls, position: PortfolioPosition
    ) -> tuple[str, str, str] | None:
        identity = position.identifier if cls._filled(position.identifier) else position.asset_name
        if not cls._filled(identity):
            return None
        return (
            str(position.institution).strip().casefold(),
            str(position.account or "").strip().casefold(),
            str(identity).strip().casefold(),
        )
