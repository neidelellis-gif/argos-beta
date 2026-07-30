"""Deterministic daily priorities derived exclusively from daily analyses."""

from collections.abc import Iterable, Mapping
from hashlib import sha256
import re
import unicodedata

from backend.models import PortfolioPosition


_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_TYPE_ORDER = {"DECIDE": 0, "ANALYZE": 1}
_REQUIRED_FIELDS = {
    "id", "type", "priority", "title", "summary", "related_facts",
}
_RECOMMENDATION_TERMS = re.compile(
    r"\b(comprar|vender|aumentar|reduzir|refor[cç]ar|liquidar|entrar|sair|"
    r"aplicar|resgatar|buy|sell|"
    r"increase\s+position|reduce\s+position)\b",
    re.IGNORECASE,
)


class DailyPriorityEngine:
    """Select at most two attention priorities without financial recommendations."""

    max_priorities = 2

    def generate(
        self,
        analyses: Iterable[Mapping[str, object]],
        positions: Iterable[PortfolioPosition],
    ) -> list[dict[str, object]]:
        """Return priorities based only on valid, immutable analysis inputs."""
        analysis_items = tuple(analyses)
        position_items = tuple(positions)
        if any(not isinstance(item, PortfolioPosition) for item in position_items):
            raise TypeError("positions accepts only PortfolioPosition instances")

        validated = self._validated(analysis_items)
        groups = self._groups(validated)
        candidates = [self._priority(group) for group in groups]
        deduplicated = self._deduplicate(candidates)
        deduplicated.sort(key=self._sort_key)
        return deduplicated[: self.max_priorities]

    build = generate

    @classmethod
    def _validated(
        cls, analyses: tuple[Mapping[str, object], ...]
    ) -> tuple[dict[str, object], ...]:
        valid: list[dict[str, object]] = []
        for analysis in analyses:
            if not isinstance(analysis, Mapping) or not _REQUIRED_FIELDS.issubset(analysis):
                continue
            identifier = analysis["id"]
            kind = analysis["type"]
            received_priority = analysis["priority"]
            title = analysis["title"]
            summary = analysis["summary"]
            related_facts = analysis["related_facts"]
            if any(
                not isinstance(value, str) or not value.strip()
                for value in (identifier, title, summary)
            ):
                continue
            if kind not in _TYPE_ORDER or not isinstance(received_priority, str):
                continue
            priority = "HIGH" if received_priority == "CRITICAL" else received_priority
            if priority not in _PRIORITY_ORDER:
                continue
            if _RECOMMENDATION_TERMS.search(f"{title} {summary}"):
                continue
            facts = cls._strings(related_facts)
            if facts is None or not facts:
                continue
            assets = cls._strings(analysis.get("affected_assets", ()))
            if assets is None:
                continue
            valid.append({
                "id": identifier,
                "type": kind,
                "priority": priority,
                "title": title,
                "summary": summary,
                "related_facts": facts,
                "affected_assets": assets,
            })
        valid.sort(key=cls._sort_key)
        return tuple(valid)

    @classmethod
    def _groups(
        cls, analyses: tuple[dict[str, object], ...]
    ) -> tuple[tuple[dict[str, object], ...], ...]:
        remaining = list(analyses)
        groups: list[tuple[dict[str, object], ...]] = []
        while remaining:
            group = [remaining.pop(0)]
            assets = set(cls._assets(group[0]))
            changed = True
            while changed:
                changed = False
                for item in tuple(remaining):
                    item_assets = set(cls._assets(item))
                    if assets and item_assets and assets & item_assets:
                        group.append(item)
                        remaining.remove(item)
                        assets.update(item_assets)
                        changed = True
            groups.append(tuple(group))
        return tuple(groups)

    @classmethod
    def _priority(cls, analyses: tuple[dict[str, object], ...]) -> dict[str, object]:
        ordered = sorted(analyses, key=cls._sort_key)
        related = [str(item["id"]) for item in ordered]
        assets = sorted(
            {asset for item in ordered for asset in cls._assets(item)},
            key=lambda value: (value.casefold(), value),
        )
        lead = ordered[0]
        digest = sha256("\x1f".join(related).encode()).hexdigest()[:12]
        attention = "decisão a ser examinada" if lead["type"] == "DECIDE" else "análise e acompanhamento"
        asset_text = ", ".join(assets) if assets else "os ativos indicados na análise"
        summary = (
            f"A prioridade deriva de {', '.join(related)}, envolve {asset_text} e requer "
            f"{attention}."
        )
        return {
            "id": f"priority-{digest}",
            "type": lead["type"],
            "priority": lead["priority"],
            "title": str(lead["title"]),
            "summary": summary,
            "related_analyses": related,
            "affected_assets": assets,
        }

    @classmethod
    def _deduplicate(
        cls, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        candidates.sort(key=cls._sort_key)
        kept: list[dict[str, object]] = []
        for item in candidates:
            duplicate = any(
                cls._normalize(str(item["id"])) == cls._normalize(str(other["id"]))
                or cls._normalize(str(item["title"])) == cls._normalize(str(other["title"]))
                or (
                    item["type"] == other["type"]
                    and cls._related_set(item) == cls._related_set(other)
                )
                for other in kept
            )
            if not duplicate:
                kept.append(item)
        return kept

    @staticmethod
    def _strings(value: object) -> tuple[str, ...] | None:
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            return None
        items = tuple(value)
        if any(not isinstance(item, str) or not item.strip() for item in items):
            return None
        return tuple(dict.fromkeys(items))

    @staticmethod
    def _assets(item: Mapping[str, object]) -> tuple[str, ...]:
        value = item["affected_assets"]
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return ()
        return tuple(str(asset) for asset in value)

    @staticmethod
    def _related_set(item: Mapping[str, object]) -> set[str]:
        value = item["related_analyses"]
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return set()
        return {str(identifier) for identifier in value}

    @classmethod
    def _sort_key(cls, item: Mapping[str, object]) -> tuple[object, ...]:
        return (
            _PRIORITY_ORDER[str(item["priority"])],
            _TYPE_ORDER[str(item["type"])],
            cls._normalize(str(item["title"])),
            str(item["id"]).casefold(),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        plain = unicodedata.normalize("NFKD", value)
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()
