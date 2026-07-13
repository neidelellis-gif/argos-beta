import re
from typing import Dict, Iterable, List

from backend.config.contribution_assumptions import BLOCK_ASSUMPTIONS, META_BASE


_KNOWN_SHORT_NAMES = {
    "VISTAONE": "VistaOne",
    "MFFXJR": "BGF Next Generation Technology",
    "MFLWCA": "PIMCO Income Fund E (Acc)",
}

_PRIVATE_CREDIT_PREFIXES = [
    ("LPM ", "LPM Private Credit"),
    ("LCRED ", "LCRED Private Credit"),
]

_ISSUER_ALIASES = [
    ("ELECTRICITE DE FRANCE", "EDF"),
    ("BANCO SANTANDER", "Santander"),
    ("JPMORGAN CHASE", "JPMorgan"),
    ("JP MORGAN CHASE", "JPMorgan"),
    ("TEVA PHARMACEUTICAL", "Teva"),
    ("FREEPORT-MCMORAN", "Freeport-McMoRan"),
    ("FREEPORT MCMORAN", "Freeport-McMoRan"),
    ("ENERGY TRANSFER", "Energy Transfer"),
    ("UNITED STATES STEEL", "U.S. Steel"),
]

# Vencimento conhecido para títulos cujo texto bruto às vezes não traz o ano.
_KNOWN_BOND_MATURITIES = {
    ("JPMorgan", "5.35"): "2037",
    ("Teva", "6.75"): "2028",
    ("Freeport-McMoRan", "5.25"): "2029",
    ("Energy Transfer", "6.94"): "2066",
    ("U.S. Steel", "6.875"): "2029",
}

# Símbolos tratados como Caixa Remunerado no bloco analítico do Cockpit.
# Não altera a classificação original do conector.
_CAIXA_REMUNERADO_SYMBOLS = {"BIL"}

# Tickers reconhecidos pelo ARGOS como ETF para reclassificação analítica de "ETF/Fundo".
_KNOWN_ETF_SYMBOLS = {"GLD", "BIL", "SMH"}


def _format_rate(rate: str) -> str:
    text = f"{float(rate):.3f}".rstrip("0").rstrip(".")
    return text


def _friendly_name(name: str) -> str:
    if not name:
        return name

    upper = name.upper()

    if "BLACKSTONE" in upper and "BXPE" in upper:
        return "BXPE"

    for keyword, short_name in _KNOWN_SHORT_NAMES.items():
        if upper.startswith(keyword):
            return short_name

    for prefix, friendly_name in _PRIVATE_CREDIT_PREFIXES:
        if upper.startswith(prefix):
            return friendly_name

    for keyword, short_name in _ISSUER_ALIASES:
        if keyword in upper:
            rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%", name)
            year_matches = re.findall(r"\b(?:19|20)\d{2}\b", name)

            parts = [short_name]
            formatted_rate = None
            if rate_match:
                formatted_rate = _format_rate(rate_match.group(1))
                parts.append(f"{formatted_rate}%")

            year = year_matches[-1] if year_matches else _KNOWN_BOND_MATURITIES.get((short_name, formatted_rate))
            if year:
                parts.append(year)
            return " ".join(parts)

    return name


def _is_technical_code(symbol: str) -> bool:
    clean = (symbol or "").strip().upper()
    if not clean:
        return False
    if not clean.isalnum():
        return False
    if not (9 <= len(clean) <= 12):
        return False
    return any(char.isdigit() for char in clean)


def _is_identifier_like(value: str) -> bool:
    clean = value.strip().upper()
    if not clean:
        return False
    if len(clean) == 12 and clean[:2].isalpha() and clean[2:].isdigit():
        return True
    if len(clean) in {9, 10} and clean.isalnum():
        return True
    return False


def _resolve_etf_fundo_class(position: Dict) -> str:
    haystack = f"{position.get('name', '')} {position.get('description', '')}".upper()
    if "ETF" in haystack:
        return "ETF"
    if position.get("symbol", "").upper() in _KNOWN_ETF_SYMBOLS:
        return "ETF"
    return "Fundo"


def _generate_next_action(position_rows: List[Dict], liquidity: Dict, threshold: float = 5.0, liq_threshold: float = 10.0) -> str:
    concentrated = [p for p in position_rows if p["weight"] > threshold]
    liq_weight = liquidity.get("total", {}).get("weight", 0.0)

    parts = []

    if concentrated:
        top = concentrated[0]
        label = top["symbol"] if not top.get("is_technical_code") else top["name"]
        parts.append(
            f"{label} representa {top['weight']:.2f}% da Jolika"
            " e merece monitoramento de concentração."
        )

    if liq_weight > liq_threshold:
        parts.append(f"A liquidez total está em {liq_weight:.1f}%, criando capacidade de alocação.")

    if not parts:
        return "Nenhuma concentração individual acima de 5% foi identificada."

    return " ".join(parts)


def _classify_block(midpoint: float) -> str:
    if midpoint >= META_BASE:
        return "MOTOR"
    if midpoint >= 7.0:
        return "CONTRIBUIDOR"
    if midpoint >= 3.0:
        return "NEUTRO"
    return "ARRASTO ESPERADO"


