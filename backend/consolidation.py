from typing import Dict, Iterable, List


def _is_identifier_like(value: str) -> bool:
    clean = value.strip().upper()
    if not clean:
        return False
    if len(clean) == 12 and clean[:2].isalpha() and clean[2:].isdigit():
        return True
    if len(clean) in {9, 10} and clean.isalnum():
        return True
    return False


def _canonize_asset(symbol: str, name: str, description: str):
    normalized_symbol = symbol.upper()
    normalized_name = name.upper()
    normalized_description = description.upper()

    if normalized_symbol in {"US78463V1070", "GLD"} or "SPDR GOLD TRUST" in normalized_name or "SPDR GOLD TRUST" in normalized_description:
        return "GLD", "SPDR GOLD TRUST"
    if normalized_symbol in {"US45866F1049", "ICE"} or "INTERCONTINENTAL EXCHANGE" in normalized_name or "INTERCONTINENTAL EXCHANGE" in normalized_description:
        return "ICE", "INTERCONTINENTAL EXCHANGE INC"
    if normalized_symbol in {"US4781601046", "JNJ"} or "JOHNSON & JOHNSON" in normalized_name or "JOHNSON & JOHNSON" in normalized_description:
        return "JNJ", "JOHNSON & JOHNSON"
    if normalized_symbol in {"US025816EF26", "AXP"} or "AMERICAN EXPRESS" in normalized_name or "AMERICAN EXPRESS" in normalized_description:
        return "AXP", "AMERICAN EXPRESS COMPANY"
    if normalized_symbol in {"US78468R6633", "BIL"} or "SPDR BBG 1-3 MONTH TBILL ETF" in normalized_name or "SPDR BBG 1-3 MONTH TBILL ETF" in normalized_description:
        return "BIL", "SPDR BBG 1-3 MONTH TBILL ETF"

    if not symbol or symbol.upper() in {"N/A", ""}:
        display = name or description
        return display, display

    if _is_identifier_like(symbol) and name and name.upper() != symbol.upper():
        return name, name

    if name and _is_identifier_like(name) and description and description.upper() != name.upper():
        return description, description

    if not name and symbol:
        return symbol, symbol

    return symbol, name or description or symbol


def _normalize_position(position: Dict) -> Dict:
    symbol = str(position.get("symbol") or "").strip()
    name = str(position.get("name") or position.get("description") or "").strip()
    description = str(position.get("description") or "").strip()

    canonical_symbol, canonical_name = _canonize_asset(symbol, name, description)
    if canonical_symbol == canonical_name and canonical_symbol and _is_identifier_like(canonical_symbol) and description:
        canonical_name = description

    if _is_identifier_like(canonical_symbol) and name and name.upper() != canonical_symbol.upper():
        canonical_symbol = name

    if not canonical_symbol or canonical_symbol.upper() in {"N/A", ""}:
        canonical_symbol = name or description or "UNKNOWN"

    return {
        "institution": position.get("institution", ""),
        "account": position.get("account", ""),
        "symbol": canonical_symbol,
        "name": canonical_name,
        "description": description,
        "asset_class": position.get("asset_class") or "Outros",
        "currency": position.get("currency") or "USD",
        "value": float(position.get("value", 0.0) or 0.0),
    }


def consolidate_positions(ubs_positions: Iterable[Dict], santander_positions: Iterable[Dict]) -> Dict:
    all_positions = [
        _normalize_position(position)
        for position in list(ubs_positions) + list(santander_positions)
    ]

    consolidated: Dict[str, Dict] = {}
    institution_order: List[str] = []
    institution_totals: Dict[str, float] = {}

    for position in all_positions:
        key = position["symbol"]
        if not key:
            key = position["name"]

        institution_name = str(position.get("institution") or "UNKNOWN").strip() or "UNKNOWN"
        if institution_name not in institution_totals:
            institution_order.append(institution_name)
            institution_totals[institution_name] = 0.0
        institution_totals[institution_name] += position["value"]

        if key in consolidated:
            consolidated[key]["value"] += position["value"]
            consolidated[key]["institution_values"][institution_name] = (
                consolidated[key]["institution_values"].get(institution_name, 0.0) + position["value"]
            )
        else:
            consolidated[key] = {
                "symbol": position["symbol"],
                "name": position["name"],
                "description": position["description"],
                "asset_class": position["asset_class"],
                "currency": position["currency"],
                "value": position["value"],
                "institution_values": {institution_name: position["value"]},
            }

    total_value = sum(item["value"] for item in consolidated.values())

    position_rows: List[Dict] = []
    for item in consolidated.values():
        weight = (item["value"] / total_value * 100) if total_value else 0.0
        institutions: List[Dict] = []

        for institution_name in institution_order:
            institution_value = item["institution_values"].get(institution_name, 0.0)
            institution_weight = (
                institution_value / institution_totals[institution_name] * 100
            ) if institution_totals[institution_name] else 0.0

            institutions.append({
                "name": institution_name,
                "value": institution_value,
                "weight_in_institution": institution_weight,
            })

        position_rows.append({
            "symbol": item["symbol"],
            "name": item["name"],
            "total_value": item["value"],
            "weight": weight,
            "institutions": institutions,
        })

    position_rows.sort(key=lambda item: item["total_value"], reverse=True)

    top_positions = position_rows[:20]
    top_symbol = top_positions[0]["symbol"] if top_positions else "N/A"
    top_weight = top_positions[0]["weight"] if top_positions else 0.0

    totals = {"Total consolidado": total_value}
    totals.update({f"Total {name}": value for name, value in institution_totals.items()})

    return {
        "argos_ai": {
            "title": "Consolidação JOLIKA",
            "items": [
                f"Total consolidado de {len(position_rows)} posições.",
                f"Maior posição é {top_symbol} com {top_weight:.2f}% do total.",
                ", ".join(
                    f"{name}: {value:.2f}"
                    for name, value in institution_totals.items()
                ) + ".",
            ],
            "next_action": "Verificar exposição por ativo e buscar equilíbrio entre instituições.",
        },
        "totals": totals,
        "top_positions": top_positions,
    }
