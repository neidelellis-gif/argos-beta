"""Assembly of the standardized Daily structure."""

from typing import Dict, List

from backend.daily.context_service import DailyContextService
from backend.daily.experience import build_analyses, build_priorities


class DailyOrchestrator:
    """Build the Daily contract without fetching or interpreting data."""

    def __init__(self, context_service=None):
        self._context_service = context_service or DailyContextService()

    def build(self) -> Dict[str, List]:
        """Return a new Daily structure populated from the official facts source."""
        context = self._context_service.generate(())
        return {
            "facts": list(context["facts"]),
            "priorities": build_priorities(context["facts"]),
            "analyses": build_analyses(context["facts"]),
            "agenda": list(context["agenda"]),
        }
