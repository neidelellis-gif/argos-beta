"""Market fact aggregation and portfolio context for the ARGOS daily flow."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence, Tuple

from backend.models import PortfolioPosition

PRIORITY_LEVELS = ("Alta", "Moderada", "Baixa")
_PRIORITY_SCORE = {"Alta": 3, "Moderada": 2, "Baixa": 1}


@dataclass(frozen=True)
class MarketEvent:
    """Structured input supplied by a market source."""

    identifier: str
    title: str
    category: str
    source: str
    occurred_at: datetime
    priority: str
    summary: str
    related_assets: Tuple[str, ...] = ()
    macro_impact: bool = False


def mock_market_events(now: datetime) -> Tuple[MarketEvent, ...]:
    """Return deterministic structured mocks relative to the requested instant."""
    return (
        MarketEvent(
            "fed-rates", "Federal Reserve reforça cautela com juros",
            "Macroeconomia", "Mock Federal Reserve", now - timedelta(hours=2),
            "Alta", "Sinais de juros altos por mais tempo afetam ativos globais.",
            macro_impact=True,
        ),
        MarketEvent(
            "nvidia-chips", "NVIDIA amplia demanda por chips de IA",
            "Tecnologia", "Mock mercado de ações", now - timedelta(hours=4),
            "Moderada", "Novos pedidos sustentam a atenção sobre o setor de semicondutores.",
            ("NVDA", "NVIDIA"),
        ),
        MarketEvent(
            "ethereum-network", "Ethereum registra maior atividade na rede",
            "Criptoativos", "Mock mercado cripto", now - timedelta(hours=6),
            "Moderada", "O volume de transações do Ethereum avançou nas últimas horas.",
            ("ETH", "ETHEREUM"),
        ),
        MarketEvent(
            "global-equities", "Bolsas globais operam com volatilidade",
            "Mercados", "Mock mercados globais", now - timedelta(hours=8),
            "Baixa", "Índices alternam direção diante do cenário de juros.",
        ),
        MarketEvent(
            "oil-supply", "Petróleo reage a riscos de oferta",
            "Geopolítica", "Mock mercado de energia", now - timedelta(hours=12),
            "Baixa", "Tensões em regiões produtoras elevaram a volatilidade do petróleo.",
            ("OIL", "PETRÓLEO", "PETROLEO"),
        ),
    )


def _position_terms(position: PortfolioPosition) -> Tuple[str, ...]:
    return tuple(
        value.strip().upper()
        for value in (position.identifier, position.asset_name)
        if value and value.strip()
    )


def _matching_assets(
    event: MarketEvent,
    positions: Sequence[PortfolioPosition],
) -> Tuple[str, ...]:
    event_terms = tuple(asset.upper() for asset in event.related_assets)
    matches = []
    for position in positions:
        terms = _position_terms(position)
        if any(
            event_term == term or event_term in term or term in event_term
            for event_term in event_terms
            for term in terms
        ):
            label = position.identifier or position.asset_name
            if label and label not in matches:
                matches.append(label)
    return tuple(matches)


def _effective_priority(base_priority: str, has_portfolio_match: bool) -> str:
    if base_priority not in _PRIORITY_SCORE:
        raise ValueError(
            f"Prioridade inválida: {base_priority}. Use Alta, Moderada ou Baixa."
        )
    score = _PRIORITY_SCORE[base_priority] + int(has_portfolio_match)
    return PRIORITY_LEVELS[max(0, 3 - min(score, 3))]


class DailyContextService:
    """Build a single prioritized daily context from structured events."""

    def __init__(self, events: Optional[Iterable[MarketEvent]] = None):
        self._events = tuple(events) if events is not None else None

    def generate(
        self,
        positions: Iterable[PortfolioPosition],
        now: Optional[datetime] = None,
    ) -> Dict:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        normalized_positions = tuple(positions)
        events = self._events if self._events is not None else mock_market_events(reference)
        cutoff = reference - timedelta(hours=24)
        facts = []

        for event in events:
            occurred_at = event.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            if not cutoff <= occurred_at <= reference:
                continue
            matches = _matching_assets(event, normalized_positions)
            priority = _effective_priority(event.priority, bool(matches))
            if matches:
                context = "Relacionado à carteira: " + ", ".join(matches)
                context_type = "portfolio"
            elif event.macro_impact:
                context = (
                    "Impacto macro para as carteiras"
                    if normalized_positions
                    else "Contexto macro geral de mercado"
                )
                context_type = "macro"
            else:
                context = "Contexto geral de mercado"
                context_type = "general"
            facts.append({
                "id": event.identifier,
                "title": event.title,
                "category": event.category,
                "source": event.source,
                "occurred_at": occurred_at.isoformat(),
                "priority": priority,
                "base_priority": event.priority,
                "summary": event.summary,
                "related_assets": list(event.related_assets),
                "matched_portfolio_assets": list(matches),
                "context": context,
                "context_type": context_type,
                "_occurred_at": occurred_at,
            })

        facts.sort(
            key=lambda fact: (
                -_PRIORITY_SCORE[fact["priority"]],
                -fact["_occurred_at"].timestamp(),
            )
        )
        for fact in facts:
            fact.pop("_occurred_at")
        selected = facts[:5]
        return {
            "generated_at": reference.isoformat(),
            "lookback_hours": 24,
            "has_portfolio_context": bool(normalized_positions),
            "facts": selected,
        }
