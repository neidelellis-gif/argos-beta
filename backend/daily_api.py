"""Stable public facade for the official ARGOS daily experience."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from backend.daily_experience import (
    DailyBlockType,
    DailyBlockVisibility,
    DailyExperienceComposer,
    DailyExperienceError,
    DailyExperienceResult,
)
from backend.daily_orchestrator import (
    DailyOrchestrationError,
    DailyOrchestrator,
)
from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshotBuilder,
    ValidationReportKey,
)
from backend.daily_priority import DailyPriorityEngine
from backend.import_validation import ImportValidationReport
from backend.important_facts import FactCandidate, ImportantFactsEngine
from backend.models import PortfolioPosition
from backend.portfolio_impact import PortfolioImpactEngine


class DailyApiStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class DailyApiErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    ORCHESTRATION_ERROR = "ORCHESTRATION_ERROR"
    EXPERIENCE_ERROR = "EXPERIENCE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class DailyApiRequest:
    positions: tuple[PortfolioPosition, ...]
    fact_candidates: tuple[FactCandidate, ...]
    reference_date: date | None = None
    validation_reports: Mapping[
        ValidationReportKey, ImportValidationReport
    ] | None = None


@dataclass(frozen=True)
class DailyApiHeader:
    greeting: str
    display_date: str
    period: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.greeting, self.display_date
        )):
            raise ValueError("header text must not be empty")
        if self.period not in {"MORNING", "AFTERNOON", "EVENING"}:
            raise ValueError("period must be an official greeting period")


@dataclass(frozen=True)
class DailyApiMessage:
    title: str
    text: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.title, self.text
        )):
            raise ValueError("message text must not be empty")


@dataclass(frozen=True)
class DailyApiFact:
    id: str
    category: str
    text: str
    importance: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.id, self.category, self.text, self.importance
        )):
            raise ValueError("fact fields must not be empty")


@dataclass(frozen=True)
class DailyApiPriority:
    fact_id: str
    level: str
    label: str
    title: str
    reason: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.fact_id, self.level, self.title, self.reason
        )):
            raise ValueError("priority fields must not be empty")
        if self.label not in {"Alta", "Moderada", "Baixa"}:
            raise ValueError("label must be an official priority label")


@dataclass(frozen=True)
class DailyApiAnalysis:
    fact_id: str
    action: str
    title: str
    reason: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.fact_id, self.title, self.reason
        )):
            raise ValueError("analysis fields must not be empty")
        if self.action not in {"Analisar", "Decidir"}:
            raise ValueError("action must be an official analysis action")


DailyApiBlockItem = DailyApiFact | DailyApiPriority | DailyApiAnalysis


@dataclass(frozen=True)
class DailyApiBlock:
    type: str
    visible: bool
    title: str
    items: tuple[DailyApiBlockItem, ...]

    def __post_init__(self) -> None:
        allowed = {"FACTS", "PRIORITIES", "ANALYSES"}
        if self.type not in allowed:
            raise ValueError("type must be an official daily API block type")
        if not isinstance(self.visible, bool):
            raise TypeError("visible must be a boolean")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        expected_type = {
            "FACTS": DailyApiFact,
            "PRIORITIES": DailyApiPriority,
            "ANALYSES": DailyApiAnalysis,
        }[self.type]
        if any(not isinstance(item, expected_type) for item in self.items):
            raise TypeError("block items must match the block type")
        expected_title = {
            "FACTS": "Fatos importantes",
            "PRIORITIES": "Prioridades do dia",
            "ANALYSES": "Análises",
        }[self.type]
        if self.title != expected_title:
            raise ValueError("title must match the official block title")


@dataclass(frozen=True)
class DailyApiSummary:
    fact_count: int
    priority_count: int
    analysis_count: int
    visible_block_count: int
    requires_attention: bool
    requires_decision: bool

    def __post_init__(self) -> None:
        counts = (
            self.fact_count,
            self.priority_count,
            self.analysis_count,
            self.visible_block_count,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in counts):
            raise TypeError("summary counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("summary counts must not be negative")
        if not isinstance(self.requires_attention, bool):
            raise TypeError("requires_attention must be a boolean")
        if not isinstance(self.requires_decision, bool):
            raise TypeError("requires_decision must be a boolean")


@dataclass(frozen=True)
class DailyApiError:
    code: DailyApiErrorCode
    message: str
    stage: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, DailyApiErrorCode):
            raise TypeError("code must be a DailyApiErrorCode")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("error message must not be empty")
        if self.stage is not None and (
            not isinstance(self.stage, str) or not self.stage.strip()
        ):
            raise ValueError("error stage must be a non-empty string or None")


@dataclass(frozen=True)
class DailyApiResponse:
    status: DailyApiStatus
    generated_at: datetime
    experience_status: str | None
    header: DailyApiHeader | None
    message: DailyApiMessage | None
    facts: tuple[DailyApiFact, ...]
    priorities: tuple[DailyApiPriority, ...]
    analyses: tuple[DailyApiAnalysis, ...]
    blocks: tuple[DailyApiBlock, ...]
    summary: DailyApiSummary | None
    error: DailyApiError | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, DailyApiStatus):
            raise TypeError("status must be a DailyApiStatus")
        normalized = _aware_utc(self.generated_at)
        object.__setattr__(self, "generated_at", normalized)
        collections = (self.facts, self.priorities, self.analyses, self.blocks)
        if any(not isinstance(items, tuple) for items in collections):
            raise TypeError("response collections must be tuples")
        if self.status is DailyApiStatus.SUCCESS:
            self._validate_success()
        else:
            self._validate_error()

    def _validate_success(self) -> None:
        if (
            self.experience_status is None
            or self.header is None
            or self.message is None
            or self.summary is None
            or self.error is not None
        ):
            raise ValueError("SUCCESS response must contain one complete experience")
        if self.experience_status not in {
            "NO_ACTION_REQUIRED", "ATTENTION_REQUIRED", "DECISION_REQUIRED"
        }:
            raise ValueError("experience_status must be an official status")
        if any(not isinstance(item, DailyApiFact) for item in self.facts):
            raise TypeError("facts accepts only DailyApiFact instances")
        if any(not isinstance(item, DailyApiPriority) for item in self.priorities):
            raise TypeError("priorities accepts only DailyApiPriority instances")
        if any(not isinstance(item, DailyApiAnalysis) for item in self.analyses):
            raise TypeError("analyses accepts only DailyApiAnalysis instances")
        if any(not isinstance(item, DailyApiBlock) for item in self.blocks):
            raise TypeError("blocks accepts only DailyApiBlock instances")
        if tuple(block.type for block in self.blocks) != (
            "FACTS", "PRIORITIES", "ANALYSES"
        ):
            raise ValueError("SUCCESS response must contain the official blocks")
        expected_items: tuple[tuple[DailyApiBlockItem, ...], ...] = (
            self.facts,
            self.priorities,
            self.analyses,
        )
        if tuple(block.items for block in self.blocks) != expected_items:
            raise ValueError("block items must match response collections")
        expected_counts = (len(self.facts), len(self.priorities), len(self.analyses))
        if expected_counts != (
            self.summary.fact_count,
            self.summary.priority_count,
            self.summary.analysis_count,
        ):
            raise ValueError("summary counts must match response collections")
        visible_count = sum(block.visible for block in self.blocks)
        if visible_count != self.summary.visible_block_count:
            raise ValueError("visible_block_count must match visible blocks")
        if self.summary.requires_attention != bool(self.priorities):
            raise ValueError("requires_attention must reflect priorities")
        requires_decision = any(item.action == "Decidir" for item in self.analyses)
        if self.summary.requires_decision != requires_decision:
            raise ValueError("requires_decision must reflect analyses")

    def _validate_error(self) -> None:
        if (
            self.experience_status is not None
            or self.header is not None
            or self.message is not None
            or self.facts
            or self.priorities
            or self.analyses
            or self.blocks
            or self.summary is not None
            or self.error is None
        ):
            raise ValueError("ERROR response must not contain a partial experience")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("clock must return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


_INVALID_CLOCK_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)


class DailyApiFacade:
    """Coordinate official daily services and protect the public boundary."""

    def __init__(
        self,
        orchestrator: DailyOrchestrator | None = None,
        composer: DailyExperienceComposer | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._orchestrator = orchestrator if orchestrator is not None else DailyOrchestrator(
            DailyPortfolioSnapshotBuilder(),
            ImportantFactsEngine(),
            PortfolioImpactEngine(),
            DailyPriorityEngine(),
        )
        self._composer = composer if composer is not None else DailyExperienceComposer()
        self._clock = clock

    def execute(self, request: DailyApiRequest) -> DailyApiResponse:
        try:
            generated_at = _aware_utc(self._clock())
        except Exception:
            return self._error_response(
                _INVALID_CLOCK_TIME,
                DailyApiErrorCode.INTERNAL_ERROR,
                "Ocorreu uma falha interna ao preparar a experiência diária.",
                "INTERNAL",
            )

        if not self._valid_request(request):
            return self._error_response(
                generated_at,
                DailyApiErrorCode.INVALID_REQUEST,
                "A solicitação da experiência diária é inválida.",
                "REQUEST",
            )

        try:
            orchestration = self._orchestrator.run(
                positions=request.positions,
                fact_candidates=request.fact_candidates,
                reference_date=request.reference_date,
                validation_reports=request.validation_reports,
            )
            experience = self._composer.compose(orchestration)
            return self._success_response(generated_at, experience)
        except DailyOrchestrationError as error:
            return self._error_response(
                generated_at,
                DailyApiErrorCode.ORCHESTRATION_ERROR,
                "Não foi possível preparar a experiência diária.",
                error.stage.value,
            )
        except DailyExperienceError:
            return self._error_response(
                generated_at,
                DailyApiErrorCode.EXPERIENCE_ERROR,
                "Não foi possível organizar a experiência diária.",
                "EXPERIENCE",
            )
        except Exception:
            return self._error_response(
                generated_at,
                DailyApiErrorCode.INTERNAL_ERROR,
                "Ocorreu uma falha interna ao preparar a experiência diária.",
                "INTERNAL",
            )

    @staticmethod
    def _valid_request(request: object) -> bool:
        if not isinstance(request, DailyApiRequest):
            return False
        if not isinstance(request.positions, tuple) or any(
            not isinstance(item, PortfolioPosition) for item in request.positions
        ):
            return False
        if not isinstance(request.fact_candidates, tuple) or any(
            not isinstance(item, FactCandidate) for item in request.fact_candidates
        ):
            return False
        if request.reference_date is not None and not isinstance(
            request.reference_date, date
        ):
            return False
        return request.validation_reports is None or isinstance(
            request.validation_reports, Mapping
        )

    @staticmethod
    def _success_response(
        generated_at: datetime, experience: DailyExperienceResult
    ) -> DailyApiResponse:
        facts = tuple(
            DailyApiFact(item.fact_id, item.category, item.title, item.priority)
            for item in experience.facts
        )
        priorities = tuple(
            DailyApiPriority(
                item.fact_id,
                item.level.value,
                item.label,
                item.title,
                item.reason,
            )
            for item in experience.priorities
        )
        analyses = tuple(
            DailyApiAnalysis(
                item.fact_id,
                item.action_label,
                item.title,
                item.reason,
            )
            for item in experience.analyses
        )
        block_items: tuple[tuple[DailyApiBlockItem, ...], ...] = (
            facts,
            priorities,
            analyses,
        )
        block_types = {
            DailyBlockType.IMPORTANT_FACTS: "FACTS",
            DailyBlockType.DAILY_PRIORITIES: "PRIORITIES",
            DailyBlockType.DAILY_ANALYSES: "ANALYSES",
        }
        blocks = tuple(
            DailyApiBlock(
                block_types[block.block_type],
                block.visibility is DailyBlockVisibility.VISIBLE,
                block.title,
                items,
            )
            for block, items in zip(experience.blocks, block_items, strict=True)
        )
        summary = DailyApiSummary(
            experience.summary.fact_count,
            experience.summary.priority_count,
            experience.summary.analysis_count,
            experience.summary.visible_block_count,
            experience.summary.has_attention,
            experience.summary.has_decision,
        )
        return DailyApiResponse(
            status=DailyApiStatus.SUCCESS,
            generated_at=generated_at,
            experience_status=experience.status.value,
            header=DailyApiHeader(
                experience.header.greeting_text,
                experience.header.formatted_date,
                experience.header.greeting_period.value,
            ),
            message=DailyApiMessage("Resumo do dia", experience.message.text),
            facts=facts,
            priorities=priorities,
            analyses=analyses,
            blocks=blocks,
            summary=summary,
            error=None,
        )

    @staticmethod
    def _error_response(
        generated_at: datetime,
        code: DailyApiErrorCode,
        message: str,
        stage: str,
    ) -> DailyApiResponse:
        return DailyApiResponse(
            status=DailyApiStatus.ERROR,
            generated_at=generated_at,
            experience_status=None,
            header=None,
            message=None,
            facts=(),
            priorities=(),
            analyses=(),
            blocks=(),
            summary=None,
            error=DailyApiError(code, message, stage),
        )


def daily_api_response_to_dict(response: DailyApiResponse) -> dict[str, object]:
    """Return a detached JSON-safe representation of a daily API response."""

    header: dict[str, object] | None = None
    if response.header is not None:
        header = {
            "greeting": response.header.greeting,
            "display_date": response.header.display_date,
            "period": response.header.period,
        }
    message: dict[str, object] | None = None
    if response.message is not None:
        message = {"title": response.message.title, "text": response.message.text}
    summary: dict[str, object] | None = None
    if response.summary is not None:
        summary = {
            "fact_count": response.summary.fact_count,
            "priority_count": response.summary.priority_count,
            "analysis_count": response.summary.analysis_count,
            "visible_block_count": response.summary.visible_block_count,
            "requires_attention": response.summary.requires_attention,
            "requires_decision": response.summary.requires_decision,
        }
    error: dict[str, object] | None = None
    if response.error is not None:
        error = {
            "code": response.error.code.value,
            "message": response.error.message,
            "stage": response.error.stage,
        }
    return {
        "status": response.status.value,
        "generated_at": response.generated_at.isoformat(),
        "experience_status": response.experience_status,
        "header": header,
        "message": message,
        "facts": [_fact_to_dict(item) for item in response.facts],
        "priorities": [_priority_to_dict(item) for item in response.priorities],
        "analyses": [_analysis_to_dict(item) for item in response.analyses],
        "blocks": [_block_to_dict(item) for item in response.blocks],
        "summary": summary,
        "error": error,
    }


def _fact_to_dict(item: DailyApiFact) -> dict[str, object]:
    return {
        "id": item.id,
        "category": item.category,
        "text": item.text,
        "importance": item.importance,
    }


def _priority_to_dict(item: DailyApiPriority) -> dict[str, object]:
    return {
        "fact_id": item.fact_id,
        "level": item.level,
        "label": item.label,
        "title": item.title,
        "reason": item.reason,
    }


def _analysis_to_dict(item: DailyApiAnalysis) -> dict[str, object]:
    return {
        "fact_id": item.fact_id,
        "action": item.action,
        "title": item.title,
        "reason": item.reason,
    }


def _block_to_dict(item: DailyApiBlock) -> dict[str, object]:
    serialized: list[dict[str, object]] = []
    for block_item in item.items:
        if isinstance(block_item, DailyApiFact):
            serialized.append(_fact_to_dict(block_item))
        elif isinstance(block_item, DailyApiPriority):
            serialized.append(_priority_to_dict(block_item))
        else:
            serialized.append(_analysis_to_dict(block_item))
    return {
        "type": item.type,
        "visible": item.visible,
        "title": item.title,
        "items": serialized,
    }
