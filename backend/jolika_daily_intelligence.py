"""Bridge consolidated JOLIKA intelligence into the ARGOS daily flow."""

from __future__ import annotations

from dataclasses import dataclass

from backend.jolika_operational_intelligence import (
    JolikaOperationalIntelligence,
    build_jolika_operational_intelligence,
)
from backend.jolika_portfolio_intelligence import (
    JolikaPortfolioIntelligence,
    build_jolika_portfolio_intelligence,
)
from backend.models import PortfolioPosition
from backend.santander_daily_intelligence import (
    SantanderDailyIntelligence,
)
from backend.ubs_daily_intelligence import (
    UBSDailyIntelligence,
)


@dataclass(frozen=True)
class JolikaDailyIntelligence:
    """Consolidated JOLIKA intelligence built from institutional results."""

    structural: JolikaPortfolioIntelligence
    operational: JolikaOperationalIntelligence

    def to_dict(self) -> dict[str, object]:
        """Return the public consolidated JOLIKA payload."""

        structural = self.structural
        operational = self.operational

        return {
            "institution": "JOLIKA",
            "owner": structural.owner.value,
            "position_count": structural.consolidated_asset_count,
            "overall_level": operational.overall_level,
            "structural_level": operational.structural_level,
            "institutional_level": operational.institutional_level,
            "executive_reading": operational.executive_reading,
            "institutions": {
                institution: {}
                for institution in structural.institutions
            },
        }


class JolikaDailyIntelligenceService:
    """Build consolidated JOLIKA intelligence from completed bank intelligence."""

    def build(
        self,
        positions: tuple[PortfolioPosition, ...],
        *,
        ubs: UBSDailyIntelligence | None = None,
        santander: SantanderDailyIntelligence | None = None,
    ) -> JolikaDailyIntelligence | None:
        """Return JOLIKA consolidation without performing market requests."""

        institutional = tuple(
            item
            for item in (ubs, santander)
            if item is not None
        )

        if not institutional or not positions:
            return None

        structural = build_jolika_portfolio_intelligence(
            positions
        )

        operational = build_jolika_operational_intelligence(
            structural,
            tuple(
                item.operational
                for item in institutional
            ),
        )

        return JolikaDailyIntelligence(
            structural=structural,
            operational=operational,
        )
