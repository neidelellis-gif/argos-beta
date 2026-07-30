"""Deterministic assessment of structured market sources against canonical positions."""

from collections.abc import Iterable, Mapping
from hashlib import sha256
import re
import unicodedata

from backend.models import PortfolioPosition


FIELDS = (
    "id", "source_type", "source_id", "impact_level", "impact_direction",
    "confidence", "title", "summary", "affected_positions", "affected_assets",
    "impact_factors", "related_facts", "related_events",
)
RELATIONSHIPS = (
    "DIRECT_ASSET", "ASSET_NAME", "INSTITUTION", "SECTOR", "ASSET_CLASS",
    "CURRENCY", "MARKET", "COUNTRY",
)
_LEVEL = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_SOURCE = {"FACT": 0, "MARKET_EVENT": 1}
_DIRECTIONS = {"POSITIVE", "NEGATIVE", "MIXED", "UNCERTAIN"}
_RECOMMENDATION = re.compile(
    r"\b(comprar|vender|aumentar posi[cç][aã]o|reduzir posi[cç][aã]o|refor[cç]ar "
    r"posi[cç][aã]o|liquidar|entrar no ativo|sair do ativo|buy|sell|increase "
    r"position|reduce position|strong buy|strong sell)\b", re.IGNORECASE,
)


def _normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""
    plain = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


def _values(source: Mapping[str, object], *names: str) -> tuple[str, ...]:
    result: list[str] = []
    for name in names:
        value = source.get(name)
        candidates = value if isinstance(value, (list, tuple)) else (value,)
        for candidate in candidates:
            normalized = _normalize(candidate)
            if normalized and normalized not in result:
                result.append(normalized)
    return tuple(result)


