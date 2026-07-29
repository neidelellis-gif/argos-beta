"""Shared transformations for the standardized Daily contract."""


def build_priorities(facts):
    """Project the first prioritized facts onto the existing Daily contract."""
    return [
        {
            "id": fact["id"],
            "title": fact["title"],
            "level": fact["priority"],
            "context": fact["context"],
        }
        for fact in facts[:3]
    ]


def build_analyses(facts):
    """Project relevant facts onto the existing analyses contract."""
    return [
        {
            "id": fact["id"],
            "title": fact["title"],
            "reason": fact["summary"],
            "related_to": ", ".join(fact["matched_portfolio_assets"]) or None,
            "status": fact["context"],
            "updated_at": fact["occurred_at"],
        }
        for fact in facts
        if fact["context_type"] in {"portfolio", "macro"}
    ][:2]
