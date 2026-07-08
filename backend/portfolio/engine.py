def analyze_portfolio(positions):
    total = sum(p["value"] for p in positions)

    high_priority = []
    medium_priority = []

    for p in positions:
        weight = p["value"] / total * 100
        p["weight"] = weight

        if weight >= 5:
            high_priority.append(p)
        elif weight >= 3:
            medium_priority.append(p)

    high_priority.sort(key=lambda x: x["weight"], reverse=True)
    medium_priority.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "total": total,
        "positions_count": len(positions),
        "high_priority": high_priority,
        "medium_priority": medium_priority,
    }