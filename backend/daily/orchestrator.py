"""Assembly of the standardized Daily structure."""

from typing import Dict, List


class DailyOrchestrator:
    """Build the Daily contract without fetching or interpreting data."""

    def build(self) -> Dict[str, List]:
        """Return a new, empty Daily structure."""
        return {
            "facts": [],
            "priorities": [],
            "analyses": [],
            "agenda": [],
        }
