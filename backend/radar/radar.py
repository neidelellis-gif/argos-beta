def build_radar(portfolio):
    alerts = []

    for p in portfolio["high_priority"]:
        alerts.append({
            "name": p["name"],
            "class": p["class"],
            "priority": "Alta",
            "reason": f"Peso relevante na carteira: {p['weight']:.2f}%"
        })

    for p in portfolio["medium_priority"]:
        alerts.append({
            "name": p["name"],
            "class": p["class"],
            "priority": "Média",
            "reason": f"Peso relevante na carteira: {p['weight']:.2f}%"
        })

    return alerts