from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass(frozen=True)
class Quote:
    """Normalized market quote returned by every ARGOS market provider."""

    ticker: str
    price: Optional[float]
    currency: Optional[str]
    provider: str
    timestamp: datetime
    status: str
    error: Optional[str] = None

    @classmethod
    def unavailable(
        cls,
        ticker: str,
        provider: str = "none",
        error: Optional[str] = None,
    ) -> "Quote":
        return cls(
            ticker=ticker.upper().strip(),
            price=None,
            currency=None,
            provider=provider,
            timestamp=datetime.now(timezone.utc),
            status="unavailable",
            error=error,
        )

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

@dataclass(frozen=True)
class MarketIntelligence:
    """Resposta consolidada da Camada de Inteligência de Mercado do ARGOS."""

    quote: Quote
    confidence: float
    sources_consulted: int
    sources_confirmed: int
    quality_status: str
    decision_note: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "quote": self.quote.to_dict(),
            "confidence": self.confidence,
            "sources_consulted": self.sources_consulted,
            "sources_confirmed": self.sources_confirmed,
            "quality_status": self.quality_status,
            "decision_note": self.decision_note,
        }
