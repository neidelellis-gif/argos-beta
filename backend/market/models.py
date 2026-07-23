from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
