from backend.config.settings import HIGH_PRIORITY, MEDIUM_PRIORITY


def analyze_portfolio(positions):
    total = sum(p["value"] for p in positions)

    high_priority = []
    medium_priority = []

    for p in positions:
        weight = p["value"] / total * 100
        p["weight"] = weight

        if weight >= HIGH_PRIORITY:
            high_priority.append(p)
        elif weight >= MEDIUM_PRIORITY:
            medium_priority.append(p)

    high_priority.sort(key=lambda x: x["weight"], reverse=True)
    medium_priority.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "total": total,
        "positions_count": len(positions),
        "high_priority": high_priority,
        "medium_priority": medium_priority,
    }