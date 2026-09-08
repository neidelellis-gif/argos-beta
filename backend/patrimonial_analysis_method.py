"""Shared five-stage patrimonial analysis contract for ARGOS.

The method is intentionally presentation-neutral.  Institution services and the
JOLIKA consolidated service can publish the same sequence while keeping their
analyzed universes separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PatrimonialAnalysisItem:
    """One evidence-based statement inside an analysis stage."""

    title: str
    reading: str
    evidence: tuple[str, ...] = ()
    confidence: str = "Média"

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "reading": self.reading,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PatrimonialAnalysisStage:
    """One fixed stage of the ARGOS patrimonial analysis method."""

    key: str
    title: str
    summary: str
    items: tuple[PatrimonialAnalysisItem, ...] = ()
    status: str = "available"

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class PatrimonialAnalysisReport:
    """The single five-stage ARGOS method applied to one analysis universe."""

    universe: str
    scope: str
    stages: tuple[PatrimonialAnalysisStage, ...]

    def __post_init__(self) -> None:
        keys = tuple(stage.key for stage in self.stages)
        if keys != PATRIMONIAL_ANALYSIS_STAGE_KEYS:
            raise ValueError("patrimonial analysis must contain the five official stages in order")

    def to_dict(self) -> dict[str, object]:
        return {
            "method": "ARGOS_PATRIMONIAL_5_STAGE_V1",
            "universe": self.universe,
            "scope": self.scope,
            "stages": [stage.to_dict() for stage in self.stages],
        }


PATRIMONIAL_ANALYSIS_STAGE_KEYS = (
    "diagnosis",
    "composition",
    "master_assumptions",
    "market_context",
    "final_diagnosis",
)

PATRIMONIAL_ANALYSIS_STAGE_TITLES = (
    "Diagnóstico da carteira",
    "Análise da composição",
    "Aderência às Premissas Mestres da JOLIKA",
    "Carteira × ambiente de mercado",
    "Diagnóstico final",
)


def build_patrimonial_analysis_report(
    *,
    universe: str,
    scope: str,
    diagnosis: PatrimonialAnalysisStage,
    composition: PatrimonialAnalysisStage,
    master_assumptions: PatrimonialAnalysisStage,
    market_context: PatrimonialAnalysisStage,
    final_diagnosis: PatrimonialAnalysisStage,
) -> PatrimonialAnalysisReport:
    """Build the official method without allowing stage reordering."""

    stages = (
        diagnosis,
        composition,
        master_assumptions,
        market_context,
        final_diagnosis,
    )
    return PatrimonialAnalysisReport(
        universe=universe,
        scope=scope,
        stages=stages,
    )


def unavailable_stage(key: str, title: str, reason: str) -> PatrimonialAnalysisStage:
    """Represent a data limitation explicitly instead of inventing a conclusion."""

    return PatrimonialAnalysisStage(
        key=key,
        title=title,
        summary=reason,
        status="limited",
        items=(
            PatrimonialAnalysisItem(
                title="Limitação dos dados",
                reading=reason,
                confidence="Alta",
            ),
        ),
    )


def evidence_tuple(values: Iterable[str]) -> tuple[str, ...]:
    """Normalize evidence labels while preserving deterministic order."""

    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))
