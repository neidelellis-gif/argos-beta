"""Presentation-only orchestration for the ARGOS daily experience."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


SUPPORTED_CONTRACT_VERSIONS = frozenset({"1.0", "1.1", "1.2", "1.3", "1.4", "1.5"})
BLOCK_ORDER = (
    "facts", "priorities", "analyses", "decision_contexts",
    "impact_assessments", "market_agenda", "data_quality",
)


class ExperienceAssemblyStatus(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DailyExperienceAssembly:
    status: ExperienceAssemblyStatus
    collections: Mapping[str, tuple[object, ...]]
    visibility: Mapping[str, bool]
    diagnostic: Mapping[str, object]


class DailyExperienceOrchestrator:
    """Validate and coordinate presentation without changing engine results."""

    def orchestrate(
        self,
        *,
        contract_version: str,
        data_quality: object | None,
        facts: Sequence[object] | None,
        priorities: Sequence[object] | None,
        analyses: Sequence[object] | None,
        decision_contexts: Sequence[object] | None,
        impact_assessments: Sequence[object] | None,
        market_agenda: Sequence[object] | None,
    ) -> DailyExperienceAssembly:
        supplied = {
            "facts": facts, "priorities": priorities, "analyses": analyses,
            "decision_contexts": decision_contexts,
            "impact_assessments": impact_assessments, "market_agenda": market_agenda,
        }
        incompatible = contract_version not in SUPPORTED_CONTRACT_VERSIONS
        invalid = tuple(name for name, value in supplied.items() if value is not None and not isinstance(value, (list, tuple)))
        missing_required = tuple(name for name in ("facts", "priorities", "analyses") if supplied[name] is None)
        missing_optional = tuple(name for name in ("decision_contexts", "impact_assessments", "market_agenda") if supplied[name] is None)
        quality_invalid = data_quality is not None and not isinstance(data_quality, Mapping)
        impossible = incompatible or bool(invalid) or bool(missing_required) or quality_invalid

        collections = {name: tuple(value or ()) for name, value in supplied.items()}
        quality_status = data_quality.get("status") if isinstance(data_quality, Mapping) else None
        quality_diagnostics = data_quality.get("diagnostics", ()) if isinstance(data_quality, Mapping) else ()
        if not isinstance(quality_diagnostics, (list, tuple)):
            quality_diagnostics = ()
            impossible = True
        collections["data_quality"] = tuple(quality_diagnostics)
        visibility = {name: bool(collections[name]) for name in BLOCK_ORDER}
        visibility["data_quality"] = quality_status in {"WARNING", "ERROR"} and bool(collections["data_quality"])

        status = (ExperienceAssemblyStatus.ERROR if impossible else
                  ExperienceAssemblyStatus.PARTIAL if missing_optional or data_quality is None else
                  ExperienceAssemblyStatus.READY)
        collections_preserved = True
        for name, original in supplied.items():
            if original is not None and len(collections[name]) != len(original):
                collections_preserved = False
        diagnostic = MappingProxyType({
            "evaluated_blocks": BLOCK_ORDER,
            "missing_components": missing_required + missing_optional + (() if data_quality is not None else ("data_quality",)),
            "invalid_components": invalid + (("data_quality",) if quality_invalid else ()),
            "compatible_version": not incompatible,
            "all_blocks_evaluated": tuple(visibility) == BLOCK_ORDER,
            "collections_preserved": collections_preserved,
        })
        return DailyExperienceAssembly(
            status, MappingProxyType(collections), MappingProxyType(visibility), diagnostic
        )
