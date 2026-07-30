"""Deterministic daily analyses derived only from portfolio-aware facts."""

from collections.abc import Iterable, Mapping
from hashlib import sha256
import re
import unicodedata

from backend.models import PortfolioPosition


_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_REQUIRED_FIELDS = {"id", "priority", "title", "summary", "affected_assets"}
_RECOMMENDATION_TERMS = re.compile(
    r"\b(comprar|vender|aumentar|reduzir|investir|desinvestir|aportar|resgatar|"
    r"recomenda(?:r|ção)|buy|sell|invest|recommend(?:ation)?)\b",
    re.IGNORECASE,
)


class DailyAnalysisEngine:
    """Group, explain, order, and limit facts without making recommendations."""

    max_analyses = 2

    def generate(
        self,
        facts: Iterable[Mapping[str, object]],
        positions: Iterable[PortfolioPosition],
        impact_assessments: Iterable[Mapping[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        """Return at most two analyses based exclusively on ``facts``."""
        fact_items = tuple(facts)
        position_items = tuple(positions)
        impact_items = tuple(impact_assessments or ())
        if any(not isinstance(impact, Mapping) for impact in impact_items):
            raise TypeError("impact_assessments accepts only mapping instances")
        if any(not isinstance(position, PortfolioPosition) for position in position_items):
            raise TypeError("positions accepts only PortfolioPosition instances")

        unique_facts = self._validated_unique_facts(fact_items)
        groups = self._groups(unique_facts)
        analyses = [self._analysis(group) for group in groups]
        impact_ids_by_fact: dict[str, list[str]] = {}
        for impact in impact_items:
            impact_id = impact.get("id")
            related = impact.get("related_facts", ())
            if isinstance(impact_id, str) and isinstance(related, (list, tuple)):
                for fact_id in related:
                    if isinstance(fact_id, str):
                        impact_ids_by_fact.setdefault(fact_id, []).append(impact_id)
        if impact_assessments is not None:
            for analysis in analyses:
                related_facts = analysis["related_facts"]
                fact_ids = related_facts if isinstance(related_facts, list) else []
                analysis["related_impacts"] = list(dict.fromkeys(
                    impact_id for fact_id in fact_ids
                    for impact_id in impact_ids_by_fact.get(str(fact_id), ())
                ))
        analyses.sort(
            key=lambda item: (
                _PRIORITY_ORDER[str(item["priority"])],
                str(item["title"]).casefold(),
                str(item["id"]),
            )
        )
        return analyses[: self.max_analyses]

    build = generate

    @classmethod
    def _validated_unique_facts(
        cls, facts: tuple[Mapping[str, object], ...]
    ) -> tuple[dict[str, object], ...]:
        validated: list[dict[str, object]] = []
        for fact in facts:
            if not isinstance(fact, Mapping):
                raise TypeError("facts accepts only mapping instances")
            if not _REQUIRED_FIELDS.issubset(fact):
                raise ValueError("fact is missing required analysis fields")
            identifier = fact["id"]
            priority = fact["priority"]
            title = fact["title"]
            summary = fact["summary"]
            assets = fact["affected_assets"]
            if any(not isinstance(value, str) or not value.strip() for value in (
                identifier, title, summary,
            )):
                raise ValueError("fact id, title, and summary must not be empty")
            if priority not in _PRIORITY_ORDER:
                raise ValueError("fact priority must be HIGH, MEDIUM, or LOW")
            if _RECOMMENDATION_TERMS.search(f"{title} {summary}"):
                continue
            if isinstance(assets, (str, bytes)) or not isinstance(assets, Iterable):
                raise TypeError("fact affected_assets must be an iterable of strings")
            asset_items = tuple(assets)
            if any(not isinstance(asset, str) or not asset.strip() for asset in asset_items):
                raise ValueError("fact affected_assets must contain non-empty strings")

            validated.append({
                "id": identifier,
                "priority": priority,
                "title": title,
                "summary": summary,
                "affected_assets": tuple(dict.fromkeys(asset_items)),
            })

        validated.sort(key=lambda fact: (
            _PRIORITY_ORDER[str(fact["priority"])],
            str(fact["title"]).casefold(),
            str(fact["id"]).casefold(),
        ))
        unique: list[dict[str, object]] = []
        remaining = list(validated)
        while remaining:
            duplicates = [remaining.pop(0)]
            ids = {cls._normalize(str(duplicates[0]["id"]))}
            titles = {cls._normalize(str(duplicates[0]["title"]))}
            changed = True
            while changed:
                changed = False
                for fact in tuple(remaining):
                    fact_id = cls._normalize(str(fact["id"]))
                    fact_title = cls._normalize(str(fact["title"]))
                    if fact_id in ids or fact_title in titles:
                        duplicates.append(fact)
                        remaining.remove(fact)
                        ids.add(fact_id)
                        titles.add(fact_title)
                        changed = True
            unique.append(duplicates[0])
        return tuple(unique)

    @classmethod
    def _groups(
        cls, facts: tuple[dict[str, object], ...]
    ) -> tuple[tuple[dict[str, object], ...], ...]:
        """Build transitive groups when facts share at least one affected asset."""
        remaining = list(facts)
        groups: list[tuple[dict[str, object], ...]] = []
        while remaining:
            group = [remaining.pop(0)]
            assets = cls._assets(group[0])
            changed = True
            while changed:
                changed = False
                for fact in tuple(remaining):
                    fact_assets = cls._assets(fact)
                    if assets and fact_assets and assets & fact_assets:
                        group.append(fact)
                        remaining.remove(fact)
                        assets.update(fact_assets)
                        changed = True
            groups.append(tuple(group))
        return tuple(groups)

    @classmethod
    def _analysis(cls, facts: tuple[dict[str, object], ...]) -> dict[str, object]:
        ordered = sorted(
            facts,
            key=lambda fact: (
                _PRIORITY_ORDER[str(fact["priority"])],
                str(fact["title"]).casefold(),
                str(fact["id"]).casefold(),
            ),
        )
        related_facts = [str(fact["id"]) for fact in ordered]
        priority = str(ordered[0]["priority"])
        assets = sorted(
            {asset for fact in ordered for asset in cls._assets(fact)},
            key=lambda value: (value.casefold(), value),
        )
        digest = sha256("\x1f".join(related_facts).encode()).hexdigest()[:12]
        if len(ordered) == 1:
            title = str(ordered[0]["title"])
            summary = f"Este fato merece atenção por afetar {cls._asset_phrase(assets)}."
        else:
            title = f"{len(ordered)} fatos relacionados sobre {cls._asset_phrase(assets)}"
            summary = (
                f"Os fatos {', '.join(related_facts)} merecem atenção conjunta porque "
                f"afetam {cls._asset_phrase(assets)}."
            )
        return {
            "id": f"analysis-{digest}",
            "type": "DECIDE" if priority == "HIGH" else "ANALYZE",
            "priority": priority,
            "title": title,
            "summary": summary,
            "related_facts": related_facts,
            "affected_assets": assets,
        }

    @staticmethod
    def _assets(fact: Mapping[str, object]) -> set[str]:
        value = fact["affected_assets"]
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return set()
        return {str(asset) for asset in value}

    @staticmethod
    def _asset_phrase(assets: list[str]) -> str:
        if not assets:
            return "a carteira"
        if len(assets) == 1:
            return assets[0]
        return ", ".join(assets[:-1]) + f" e {assets[-1]}"

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()
