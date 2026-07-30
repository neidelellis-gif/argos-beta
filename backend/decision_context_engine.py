"""Deterministic contextual relevance engine without financial recommendations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import date
from enum import Enum
from typing import Any

from backend.decision_context import DecisionProfile

FIELDS = (
    "id", "context_type", "relevance_level", "title", "summary", "related_assets",
    "related_facts", "related_events", "related_impacts", "related_analyses",
    "related_priorities", "context_factors", "limitations",
)
TYPE_ORDER = (
    "CONTEXT_CONFLICT", "RESTRICTION_CONTEXT", "RISK_ALIGNMENT",
    "PRESERVATION_CONTEXT", "HORIZON_ALIGNMENT", "OBJECTIVE_ALIGNMENT",
    "LIQUIDITY_CONTEXT", "VOLATILITY_CONTEXT", "CONCENTRATION_CONTEXT",
    "CURRENCY_CONTEXT", "MARKET_PREFERENCE", "DECISION_FREQUENCY",
)
FORBIDDEN = re.compile(
    r"\b(comprar|vender|reforçar|liquidar|entrar|sair|buy|sell|strong buy|strong sell|"
    r"aumentar posição|reduzir posição|increase position|reduce position)\b", re.I,
)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _id(item: Any) -> str:
    return str(_value(item, "id", _value(item, "event_id", _value(item, "fact_id", ""))))


def _norm(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    return " ".join(str(value).casefold().split())


def _values(item: Any, *names: str) -> set[str]:
    result: set[str] = set()
    for name in names:
        raw = _value(item, name, ())
        if isinstance(raw, str):
            raw = (raw,)
        if isinstance(raw, Iterable):
            result.update(_norm(value) for value in raw if value is not None and _norm(value))
    return result


def _factor(kind: str, value: str, description: str) -> dict[str, str]:
    return {"factor_type": kind, "factor_value": value, "description": description}


def _profile_value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value)


class DecisionContextEngine:
    """Explain relevance using only declared profile and structured relations."""

    def generate(
        self, profile: DecisionProfile | None, facts: Iterable[Any] = (),
        market_agenda: Iterable[Any] = (), impact_assessments: Iterable[Any] = (),
        analyses: Iterable[Any] = (), priorities: Iterable[Any] = (),
        positions: Iterable[Any] = (), reference_date: date | None = None,
    ) -> tuple[dict[str, object], ...]:
        if profile is None:
            return ()
        facts, events, impacts = tuple(facts), tuple(market_agenda), tuple(impact_assessments)
        analyses, priorities, positions = tuple(analyses), tuple(priorities), tuple(positions)
        sources = facts + events + impacts
        contexts: list[dict[str, object]] = []

        high_impacts = tuple(item for item in impacts if _value(item, "impact_level") == "HIGH")
        if high_impacts:
            contexts.append(self._context(
                "RISK_ALIGNMENT", "HIGH", "Impacto e perfil de risco",
                "Impactos de alta relevância estão relacionados ao nível de risco declarado no perfil.",
                profile, high_impacts, facts, events, impacts, analyses, priorities,
                [_factor("RISK_LEVEL", profile.risk_level.value,
                         f"O perfil declara nível de risco {profile.risk_level.value.lower().replace('_', ' ')}.")],
                ["A direção do impacto permanece incerta."] if any(_value(i, "impact_direction") == "UNCERTAIN" for i in high_impacts) else [],
            ))
        if profile.capital_preservation_level.value in {"HIGH", "CRITICAL"} and high_impacts:
            relevant = tuple(i for i in high_impacts if _value(i, "impact_direction") in {"NEGATIVE", "UNCERTAIN"})
            if relevant:
                contexts.append(self._context(
                    "CONTEXT_CONFLICT" if profile.capital_preservation_level.value == "CRITICAL" else "PRESERVATION_CONTEXT",
                    "HIGH", "Preservação e impacto relevante",
                    "O impacto negativo ou incerto possui relevância diante da preservação de capital declarada.",
                    profile, relevant, facts, events, impacts, analyses, priorities,
                    [_factor("CAPITAL_PRESERVATION", profile.capital_preservation_level.value,
                             "O perfil declara preservação de capital elevada.")],
                    ["A direção do impacto permanece incerta."] if any(_value(i, "impact_direction") == "UNCERTAIN" for i in relevant) else [],
                ))

        dated = tuple(event for event in events if reference_date and isinstance(_value(event, "event_date"), (date, str))
                      and self._within_horizon(profile.investment_horizon.value, reference_date, _value(event, "event_date")))
        if dated:
            level = "HIGH" if profile.investment_horizon.value in {"IMMEDIATE", "SHORT_TERM"} else "MEDIUM"
            contexts.append(self._context(
                "HORIZON_ALIGNMENT", level, "Evento dentro do horizonte declarado",
                "Este evento ocorre dentro do horizonte explicitamente definido para a carteira.",
                profile, dated, facts, events, impacts, analyses, priorities,
                [_factor("INVESTMENT_HORIZON", profile.investment_horizon.value,
                         "O perfil possui horizonte de investimento declarado.")], [],
            ))

        objective_rules = {
            "INCOME": {"DIVIDEND"}, "INFLATION_PROTECTION": {"INFLATION"},
            "CURRENCY_PROTECTION": {"CURRENCY", "FX", "EXCHANGE_RATE"},
        }
        declared_objectives = (
            tuple((objective.value, True) for objective in profile.primary_objectives)
            + tuple((objective.value, False) for objective in profile.secondary_objectives)
        )
        for objective, primary in declared_objectives:
            matched = tuple(item for item in sources if objective_rules.get(objective, set()) & self._markers(item))
            if matched:
                contexts.append(self._context(
                    "OBJECTIVE_ALIGNMENT", "HIGH" if primary else "MEDIUM",
                    "Informação relacionada a objetivo declarado",
                    "A informação possui relevância para um objetivo declarado no perfil.", profile,
                    matched, facts, events, impacts, analyses, priorities,
                    [_factor("PRIMARY_OBJECTIVE" if primary else "SECONDARY_OBJECTIVE", objective,
                             "A associação utiliza uma regra explícita de objetivo.")], [],
                ))

        contexts.extend(self._restriction_contexts(profile, sources, facts, events, impacts, analyses, priorities))
        contexts.extend(self._position_contexts(profile, sources, positions, facts, events, impacts, analyses, priorities))

        volatility = tuple(item for item in sources if self._markers(item) & {"VOLATILITY", "VOLATILE"})
        if volatility:
            contexts.append(self._context(
                "VOLATILITY_CONTEXT", "MEDIUM", "Volatilidade declarada na informação",
                "A informação contém marcador estruturado de volatilidade relacionado à tolerância declarada.",
                profile, volatility, facts, events, impacts, analyses, priorities,
                [_factor("VOLATILITY_TOLERANCE", profile.volatility_tolerance.value,
                         "A tolerância à volatilidade é uma preferência declarada.")], [],
            ))

        if profile.liquidity_needs.value == "VERY_HIGH":
            illiquid = tuple(item for item in sources if self._markers(item) & {"ILLIQUID", "ILLIQUIDITY"})
            if illiquid:
                contexts.append(self._context(
                    "CONTEXT_CONFLICT", "HIGH", "Liquidez declarada e ativo ilíquido",
                    "A necessidade de liquidez declarada está relacionada a uma marcação explícita de iliquidez.",
                    profile, illiquid, facts, events, impacts, analyses, priorities,
                    [_factor("LIQUIDITY_NEED", "VERY_HIGH", "O perfil declara necessidade de liquidez muito alta.")],
                    ["A liquidez real da carteira não foi calculada."],
                ))

        unique: dict[tuple[Any, ...], dict[str, object]] = {}
        for context in contexts:
            if any(FORBIDDEN.search(str(context[field])) for field in ("title", "summary")):
                continue
            def relation_key(field: str) -> tuple[object, ...]:
                value = context[field]
                return tuple(value) if isinstance(value, list) else ()

            key = (context["context_type"], *(relation_key(field) for field in (
                "related_facts", "related_events", "related_impacts", "related_analyses", "related_priorities")))
            previous = unique.get(key)
            if previous is None or self._sort_key(context) < self._sort_key(previous):
                unique[key] = context
        return tuple(sorted(unique.values(), key=self._sort_key)[:5])

    @staticmethod
    def _within_horizon(horizon: str, reference: date, raw: Any) -> bool:
        try:
            event_date = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        except ValueError:
            return False
        days = (event_date - reference).days
        limits = {"IMMEDIATE": 30, "SHORT_TERM": 365, "MEDIUM_TERM": 1825, "LONG_TERM": 36500}
        return 0 <= days <= limits.get(horizon, 36500)

    @staticmethod
    def _markers(item: Any) -> set[str]:
        markers = _values(item, "event_type", "category", "markers", "tags", "impact_factors")
        factors = _value(item, "impact_factors", ())
        if isinstance(factors, Iterable) and not isinstance(factors, (str, bytes)):
            for factor in factors:
                markers |= {_norm(_value(factor, "factor_type", "")), _norm(_value(factor, "factor_value", ""))}
        return {marker.upper() for marker in markers}

    def _restriction_contexts(
        self, profile: DecisionProfile, sources: tuple[Any, ...], facts: tuple[Any, ...],
        events: tuple[Any, ...], impacts: tuple[Any, ...], analyses: tuple[Any, ...],
        priorities: tuple[Any, ...],
    ) -> list[dict[str, object]]:
        result = []
        rules = (
            (profile.restricted_assets, ("affected_assets", "related_assets", "asset_identifiers", "asset_names"), "ativo"),
            (profile.restricted_asset_classes, ("asset_classes", "related_asset_classes"), "classe"),
            (profile.restricted_sectors, ("sectors", "related_sectors"), "setor"),
            (profile.restricted_currencies, ("currencies", "related_currencies"), "moeda"),
        )
        for restricted, names, label in rules:
            declared = {_norm(value) for value in restricted}
            matched = tuple(item for item in sources if declared & _values(item, *names))
            if matched:
                result.append(self._context(
                    "RESTRICTION_CONTEXT", "HIGH", f"Relação com restrição de {label}",
                    f"A informação está relacionada a {label} incluído nas restrições declaradas do perfil.",
                    profile, matched, facts, events, impacts, analyses, priorities,
                    [_factor("RESTRICTION", "|".join(sorted(restricted)), "A restrição foi declarada explicitamente.")], [],
                ))
        return result

    def _position_contexts(
        self, profile: DecisionProfile, sources: tuple[Any, ...], positions: tuple[Any, ...],
        facts: tuple[Any, ...], events: tuple[Any, ...], impacts: tuple[Any, ...],
        analyses: tuple[Any, ...], priorities: tuple[Any, ...],
    ) -> list[dict[str, object]]:
        result = []
        related_assets = set().union(*(_values(item, "affected_assets", "related_assets", "asset_identifiers", "asset_names") for item in sources)) if sources else set()
        related = tuple(p for p in positions if related_assets & _values(p, "identifier", "asset_name"))
        if len(related) >= 2:
            result.append(self._context(
                "CONCENTRATION_CONTEXT", "MEDIUM", "Múltiplas posições relacionadas",
                "A informação está relacionada a múltiplas posições; nenhum percentual de concentração foi calculado.",
                profile, sources, facts, events, impacts, analyses, priorities,
                [_factor("CONCENTRATION_TOLERANCE", profile.concentration_tolerance.value,
                         "A tolerância à concentração é uma preferência declarada.")],
                ["A exposição quantitativa não foi calculada."],
            ))
        currencies = {_norm(_value(p, "currency", "")) for p in related}
        if _norm(profile.base_currency) in currencies:
            result.append(self._context(
                "CURRENCY_CONTEXT", "MEDIUM", "Relação com a moeda-base",
                "A exposição relacionada utiliza a moeda-base declarada no perfil.", profile, sources,
                facts, events, impacts, analyses, priorities,
                [_factor("BASE_CURRENCY", profile.base_currency, "A moeda-base foi declarada no perfil.")], [],
            ))
        markets = set().union(*(_values(item, "markets", "market") for item in sources)) if sources else set()
        preferred = {_norm(value) for value in profile.preferred_markets}
        if markets & preferred:
            result.append(self._context(
                "MARKET_PREFERENCE", "MEDIUM", "Relação com mercado preferencial",
                "A informação está relacionada a um mercado preferencial declarado.", profile, sources,
                facts, events, impacts, analyses, priorities,
                [_factor("PREFERRED_MARKET", "|".join(sorted(profile.preferred_markets)),
                         "O mercado foi declarado como preferência contextual.")], [],
            ))
        return result

    def _context(self, kind: str, relevance: str, title: str, summary: str,
                 profile: DecisionProfile, matched: tuple[Any, ...], facts: tuple[Any, ...],
                 events: tuple[Any, ...], impacts: tuple[Any, ...], analyses: tuple[Any, ...],
                 priorities: tuple[Any, ...], factors: list[dict[str, str]], limitations: list[str]) -> dict[str, object]:
        matched_ids = {_id(item) for item in matched}
        def relation(items: tuple[Any, ...]) -> list[str]:
            return sorted({_id(item) for item in items if _id(item) in matched_ids})
        assets = sorted(set().union(*(_values(item, "affected_assets", "related_assets", "asset_identifiers", "asset_names") for item in matched)) if matched else set())
        digest = hashlib.sha256((profile.profile_id + kind + "|".join(sorted(matched_ids))).encode()).hexdigest()[:12]
        context: dict[str, object] = {
            "id": f"context-{digest}", "context_type": kind, "relevance_level": relevance,
            "title": title, "summary": summary, "related_assets": assets,
            "related_facts": relation(facts), "related_events": relation(events),
            "related_impacts": relation(impacts), "related_analyses": relation(analyses),
            "related_priorities": relation(priorities), "context_factors": factors,
            "limitations": limitations,
        }
        assert tuple(context) == FIELDS
        return context

    @staticmethod
    def _sort_key(item: dict[str, object]) -> tuple[Any, ...]:
        relevance = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(str(item["relevance_level"]), 3)
        kind = TYPE_ORDER.index(str(item["context_type"]))
        direct = 0
        for field in ("related_facts", "related_events", "related_impacts", "related_analyses", "related_priorities"):
            value = item[field]
            if isinstance(value, list):
                direct += len(value)
        return relevance, kind, -direct, _norm(item["title"]), item["id"]
