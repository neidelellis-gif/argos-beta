"""Deterministic presentation contract for a completed ARGOS daily flow."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.daily_brief import DailyPriorityLevel
from backend.daily_orchestrator import (
    DailyOrchestrationResult,
    DailyOrchestrationStage,
    DailyOrchestrationStatus,
    DailyStageStatus,
)
from backend.daily_priority import (
    AffectedDimension,
    DailyPriorityAction,
)


class DailyGreetingPeriod(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"


class DailyExperienceStatus(str, Enum):
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    DECISION_REQUIRED = "DECISION_REQUIRED"


class DailyBlockType(str, Enum):
    IMPORTANT_FACTS = "IMPORTANT_FACTS"
    DAILY_PRIORITIES = "DAILY_PRIORITIES"
    DAILY_ANALYSES = "DAILY_ANALYSES"


class DailyBlockVisibility(str, Enum):
    VISIBLE = "VISIBLE"
    HIDDEN = "HIDDEN"


_LEVEL_LABELS = {
    DailyPriorityLevel.HIGH: "Alta",
    DailyPriorityLevel.MODERATE: "Moderada",
    DailyPriorityLevel.LOW: "Baixa",
}
_ACTION_LABELS = {
    DailyPriorityAction.ANALYZE: "Analisar",
    DailyPriorityAction.DECIDE: "Decidir",
}
_MESSAGES = {
    DailyExperienceStatus.NO_ACTION_REQUIRED: "Nada exige sua atenção na carteira hoje.",
    DailyExperienceStatus.ATTENTION_REQUIRED: "Há pontos da carteira que merecem sua análise hoje.",
    DailyExperienceStatus.DECISION_REQUIRED: "Há uma decisão que merece sua atenção hoje.",
}
_BLOCK_TITLES = {
    DailyBlockType.IMPORTANT_FACTS: "Fatos importantes",
    DailyBlockType.DAILY_PRIORITIES: "Prioridades do dia",
    DailyBlockType.DAILY_ANALYSES: "Análises",
}
_WEEKDAYS = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)
_MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


@dataclass(frozen=True)
class DailyExperienceHeader:
    user_name: str
    greeting_period: DailyGreetingPeriod
    greeting_text: str
    reference_date: date
    formatted_date: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_name, str) or not self.user_name.strip():
            raise ValueError("user_name must not be empty")
        if not isinstance(self.greeting_period, DailyGreetingPeriod):
            raise TypeError("greeting_period must be a DailyGreetingPeriod")
        expected = {
            DailyGreetingPeriod.MORNING: "Bom dia",
            DailyGreetingPeriod.AFTERNOON: "Boa tarde",
            DailyGreetingPeriod.EVENING: "Boa noite",
        }[self.greeting_period]
        if self.greeting_text != f"{expected}, {self.user_name}":
            raise ValueError("greeting_text is inconsistent")
        if not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date")
        if self.formatted_date != _format_date(self.reference_date):
            raise ValueError("formatted_date is inconsistent")


@dataclass(frozen=True)
class DailyExperienceMessage:
    status: DailyExperienceStatus
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, DailyExperienceStatus):
            raise TypeError("status must be a DailyExperienceStatus")
        if self.text != _MESSAGES[self.status]:
            raise ValueError("message text is inconsistent")


@dataclass(frozen=True)
class DailyFactItem:
    fact_id: str
    title: str
    category: str
    priority: str
    source: str | None

    def __post_init__(self) -> None:
        for name, value in (
            ("fact_id", self.fact_id), ("title", self.title),
            ("category", self.category), ("priority", self.priority),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.source is not None and not isinstance(self.source, str):
            raise TypeError("source must be a string or None")


@dataclass(frozen=True)
class DailyPriorityItem:
    priority_id: str
    fact_id: str
    level: DailyPriorityLevel
    label: str
    title: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.level, DailyPriorityLevel):
            raise TypeError("level must be a DailyPriorityLevel")
        if self.label != _LEVEL_LABELS[self.level]:
            raise ValueError("priority label is inconsistent")
        _validate_priority_text(self.priority_id, self.fact_id, self.title, self.reason)


@dataclass(frozen=True)
class DailyAnalysisItem:
    priority_id: str
    fact_id: str
    action: DailyPriorityAction
    action_label: str
    level: DailyPriorityLevel
    title: str
    reason: str
    affected_dimensions: tuple[AffectedDimension, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action, DailyPriorityAction):
            raise TypeError("action must be a DailyPriorityAction")
        if self.action_label != _ACTION_LABELS[self.action]:
            raise ValueError("action_label is inconsistent")
        if not isinstance(self.level, DailyPriorityLevel):
            raise TypeError("level must be a DailyPriorityLevel")
        _validate_priority_text(self.priority_id, self.fact_id, self.title, self.reason)
        if not isinstance(self.affected_dimensions, tuple):
            raise TypeError("affected_dimensions must be a tuple")
        if any(not isinstance(item, AffectedDimension) for item in self.affected_dimensions):
            raise TypeError("affected_dimensions accepts only AffectedDimension instances")


@dataclass(frozen=True)
class DailyExperienceBlock:
    block_type: DailyBlockType
    title: str
    visibility: DailyBlockVisibility
    item_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.block_type, DailyBlockType):
            raise TypeError("block_type must be a DailyBlockType")
        if self.title != _BLOCK_TITLES[self.block_type]:
            raise ValueError("block title is inconsistent")
        if not isinstance(self.visibility, DailyBlockVisibility):
            raise TypeError("visibility must be a DailyBlockVisibility")
        if not isinstance(self.item_count, int) or self.item_count < 0:
            raise ValueError("item_count must be a non-negative integer")
        expected = DailyBlockVisibility.VISIBLE if self.item_count else DailyBlockVisibility.HIDDEN
        if self.visibility is not expected:
            raise ValueError("block visibility is inconsistent")


@dataclass(frozen=True)
class DailyExperienceSummary:
    fact_count: int
    priority_count: int
    analysis_count: int
    visible_block_count: int
    hidden_block_count: int
    automatic_analysis_open: bool
    has_decision: bool
    has_attention: bool

    def __post_init__(self) -> None:
        counts = (
            self.fact_count, self.priority_count, self.analysis_count,
            self.visible_block_count, self.hidden_block_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("summary counts must be non-negative integers")
        if self.fact_count > 5 or self.priority_count > 3 or self.analysis_count > 2:
            raise ValueError("summary exceeds presentation limits")
        if self.visible_block_count + self.hidden_block_count != 3:
            raise ValueError("block counts must equal the official block count")
        for value in (self.automatic_analysis_open, self.has_decision, self.has_attention):
            if not isinstance(value, bool):
                raise TypeError("summary flags must be booleans")
        if self.has_attention != (self.priority_count > 0):
            raise ValueError("has_attention is inconsistent")
        if self.automatic_analysis_open != self.has_attention:
            raise ValueError("automatic_analysis_open is inconsistent")
        if self.has_decision and not self.has_attention:
            raise ValueError("has_decision requires attention")


@dataclass(frozen=True)
class DailyExperienceResult:
    reference_date: date
    generated_at: datetime
    header: DailyExperienceHeader
    status: DailyExperienceStatus
    message: DailyExperienceMessage
    facts: tuple[DailyFactItem, ...]
    priorities: tuple[DailyPriorityItem, ...]
    analyses: tuple[DailyAnalysisItem, ...]
    blocks: tuple[DailyExperienceBlock, ...]
    summary: DailyExperienceSummary

    def __post_init__(self) -> None:
        if not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must include timezone information")
        if self.generated_at.utcoffset() != timezone.utc.utcoffset(self.generated_at):
            raise ValueError("generated_at must be normalized to UTC")
        if self.header.reference_date != self.reference_date:
            raise ValueError("header reference_date is inconsistent")
        if self.message.status is not self.status:
            raise ValueError("message status is inconsistent")
        collections = (self.facts, self.priorities, self.analyses, self.blocks)
        if any(not isinstance(items, tuple) for items in collections):
            raise TypeError("experience collections must be tuples")
        expected_blocks = tuple(DailyBlockType)
        if tuple(block.block_type for block in self.blocks) != expected_blocks:
            raise ValueError("blocks must follow the official order")
        counts = (len(self.facts), len(self.priorities), len(self.analyses))
        if counts != (self.summary.fact_count, self.summary.priority_count, self.summary.analysis_count):
            raise ValueError("summary item counts are inconsistent")
        if tuple(block.item_count for block in self.blocks) != counts:
            raise ValueError("block item counts are inconsistent")
        visible = sum(block.visibility is DailyBlockVisibility.VISIBLE for block in self.blocks)
        if (visible, len(self.blocks) - visible) != (
            self.summary.visible_block_count, self.summary.hidden_block_count,
        ):
            raise ValueError("summary block counts are inconsistent")
        expected_status = _experience_status(self.summary.has_decision, bool(self.priorities))
        if self.status is not expected_status:
            raise ValueError("experience status is inconsistent")


class DailyExperienceError(Exception):
    """Safe typed error raised when an experience cannot be composed."""

    def __init__(self, error_type: str, message: str, cause: Exception | None = None) -> None:
        self.error_type = error_type
        self.cause = cause
        super().__init__(message)


class DailyExperienceComposer:
    """Compose presentation data without reproducing engine decisions."""

    def __init__(
        self,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        user_name: str = "Nei",
        presentation_timezone: str = "America/Sao_Paulo",
    ) -> None:
        if not isinstance(user_name, str) or not user_name.strip():
            raise DailyExperienceError("INVALID_USER_NAME", "User name must not be empty.")
        if not isinstance(presentation_timezone, str) or not presentation_timezone.strip():
            raise DailyExperienceError("INVALID_TIMEZONE", "Presentation timezone is invalid.")
        try:
            self._timezone = ZoneInfo(presentation_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise DailyExperienceError(
                "INVALID_TIMEZONE", "Presentation timezone is invalid.", error
            ) from error
        self._clock = clock
        self._user_name = user_name

    def compose(self, result: DailyOrchestrationResult) -> DailyExperienceResult:
        self._validate_input(result)
        try:
            now = self._clock()
        except Exception as error:
            raise DailyExperienceError("CLOCK_ERROR", "Presentation clock failed.", error) from error
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise DailyExperienceError("INVALID_CLOCK", "Presentation clock must be timezone-aware.")

        # Narrowed by _validate_input; local names keep composition readable.
        reference_date = result.reference_date
        facts_result = result.important_facts
        priorities_result = result.daily_priorities
        if reference_date is None or facts_result is None or priorities_result is None:
            raise DailyExperienceError("INCOMPLETE_RESULT", "Daily orchestration result is incomplete.")

        local_now = now.astimezone(self._timezone)
        generated_at = now.astimezone(timezone.utc)
        period = _greeting_period(local_now)
        greeting = {
            DailyGreetingPeriod.MORNING: "Bom dia",
            DailyGreetingPeriod.AFTERNOON: "Boa tarde",
            DailyGreetingPeriod.EVENING: "Boa noite",
        }[period]
        header = DailyExperienceHeader(
            self._user_name, period, f"{greeting}, {self._user_name}",
            reference_date, _format_date(reference_date),
        )
        facts = tuple(
            DailyFactItem(fact.id, fact.title, fact.category, fact.priority, fact.source)
            for fact in facts_result.important_facts[:5]
        )
        selected = priorities_result.priorities[:3]
        priorities = tuple(
            DailyPriorityItem(
                item.priority_id, item.fact_id, item.level, _LEVEL_LABELS[item.level],
                item.title, item.reason,
            )
            for item in selected
        )
        analyses = tuple(
            DailyAnalysisItem(
                item.priority_id, item.fact_id, item.action, _ACTION_LABELS[item.action],
                item.level, item.title, item.reason, item.affected_dimensions,
            )
            for item in selected[:2]
        )
        has_decision = any(item.action is DailyPriorityAction.DECIDE for item in selected)
        status = _experience_status(has_decision, bool(priorities))
        message = DailyExperienceMessage(status, _MESSAGES[status])
        counts = (len(facts), len(priorities), len(analyses))
        blocks = tuple(
            DailyExperienceBlock(
                block_type,
                _BLOCK_TITLES[block_type],
                DailyBlockVisibility.VISIBLE if count else DailyBlockVisibility.HIDDEN,
                count,
            )
            for block_type, count in zip(tuple(DailyBlockType), counts, strict=True)
        )
        visible = sum(block.visibility is DailyBlockVisibility.VISIBLE for block in blocks)
        summary = DailyExperienceSummary(
            counts[0], counts[1], counts[2], visible, 3 - visible,
            bool(priorities), has_decision, bool(priorities),
        )
        return DailyExperienceResult(
            reference_date, generated_at, header, status, message,
            facts, priorities, analyses, blocks, summary,
        )

    @staticmethod
    def _validate_input(result: DailyOrchestrationResult) -> None:
        if not isinstance(result, DailyOrchestrationResult):
            raise DailyExperienceError("INVALID_RESULT_TYPE", "Expected DailyOrchestrationResult.")
        if result.status is not DailyOrchestrationStatus.COMPLETED:
            raise DailyExperienceError("ORCHESTRATION_NOT_COMPLETED", "Daily orchestration is not completed.")
        if result.reference_date is None:
            raise DailyExperienceError("MISSING_REFERENCE_DATE", "Daily reference date is required.")
        internal = (
            result.snapshot, result.important_facts,
            result.portfolio_impacts, result.daily_priorities, result.summary,
        )
        if any(item is None for item in internal):
            raise DailyExperienceError("INCOMPLETE_RESULT", "Daily orchestration result is incomplete.")
        if tuple(item.stage for item in result.stages) != tuple(DailyOrchestrationStage):
            raise DailyExperienceError("INCOMPLETE_STAGES", "Daily orchestration stages are incomplete.")
        if any(item.status is not DailyStageStatus.COMPLETED for item in result.stages):
            raise DailyExperienceError("INCOMPLETE_STAGES", "Daily orchestration stages are incomplete.")
        snapshot = result.snapshot
        impacts = result.portfolio_impacts
        priorities = result.daily_priorities
        if snapshot is None or impacts is None or priorities is None:
            raise DailyExperienceError("INCOMPLETE_RESULT", "Daily orchestration result is incomplete.")
        if not (
            snapshot.reference_date == result.reference_date
            and impacts.reference_date == result.reference_date
            and priorities.reference_date == result.reference_date
        ):
            raise DailyExperienceError("INCONSISTENT_REFERENCE_DATE", "Daily reference dates are inconsistent.")


def _format_date(value: date) -> str:
    return f"{_WEEKDAYS[value.weekday()]}, {value.day} de {_MONTHS[value.month - 1]} de {value.year}"


def _greeting_period(value: datetime) -> DailyGreetingPeriod:
    if 5 <= value.hour < 12:
        return DailyGreetingPeriod.MORNING
    if 12 <= value.hour < 18:
        return DailyGreetingPeriod.AFTERNOON
    return DailyGreetingPeriod.EVENING


def _experience_status(
    has_decision: bool, has_priorities: bool
) -> DailyExperienceStatus:
    if has_decision:
        return DailyExperienceStatus.DECISION_REQUIRED
    if has_priorities:
        return DailyExperienceStatus.ATTENTION_REQUIRED
    return DailyExperienceStatus.NO_ACTION_REQUIRED


def _validate_priority_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("priority text fields must not be empty")