class PortfolioImpactAssessmentEngine:
    """Explain verifiable relationships; never forecast or recommend operations."""

    max_assessments = 5

    def generate(
        self, facts: Iterable[Mapping[str, object]],
        market_agenda: Iterable[Mapping[str, object]], positions: Iterable[PortfolioPosition],
    ) -> list[dict[str, object]]:
        fact_items, event_items, position_items = tuple(facts), tuple(market_agenda), tuple(positions)
        if any(not isinstance(item, Mapping) for item in fact_items + event_items):
            raise TypeError("facts and market_agenda accept only mapping instances")
        if any(not isinstance(item, PortfolioPosition) for item in position_items):
            raise TypeError("positions accepts only PortfolioPosition instances")
        candidates = [
            assessment for source_type, sources in (("FACT", fact_items), ("MARKET_EVENT", event_items))
            for source in sources
            if (assessment := self._assessment(source_type, source, position_items)) is not None
        ]
        selected: dict[tuple[str, str], dict[str, object]] = {}
        for item in candidates:
            key = (str(item["source_type"]), str(item["source_id"]))
            previous = selected.get(key)
            if previous is None or self._quality(item) < self._quality(previous):
                selected[key] = item
        result = list(selected.values())
        result.sort(key=lambda item: (
            _LEVEL[str(item["impact_level"])], _LEVEL[str(item["confidence"])],
            _SOURCE[str(item["source_type"])], _normalize(item["title"]), str(item["id"]),
        ))
        return result[: self.max_assessments]

    build = generate

    def _assessment(self, source_type: str, source: Mapping[str, object],
                    positions: tuple[PortfolioPosition, ...]) -> dict[str, object] | None:
        source_id = source.get("id")
        title, summary = source.get("title"), source.get("summary", source.get("description", ""))
        if not isinstance(source_id, str) or not source_id.strip() or not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(summary, str):
            return None
        if _RECOMMENDATION.search(f"{title} {summary}"):
            return None
        importance = str(source.get("priority", source.get("importance", "LOW"))).upper()
        importance = {"CRITICAL": "HIGH", "MODERATE": "MEDIUM"}.get(importance, importance)
        if importance not in _LEVEL:
            return None
        matches: list[tuple[PortfolioPosition, str, str]] = []
        for index, position in enumerate(positions):
            relation, factor = self._relationship(source, position)
            if relation:
                matches.append((position, relation, factor))
        if not matches:
            return None
        strongest = min((RELATIONSHIPS.index(match[1]) for match in matches))
        direct = strongest <= RELATIONSHIPS.index("ASSET_NAME")
        if direct:
            level = "HIGH" if importance == "HIGH" else "MEDIUM"
        elif importance == "HIGH":
            level = "MEDIUM"
        elif importance == "MEDIUM":
            level = "LOW"
        else:
            return None
        confidence = "HIGH" if strongest <= 2 else "MEDIUM" if strongest <= 6 else "LOW"
        direction = str(source.get("impact_direction", source.get("direction", "UNCERTAIN"))).upper()
        if direction not in _DIRECTIONS:
            direction = "UNCERTAIN"
        affected_positions = []
        affected_assets: list[str] = []
        factors: list[dict[str, str]] = []
        for index, (position, relation, factor) in enumerate(matches):
            identifier = position.identifier or ""
            name = position.asset_name or ""
            position_id = self._position_id(position, index)
            affected_positions.append({
                "position_id": position_id, "asset_identifier": identifier,
                "asset_name": name, "institution": position.institution,
                "relationship_type": relation,
            })
            label = identifier or name
            if label and label not in affected_assets:
                affected_assets.append(label)
            factor_item = {"factor_type": relation, "factor_value": factor,
                           "description": self._factor_description(relation, factor)}
            if factor_item not in factors:
                factors.append(factor_item)
        digest = sha256(f"{source_type}\x1f{source_id}".encode()).hexdigest()[:12]
        return dict(zip(FIELDS, (
            f"impact-{digest}", source_type, source_id, level, direction, confidence,
            title.strip(), summary.strip() or "A origem possui relação verificável com posições da carteira.",
            affected_positions, affected_assets, factors,
            [source_id] if source_type == "FACT" else [],
            [source_id] if source_type == "MARKET_EVENT" else [],
        ), strict=True))

    @staticmethod
    def _relationship(source: Mapping[str, object], position: PortfolioPosition) -> tuple[str, str]:
        comparisons = (
            ("DIRECT_ASSET", _values(source, "asset_identifiers", "related_assets", "affected_assets"), position.identifier),
            ("ASSET_NAME", _values(source, "asset_names"), position.asset_name),
            ("INSTITUTION", _values(source, "institutions", "related_institutions", "institution"), position.institution),
            ("SECTOR", _values(source, "sectors", "related_sectors"), position.asset_subclass),
            ("ASSET_CLASS", _values(source, "asset_classes"), position.asset_class),
            ("CURRENCY", _values(source, "currencies", "related_currencies"), position.currency),
            ("MARKET", _values(source, "markets"), getattr(position, "market", None)),
            ("COUNTRY", _values(source, "countries", "country"), getattr(position, "country", None)),
        )
        for relation, values, raw in comparisons:
            normalized = _normalize(raw)
            if normalized and normalized in values:
                return relation, str(raw).strip()
        return "", ""

    @staticmethod
    def _position_id(position: PortfolioPosition, index: int) -> str:
        material = "\x1f".join((position.owner.value, position.institution,
                                  position.account or "", position.identifier or "",
                                  position.asset_name or "", str(index)))
        return f"position-{sha256(material.encode()).hexdigest()[:12]}"

    @staticmethod
    def _factor_description(relation: str, value: str) -> str:
        labels = {"DIRECT_ASSET": "ativo", "ASSET_NAME": "nome do ativo", "INSTITUTION": "instituição",
                  "SECTOR": "setor", "ASSET_CLASS": "classe", "CURRENCY": "moeda",
                  "MARKET": "mercado", "COUNTRY": "país"}
        return f"A origem está relacionada ao {labels[relation]} {value} presente na carteira."

    @staticmethod
    def _quality(item: Mapping[str, object]) -> tuple[int, int, int, str]:
        positions = item["affected_positions"]
        position_items = positions if isinstance(positions, list) else []
        direct = sum(
            isinstance(position, Mapping) and position.get("relationship_type") == "DIRECT_ASSET"
            for position in position_items
        )
        return (_LEVEL[str(item["impact_level"])], _LEVEL[str(item["confidence"])], -direct, str(item["id"]))
