"""Versioned public contract for the ARGOS daily experience.

This module contains only boundary types and structural validation.  Business
decisions remain in the orchestrator and experience composer.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from backend.daily_portfolio_snapshot import ValidationReportKey
from backend.import_validation import ImportValidationReport
from backend.important_facts import FactCandidate
from backend.models import PortfolioPosition


CONTRACT_VERSION = "1.0"


class DailyApiStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class DailyExperienceStatus(str, Enum):
    READY = "READY"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    DECISION_REQUIRED = "DECISION_REQUIRED"


class DailyPriorityLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DailyApiBlockType(str, Enum):
    FACTS = "FACTS"
    PRIORITIES = "PRIORITIES"
    ANALYSES = "ANALYSES"


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
    validation_reports: Mapping[ValidationReportKey, ImportValidationReport] | None = None


def validate_daily_api_request(request: object) -> bool:
    """Validate the four official request fields without executing business logic."""
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
    if request.reference_date is not None and not isinstance(request.reference_date, date):
        return False
    return request.validation_reports is None or isinstance(request.validation_reports, Mapping)


@dataclass(frozen=True)
class DailyApiHeader:
    greeting: str
    display_date: str
    period: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.greeting, self.display_date)):
            raise ValueError("header text must not be empty")
        if self.period not in {"MORNING", "AFTERNOON", "EVENING"}:
            raise ValueError("period must be an official greeting period")


@dataclass(frozen=True)
class DailyApiMessage:
    title: str
    text: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.title, self.text)):
            raise ValueError("message text must not be empty")


@dataclass(frozen=True)
class DailyApiFact:
    id: str
    category: str
    text: str
    importance: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.id, self.category, self.text, self.importance)):
            raise ValueError("fact fields must not be empty")


@dataclass(frozen=True)
class DailyApiPriority:
    fact_id: str
    level: str
    label: str
    title: str
    reason: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.fact_id, self.level, self.title, self.reason)):
            raise ValueError("priority fields must not be empty")
        if self.level not in {level.value for level in DailyPriorityLevel}:
            raise ValueError("level must be an official priority level")
        if self.label not in {"Alta", "Moderada", "Baixa"}:
            raise ValueError("label must be an official priority label")


@dataclass(frozen=True)
class DailyApiAnalysis:
    fact_id: str
    action: str
    title: str
    reason: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.fact_id, self.title, self.reason)):
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
        allowed = {item.value for item in DailyApiBlockType}
        if self.type not in allowed:
            raise ValueError("type must be an official daily API block type")
        if not isinstance(self.visible, bool):
            raise TypeError("visible must be a boolean")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        expected_type = {"FACTS": DailyApiFact, "PRIORITIES": DailyApiPriority, "ANALYSES": DailyApiAnalysis}[self.type]
        if any(not isinstance(item, expected_type) for item in self.items):
            raise TypeError("block items must match the block type")
        expected_title = {"FACTS": "Fatos importantes", "PRIORITIES": "Prioridades do dia", "ANALYSES": "Análises"}[self.type]
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
        counts = (self.fact_count, self.priority_count, self.analysis_count, self.visible_block_count)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in counts):
            raise TypeError("summary counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("summary counts must not be negative")
        if not isinstance(self.requires_attention, bool) or not isinstance(self.requires_decision, bool):
            raise TypeError("summary flags must be booleans")


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
        if self.stage is not None and (not isinstance(self.stage, str) or not self.stage.strip()):
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
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError("contract_version is incompatible")
        if not isinstance(self.status, DailyApiStatus):
            raise TypeError("status must be a DailyApiStatus")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        object.__setattr__(self, "generated_at", self.generated_at.astimezone(timezone.utc))
        if any(not isinstance(items, tuple) for items in (self.facts, self.priorities, self.analyses, self.blocks)):
            raise TypeError("response collections must be tuples")
        if self.status is DailyApiStatus.SUCCESS:
            self._validate_success()
        else:
            self._validate_error()

    def _validate_success(self) -> None:
        if self.experience_status is None or self.header is None or self.message is None or self.summary is None or self.error is not None:
            raise ValueError("SUCCESS response must contain one complete experience")
        if self.experience_status not in {status.value for status in DailyExperienceStatus}:
            raise ValueError("experience_status must be an official status")
        expected_classes = (DailyApiFact, DailyApiPriority, DailyApiAnalysis, DailyApiBlock)
        for items, expected in zip((self.facts, self.priorities, self.analyses, self.blocks), expected_classes, strict=True):
            if any(not isinstance(item, expected) for item in items):
                raise TypeError("response collection contains an invalid item")
        official_blocks = tuple(item.value for item in DailyApiBlockType)
        if tuple(block.type for block in self.blocks) != official_blocks:
            raise ValueError("SUCCESS response must contain the official blocks")
        expected_items = (self.facts, self.priorities, self.analyses)
        if tuple(block.items for block in self.blocks) != expected_items:
            raise ValueError("block items must match response collections")
        if (len(self.facts), len(self.priorities), len(self.analyses)) != (self.summary.fact_count, self.summary.priority_count, self.summary.analysis_count):
            raise ValueError("summary counts must match response collections")
        if sum(block.visible for block in self.blocks) != self.summary.visible_block_count:
            raise ValueError("visible_block_count must match visible blocks")
        if self.summary.requires_attention != bool(self.priorities):
            raise ValueError("requires_attention must reflect priorities")
        if self.summary.requires_decision != any(item.action == "Decidir" for item in self.analyses):
            raise ValueError("requires_decision must reflect analyses")

    def _validate_error(self) -> None:
        if self.experience_status is not None or self.header is not None or self.message is not None or self.facts or self.priorities or self.analyses or self.blocks or self.summary is not None or self.error is None:
            raise ValueError("ERROR response must not contain a partial experience")


RESPONSE_REQUIRED_FIELDS = frozenset({
    "status", "generated_at", "contract_version", "experience_status", "header",
    "message", "facts", "priorities", "analyses", "blocks", "summary", "error",
})


def validate_daily_api_response_payload(payload: object) -> bool:
    """Validate required fields, version, top-level types, and official enums."""
    if not isinstance(payload, Mapping) or not RESPONSE_REQUIRED_FIELDS <= payload.keys():
        return False
    if payload["contract_version"] != CONTRACT_VERSION or payload["status"] not in {item.value for item in DailyApiStatus}:
        return False
    if payload["status"] == DailyApiStatus.ERROR.value:
        return (
            payload["experience_status"] is None
            and payload["header"] is None
            and payload["message"] is None
            and all(payload[field] == [] for field in ("facts", "priorities", "analyses", "blocks"))
            and payload["summary"] is None
            and isinstance(payload["error"], Mapping)
        )
    return (
        isinstance(payload["generated_at"], str)
        and payload["experience_status"] in {item.value for item in DailyExperienceStatus}
        and isinstance(payload["header"], Mapping)
        and isinstance(payload["message"], Mapping)
        and all(isinstance(payload[field], list) for field in ("facts", "priorities", "analyses", "blocks"))
        and isinstance(payload["summary"], Mapping)
        and payload["error"] is None
        and all(isinstance(fact, Mapping) and fact.get("importance") in {item.value for item in DailyPriorityLevel} for fact in payload["facts"])
        and all(isinstance(priority, Mapping) and priority.get("level") in {item.value for item in DailyPriorityLevel} for priority in payload["priorities"])
        and all(isinstance(block, Mapping) and block.get("type") in {item.value for item in DailyApiBlockType} for block in payload["blocks"])
    )
