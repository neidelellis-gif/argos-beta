from collections import defaultdict

from backend.assets.manager import normalize_position


def consolidate_accounts(accounts):
    total = sum(account["total"] for account in accounts)

    consolidated = defaultdict(
        lambda: {
            "symbol": "",
            "name": "",
            "class": "",
            "total_value": 0.0,
            "accounts": defaultdict(float),
        }
    )

    for account in accounts:
        bank = account["name"]

        for raw_position in account["positions"]:
            position = normalize_position(raw_position)
            key = position["symbol"]

            item = consolidated[key]
            item["symbol"] = position["symbol"]
            item["name"] = position["name"]
            item["class"] = position.get("class", "")
            item["total_value"] += position["value"]
            item["accounts"][bank] += position["value"]

    positions = []

    for item in consolidated.values():
        item["accounts"] = dict(item["accounts"])
        item["weight"] = item["total_value"] / total * 100 if total > 0 else 0
        positions.append(item)

    return {
        "accounts": accounts,
        "total": total,
        "positions": sorted(
            positions,
            key=lambda x: x["total_value"],
            reverse=True,
        ),
    }
