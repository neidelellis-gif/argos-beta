"""Stable public facade for the official ARGOS daily experience."""

from collections.abc import Callable
from datetime import datetime, timezone

from backend.daily_contract import (
    DailyApiAnalysis,
    DailyApiBlock,
    DailyApiBlockItem,
    DailyApiError,
    DailyApiErrorCode,
    DailyApiFact,
    DailyApiHeader,
    DailyApiMessage,
    DailyApiPriority,
    DailyApiRequest,
    DailyApiResponse,
    DailyApiStatus,
    DailyApiSummary,
    validate_daily_api_request,
)
from backend.daily_experience import (
    DailyBlockType,
    DailyBlockVisibility,
    DailyExperienceComposer,
    DailyExperienceError,
    DailyExperienceResult,
)
from backend.daily_orchestrator import DailyOrchestrationError, DailyOrchestrator
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityEngine
from backend.important_facts import ImportantFactsEngine
from backend.portfolio_impact import PortfolioImpactEngine


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

        if not validate_daily_api_request(request):
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
                "MEDIUM" if item.level.value == "MODERATE" else item.level.value,
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
        "contract_version": response.contract_version,
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
