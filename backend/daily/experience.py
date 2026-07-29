"""Compatibility entry point for building the ARGOS Daily experience."""

from datetime import date, datetime
from typing import Dict, Iterable, Optional

from backend.daily.context_service import DailyContextService
from backend.daily.orchestrator import DailyOrchestrator, PANORAMA_TOPICS as PANORAMA_TOPICS
from backend.models import PortfolioPosition


def build_daily_experience(
    positions: Iterable[PortfolioPosition],
    current_date: Optional[date] = None,
    now: Optional[datetime] = None,
    context_service: Optional[DailyContextService] = None,
) -> Dict:
    """Build the Daily contract through the official orchestrator."""
    return DailyOrchestrator(context_service=context_service).build(
        positions=positions,
        current_date=current_date,
        now=now,
    )
