from types import MappingProxyType
from typing import Any, cast

import pytest

from backend.daily_experience_orchestrator import (
    BLOCK_ORDER,
    DailyExperienceOrchestrator,
    ExperienceAssemblyStatus,
)


def assemble(**changes: object):
    values: dict[str, object] = {
        "contract_version": "1.5",
        "data_quality": {"status": "HEALTHY", "diagnostics": []},
        "facts": ("fact",), "priorities": ("priority",), "analyses": ("analysis",),
        "decision_contexts": ("context",), "impact_assessments": ("impact",),
        "market_agenda": ("event",),
    }
    values.update(changes)
    return DailyExperienceOrchestrator().orchestrate(**cast(Any, values))


def test_preserves_official_order_collections_and_input_immutability() -> None:
    marker = object()
    facts = [marker]
    result = assemble(facts=facts)
    assert tuple(result.collections) == BLOCK_ORDER
    assert result.collections["facts"] == (marker,)
    assert result.status is ExperienceAssemblyStatus.READY
    assert result.diagnostic["all_blocks_evaluated"] is True
    assert result.diagnostic["collections_preserved"] is True
    assert facts == [marker]
    assert isinstance(result.collections, MappingProxyType)
    with pytest.raises(TypeError):
        result.visibility["facts"] = False  # type: ignore[index]


def test_hides_empty_blocks_and_only_shows_actionable_quality() -> None:
    result = assemble(
        facts=(), priorities=(), analyses=(), decision_contexts=(),
        impact_assessments=(), market_agenda=(),
        data_quality={"status": "WARNING", "diagnostics": ({"id": "warning"},)},
    )
    assert tuple(name for name, visible in result.visibility.items() if visible) == ("data_quality",)


def test_partial_for_absent_optional_component_and_error_for_impossible_contract() -> None:
    partial = assemble(market_agenda=None)
    assert partial.status is ExperienceAssemblyStatus.PARTIAL
    assert partial.diagnostic["missing_components"] == ("market_agenda",)
    error = assemble(contract_version="2.0")
    assert error.status is ExperienceAssemblyStatus.ERROR
    assert error.diagnostic["compatible_version"] is False


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"])
def test_accepts_every_supported_contract(version: str) -> None:
    assert assemble(contract_version=version).status is ExperienceAssemblyStatus.READY
