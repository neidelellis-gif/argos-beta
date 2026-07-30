"""Stable public facade for the official ARGOS daily experience."""

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from backend.daily_contract import (
    DailyApiAnalysis,
    DailyApiBlock,
    DailyApiBlockItem,
    DailyApiError,
    DailyApiErrorCode,
    DailyApiFact,
    DailyApiHeader,
    DailyApiImpactAssessment,
    DailyApiDecisionContext,
    DailyApiDataQuality,
    DailyApiMessage,
    DailyApiMarketAgendaEvent,
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
from backend.daily_facts_engine import DailyFactsEngine
from backend.daily_analysis_engine import DailyAnalysisEngine
from backend.daily_priority_engine import DailyPriorityEngine as AnalysisPriorityEngine
from backend.daily_orchestrator import DailyOrchestrationError, DailyOrchestrator
from backend.daily_portfolio_snapshot import DailyPortfolioSnapshotBuilder
from backend.daily_priority import DailyPriorityEngine
from backend.important_facts import ImportantFactsEngine
from backend.portfolio_impact import PortfolioImpactEngine
from backend.market_agenda_engine import MarketAgendaEngine
from backend.portfolio_impact_engine import PortfolioImpactAssessmentEngine
from backend.decision_context_engine import DecisionContextEngine
from backend.data_quality_engine import DataQualityEngine


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("clock must return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


_INVALID_CLOCK_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _iterable(value: object) -> Iterable[object]:
    return value if isinstance(value, (list, tuple)) else ()


def _data_quality_contract(value: dict[str, object] | None) -> DailyApiDataQuality:
    if value is None:
        value = {"status": "ERROR", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                 "diagnostics": [{"id": "system.daily_experience", "severity": "ERROR",
                    "category": "SYSTEM", "title": "Experiência indisponível",
                    "description": "A qualidade dos dados não pôde ser concluída.",
                    "affected_items": [], "can_continue": False}]}
    summary = value["summary"]
    diagnostics = value["diagnostics"]
    if not isinstance(summary, dict) or not isinstance(diagnostics, list):
        raise TypeError("invalid data quality result")
    return DailyApiDataQuality(str(value["status"]), dict(summary),
                               tuple(dict(item) for item in diagnostics if isinstance(item, dict)))


class DailyApiFacade:
    """Coordinate official daily services and protect the public boundary."""

    def __init__(
        self,
        orchestrator: DailyOrchestrator | None = None,
        composer: DailyExperienceComposer | None = None,
        clock: Callable[[], datetime] = _utc_now,
        facts_engine: DailyFactsEngine | None = None,
        analysis_engine: DailyAnalysisEngine | None = None,
        priority_engine: AnalysisPriorityEngine | None = None,
        market_agenda_engine: MarketAgendaEngine | None = None,
        impact_engine: PortfolioImpactAssessmentEngine | None = None,
        decision_context_engine: DecisionContextEngine | None = None,
        data_quality_engine: DataQualityEngine | None = None,
    ) -> None:
        self._orchestrator = orchestrator if orchestrator is not None else DailyOrchestrator(
            DailyPortfolioSnapshotBuilder(),
            ImportantFactsEngine(),
            PortfolioImpactEngine(),
            DailyPriorityEngine(),
        )
        self._composer = composer if composer is not None else DailyExperienceComposer()
        self._clock = clock
        self._facts_engine = facts_engine if facts_engine is not None else DailyFactsEngine()
        self._analysis_engine = analysis_engine if analysis_engine is not None else DailyAnalysisEngine()
        self._priority_engine = priority_engine if priority_engine is not None else AnalysisPriorityEngine()
        self._market_agenda_engine = market_agenda_engine if market_agenda_engine is not None else MarketAgendaEngine()
        self._impact_engine = impact_engine if impact_engine is not None else PortfolioImpactAssessmentEngine()
        self._decision_context_engine = decision_context_engine or DecisionContextEngine()
        self._data_quality_engine = data_quality_engine or DataQualityEngine()

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
            quality = self._data_quality_engine.diagnose(
                request.positions, request.agenda_events, request.decision_profile,
                request.reference_date or generated_at.date(),
            )
            generated_facts = self._facts_engine.generate(
                request.positions, request.fact_candidates
            )
            agenda = self._market_agenda_engine.generate(
                request.agenda_events, request.positions, request.reference_date
            )
            event_by_id = {f"agenda-{event.event_id}": event for event in request.agenda_events}
            impact_agenda = []
            for item in agenda:
                enriched = dict(item)
                event = event_by_id.get(str(item["id"]))
                if event is not None:
                    enriched.update({
                        "asset_identifiers": list(event.asset_identifiers),
                        "asset_names": list(event.asset_names), "asset_classes": list(event.asset_classes),
                        "sectors": list(event.sectors), "currencies": list(event.currencies),
                        "markets": list(event.markets), "country": event.country,
                        "institution": event.institution,
                    })
                impact_agenda.append(enriched)
            impacts = self._impact_engine.generate(generated_facts, impact_agenda, request.positions)
            analyses = self._analysis_engine.generate(generated_facts, request.positions, impacts)
            priorities = self._priority_engine.generate(analyses, request.positions)
            decision_contexts = self._decision_context_engine.generate(
                request.decision_profile, generated_facts, impact_agenda, impacts,
                analyses, priorities, request.positions, request.reference_date,
            )
            context_by_id = {item.id: item for item in request.fact_candidates}
            fact_candidates = tuple(
                context_by_id[str(item["id"])] for item in generated_facts
            )
            orchestration = self._orchestrator.run(
                positions=request.positions,
                fact_candidates=fact_candidates,
                reference_date=request.reference_date,
                validation_reports=request.validation_reports,
            )
            experience = self._composer.compose_priorities(orchestration, priorities)
            return self._success_response(generated_at, experience, agenda, impacts, decision_contexts, quality)
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
        generated_at: datetime, experience: DailyExperienceResult,
        agenda: tuple[dict[str, object], ...] = (),
        impacts: list[dict[str, object]] | tuple[dict[str, object], ...] = (),
        decision_contexts: tuple[dict[str, object], ...] = (),
        data_quality: dict[str, object] | None = None,
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
            market_agenda=tuple(DailyApiMarketAgendaEvent(
                id=str(item["id"]), event_type=str(item["event_type"]),
                importance=str(item["importance"]), title=str(item["title"]),
                summary=str(item["description"]), event_date=str(item["event_date"]),
                event_time=item["event_time"] if isinstance(item["event_time"], str) else None,
                timezone=item["timezone"] if isinstance(item["timezone"], str) else None,
                all_day=bool(item["all_day"]),
                affected_assets=tuple(str(value) for value in _iterable(item["affected_assets"])),
                source_name=str(item["source_name"]),
            ) for item in agenda),
            impact_assessments=tuple(DailyApiImpactAssessment(
                id=str(item["id"]), source_type=str(item["source_type"]),
                impact_level=str(item["impact_level"]), impact_direction=str(item["impact_direction"]),
                confidence=str(item["confidence"]), title=str(item["title"]), summary=str(item["summary"]),
                affected_assets=tuple(str(value) for value in _iterable(item["affected_assets"])),
                impact_factors=tuple(dict(factor) for factor in _iterable(item["impact_factors"]) if isinstance(factor, dict)),
            ) for item in impacts[:5]),
            decision_contexts=tuple(DailyApiDecisionContext(
                id=str(item["id"]), context_type=str(item["context_type"]),
                relevance_level=str(item["relevance_level"]), title=str(item["title"]),
                summary=str(item["summary"]),
                related_assets=tuple(str(value) for value in _iterable(item["related_assets"])),
                context_factors=tuple(dict(value) for value in _iterable(item["context_factors"]) if isinstance(value, dict)),
                limitations=tuple(str(value) for value in _iterable(item["limitations"])),
            ) for item in decision_contexts[:5]),
            data_quality=_data_quality_contract(data_quality),
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
            data_quality=_data_quality_contract(None),
        )


def daily_api_response_to_dict(response: DailyApiResponse) -> dict[str, object]:
    """Return a detached JSON-safe representation of a daily API response."""

    quality = response.data_quality
    if quality is None:  # Defensive guard for static callers bypassing the dataclass validation.
        raise TypeError("response data_quality is required")

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
        "market_agenda": [{
            "id": item.id, "event_type": item.event_type, "importance": item.importance,
            "title": item.title, "summary": item.summary, "event_date": item.event_date,
            "event_time": item.event_time, "timezone": item.timezone, "all_day": item.all_day,
            "affected_assets": list(item.affected_assets), "source_name": item.source_name,
        } for item in response.market_agenda],
        "impact_assessments": [{
            "id": item.id, "source_type": item.source_type, "impact_level": item.impact_level,
            "impact_direction": item.impact_direction, "confidence": item.confidence,
            "title": item.title, "summary": item.summary,
            "affected_assets": list(item.affected_assets),
            "impact_factors": [dict(factor) for factor in item.impact_factors],
        } for item in response.impact_assessments],
        "decision_contexts": [{
            "id": item.id, "context_type": item.context_type,
            "relevance_level": item.relevance_level, "title": item.title,
            "summary": item.summary, "related_assets": list(item.related_assets),
            "context_factors": [dict(factor) for factor in item.context_factors],
            "limitations": list(item.limitations),
        } for item in response.decision_contexts],
        "data_quality": {
            "status": quality.status,
            "summary": dict(quality.summary),
            "diagnostics": [dict(item) for item in quality.diagnostics],
        },
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
