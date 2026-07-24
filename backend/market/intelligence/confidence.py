from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceResult:
    score: float
    status: str
    decision_note: str


class ConfidenceEvaluator:
    """Avalia a confiança da inteligência de mercado."""

    def evaluate(
        self,
        *,
        sources_consulted: int,
        sources_confirmed: int,
    ) -> ConfidenceResult:
        if sources_consulted <= 0:
            return ConfidenceResult(
                score=0.0,
                status="invalid",
                decision_note="Nenhuma fonte consultada.",
            )

        score = sources_confirmed / sources_consulted

        if score >= 0.80:
            status = "validated"
        elif score >= 0.50:
            status = "partial"
        else:
            status = "low"

        return ConfidenceResult(
            score=score,
            status=status,
            decision_note="Confiança calculada automaticamente.",
        )