def _compute_contribution_analysis(by_asset_class: Dict, liquidity: Dict) -> Dict:
    caixa_rem_weight = liquidity.get("caixa_remunerado", {}).get("weight", 0.0)

    # Constrói pesos efetivos por bloco analítico.
    # BIL é extraído da Renda Fixa e tratado como Caixa Remunerado apenas aqui.
    effective: Dict[str, float] = {}
    for cls, data in by_asset_class.items():
        w = data["weight"]
        if cls == "Renda Fixa":
            w = max(0.0, w - caixa_rem_weight)
        effective[cls] = w
    if caixa_rem_weight > 0:
        effective["Caixa Remunerado"] = caixa_rem_weight

    modeled: List[Dict] = []
    unmodeled: List[Dict] = []
    total_weighted_return = 0.0
    modeled_weight = 0.0

    for name, assumption in BLOCK_ASSUMPTIONS.items():
        weight = effective.get(name, 0.0)
        if weight <= 0.0:
            continue
        low = assumption["return_low"]
        high = assumption["return_high"]
        mid = (low + high) / 2.0
        contribution = weight * mid / 100.0
        total_weighted_return += contribution
        modeled_weight += weight
        modeled.append({
            "name": name,
            "weight": round(weight, 4),
            "return_low": low,
            "return_high": high,
            "return_mid": round(mid, 4),
            "weighted_contribution": round(contribution, 4),
            "classification": _classify_block(mid),
        })

    for cls, weight in effective.items():
        if cls not in BLOCK_ASSUMPTIONS and weight > 0:
            unmodeled.append({
                "name": cls,
                "weight": round(weight, 4),
                "return_low": None,
                "return_high": None,
                "return_mid": None,
                "weighted_contribution": None,
                "classification": None,
            })

    modeled.sort(key=lambda b: b["weighted_contribution"], reverse=True)
    blocks = modeled + unmodeled

    gap = total_weighted_return - META_BASE
    conclusion = (
        "Com as premissas estruturais atuais, a capacidade ponderada hipotética do capital modelado "
        "está abaixo da meta-base. É necessário investigar a composição interna dos blocos "
        "antes de sugerir realocação."
        if total_weighted_return < META_BASE else
        "A capacidade ponderada hipotética do capital modelado atinge ou supera a meta-base "
        "com as premissas atuais."
    )

    return {
        "meta_base": META_BASE,
        "total_weighted_return": round(total_weighted_return, 4),
        "modeled_weight": round(modeled_weight, 4),
        "gap": round(gap, 4),
        "conclusion": conclusion,
        "methodology_note": (
            "ETF, Fundo e Alternativos são blocos heterogêneos. "
            "A análise atual é estrutural por classe e não substitui análise por mandato ou ativo."
        ),
        "blocks": blocks,
    }


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

        friendly_name = _friendly_name(item["name"])
        no_real_ticker = (
            item["symbol"].strip().upper() == item["name"].strip().upper()
            and friendly_name.strip().upper() != item["symbol"].strip().upper()
        )

        position_rows.append({
            "symbol": item["symbol"],
            "name": friendly_name,
            "description": item["description"],
            "asset_class": item["asset_class"],
            "is_technical_code": _is_technical_code(item["symbol"]) or no_real_ticker,
            "total_value": item["value"],
            "weight": weight,
            "institutions": institutions,
        })

    position_rows.sort(key=lambda item: item["total_value"], reverse=True)

    # Alocação por classe — calculada de TODAS as posições antes do corte Top 20.
    # "ETF/Fundo" é reclassificado analiticamente; a classificação original da posição não é alterada.
    by_asset_class: Dict[str, Dict] = {}
    for row in position_rows:
        cls = row["asset_class"] or "Outros"
        if cls == "ETF/Fundo":
            cls = _resolve_etf_fundo_class(row)
        if cls not in by_asset_class:
            by_asset_class[cls] = {"value": 0.0, "weight": 0.0, "count": 0}
        by_asset_class[cls]["value"] += row["total_value"]
        by_asset_class[cls]["count"] += 1
    for cls in by_asset_class:
        by_asset_class[cls]["weight"] = (
            by_asset_class[cls]["value"] / total_value * 100
        ) if total_value else 0.0

    # Liquidez analítica (não altera classificação original do conector).
    caixa_value = by_asset_class.get("Caixa", {}).get("value", 0.0)
    caixa_remunerado_value = sum(
        row["total_value"] for row in position_rows
        if row["symbol"].upper() in _CAIXA_REMUNERADO_SYMBOLS
    )
    liquidity = {
        "caixa": {
            "value": caixa_value,
            "weight": (caixa_value / total_value * 100) if total_value else 0.0,
        },
        "caixa_remunerado": {
            "value": caixa_remunerado_value,
            "weight": (caixa_remunerado_value / total_value * 100) if total_value else 0.0,
        },
        "total": {
            "value": caixa_value + caixa_remunerado_value,
            "weight": (
                (caixa_value + caixa_remunerado_value) / total_value * 100
            ) if total_value else 0.0,
        },
    }

    # Alertas de concentração.
    _CONCENTRATION_THRESHOLD = 5.0
    concentration_alerts = [
        {
            "symbol": row["symbol"],
            "name": row["name"],
            "weight": row["weight"],
            "is_technical_code": row["is_technical_code"],
        }
        for row in position_rows
        if row["weight"] > _CONCENTRATION_THRESHOLD
    ][:5]

    # Resumo dinâmico (não hardcoda instituições).
    summary = {
        "total_positions": len(position_rows),
        "institution_count": len(institution_order),
        "institution_weights": {
            name: (institution_totals[name] / total_value * 100) if total_value else 0.0
            for name in institution_order
        },
    }

    contribution_analysis = _compute_contribution_analysis(by_asset_class, liquidity)
    next_action = _generate_next_action(position_rows, liquidity)

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
            "next_action": next_action,
        },
        "summary": summary,
        "by_asset_class": by_asset_class,
        "liquidity": liquidity,
        "concentration_alerts": concentration_alerts,
        "contribution_analysis": contribution_analysis,
        "totals": totals,
        "top_positions": top_positions,
    }
