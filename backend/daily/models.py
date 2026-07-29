"""Shared immutable contracts for the ARGOS daily pipeline."""

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Optional, Tuple, TypeVar


DailyItem = TypeVar("DailyItem")


@dataclass(frozen=True)
class ExternalDataResult(Generic[DailyItem]):
    status: str
    items: Tuple[DailyItem, ...]
    cached: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class MarketEvent:
    identifier: str
    title: str
    category: str
    source: str
    occurred_at: datetime
    priority: str
    summary: str
    related_assets: Tuple[str, ...] = ()
    macro_impact: bool = False


@dataclass(frozen=True)
class AgendaEvent:
    identifier: str
    title: str
    category: str
    scheduled_at: datetime
    source: str
    importance: str
    related_assets: Tuple[str, ...] = ()
    time_explicit: bool = True
