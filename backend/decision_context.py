"""Canonical immutable decision profile and atomic JSON/CSV import."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

MAX_COLLECTION = 20
COLLECTION_FIELDS = (
    "primary_objectives", "secondary_objectives", "restricted_assets",
    "restricted_asset_classes", "restricted_sectors", "restricted_currencies",
    "preferred_markets",
)
CSV_FIELDS = (
    "profile_id", "profile_name", "portfolio_scope", "risk_level",
    "investment_horizon", "primary_objectives", "secondary_objectives",
    "liquidity_needs", "capital_preservation_level", "volatility_tolerance",
    "concentration_tolerance", "restricted_assets", "restricted_asset_classes",
    "restricted_sectors", "restricted_currencies", "preferred_markets",
    "base_currency", "decision_frequency", "review_date", "source_name",
    "source_reference", "notes",
)
_SAFE_TEXT = re.compile(r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$")
_SAFE_ID = re.compile(r"^[\w.:/@+\- ]+$", re.UNICODE)
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class PortfolioScope(str, Enum):
    PERSONAL = "PERSONAL"
    COMPANY = "COMPANY"
    CONSOLIDATED = "CONSOLIDATED"


class DeclaredLevel(str, Enum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class InvestmentHorizon(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    SHORT_TERM = "SHORT_TERM"
    MEDIUM_TERM = "MEDIUM_TERM"
    LONG_TERM = "LONG_TERM"
    MULTI_HORIZON = "MULTI_HORIZON"


class Objective(str, Enum):
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    INCOME = "INCOME"
    CAPITAL_GROWTH = "CAPITAL_GROWTH"
    LIQUIDITY = "LIQUIDITY"
    DIVERSIFICATION = "DIVERSIFICATION"
    INFLATION_PROTECTION = "INFLATION_PROTECTION"
    CURRENCY_PROTECTION = "CURRENCY_PROTECTION"
    TACTICAL_RETURN = "TACTICAL_RETURN"
    LONG_TERM_WEALTH = "LONG_TERM_WEALTH"
    SUCCESSION = "SUCCESSION"
    SPECULATIVE_GROWTH = "SPECULATIVE_GROWTH"


class CapitalPreservationLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    EVENT_DRIVEN = "EVENT_DRIVEN"


@dataclass(frozen=True)
class DecisionProfile:
    profile_id: str
    profile_name: str
    portfolio_scope: PortfolioScope
    risk_level: DeclaredLevel
    investment_horizon: InvestmentHorizon
    primary_objectives: tuple[Objective, ...]
    secondary_objectives: tuple[Objective, ...]
    liquidity_needs: DeclaredLevel
    capital_preservation_level: CapitalPreservationLevel
    volatility_tolerance: DeclaredLevel
    concentration_tolerance: DeclaredLevel
    restricted_assets: tuple[str, ...]
    restricted_asset_classes: tuple[str, ...]
    restricted_sectors: tuple[str, ...]
    restricted_currencies: tuple[str, ...]
    preferred_markets: tuple[str, ...]
    base_currency: str
    decision_frequency: DecisionFrequency
    review_date: date
    source_name: str
    source_reference: str
    notes: str


class DecisionContextValidationError(ValueError):
    """Raised when a profile cannot be accepted atomically."""


def _text(value: Any, field: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise DecisionContextValidationError(f"O campo {field} deve ser texto.")
    result = value.strip()
    if required and not result:
        raise DecisionContextValidationError(f"O campo {field} é obrigatório.")
    if len(result) > maximum or not _SAFE_TEXT.fullmatch(result):
        raise DecisionContextValidationError(f"O campo {field} é inválido ou excessivo.")
    return result


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    if value == "MEDIUM" and enum_type is DeclaredLevel:
        value = "MODERATE"
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise DecisionContextValidationError(f"O campo {field} possui valor inválido.") from error


def _collection(value: Any, field: str, enum_type: type[Enum] | None = None) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise DecisionContextValidationError(f"O campo {field} deve ser uma coleção.")
    if len(value) > MAX_COLLECTION:
        raise DecisionContextValidationError(f"O campo {field} excede {MAX_COLLECTION} itens.")
    result: list[Any] = []
    keys: set[str] = set()
    for raw in value:
        item = _enum(enum_type, raw, field) if enum_type else _text(raw, field, 200)
        rendered = item.value if isinstance(item, Enum) else item
        if not _SAFE_ID.fullmatch(rendered):
            raise DecisionContextValidationError(f"O campo {field} contém identificador inválido.")
        key = " ".join(rendered.casefold().split())
        if key in keys:
            raise DecisionContextValidationError(f"O campo {field} contém itens duplicados.")
        keys.add(key)
        result.append(item)
    return tuple(result)


def validate_decision_profile(data: Any) -> DecisionProfile:
    if not isinstance(data, dict):
        raise DecisionContextValidationError("O perfil deve ser um objeto.")
    missing, unknown = set(CSV_FIELDS) - set(data), set(data) - set(CSV_FIELDS)
    if missing:
        raise DecisionContextValidationError(f"O campo {min(missing)} é obrigatório.")
    if unknown:
        raise DecisionContextValidationError(f"Campo desconhecido: {min(unknown)}.")
    profile_id = _text(data["profile_id"], "profile_id", 100)
    if not _SAFE_ID.fullmatch(profile_id):
        raise DecisionContextValidationError("O campo profile_id é inválido.")
    currency = _text(data["base_currency"], "base_currency", 3).upper()
    if not _CURRENCY.fullmatch(currency):
        raise DecisionContextValidationError("A moeda-base deve usar um código ISO de três letras.")
    try:
        raw_date = data["review_date"]
        if not isinstance(raw_date, str) or len(raw_date) != 10:
            raise ValueError
        review_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise DecisionContextValidationError("A data de revisão é inválida.") from error
    primary = _collection(data["primary_objectives"], "primary_objectives", Objective)
    secondary = _collection(data["secondary_objectives"], "secondary_objectives", Objective)
    if set(primary) & set(secondary):
        raise DecisionContextValidationError("Objetivos primários e secundários não podem se repetir.")
    return DecisionProfile(
        profile_id, _text(data["profile_name"], "profile_name", 200),
        _enum(PortfolioScope, data["portfolio_scope"], "portfolio_scope"),
        _enum(DeclaredLevel, data["risk_level"], "risk_level"),
        _enum(InvestmentHorizon, data["investment_horizon"], "investment_horizon"),
        primary, secondary, _enum(DeclaredLevel, data["liquidity_needs"], "liquidity_needs"),
        _enum(CapitalPreservationLevel, data["capital_preservation_level"], "capital_preservation_level"),
        _enum(DeclaredLevel, data["volatility_tolerance"], "volatility_tolerance"),
        _enum(DeclaredLevel, data["concentration_tolerance"], "concentration_tolerance"),
        _collection(data["restricted_assets"], "restricted_assets"),
        _collection(data["restricted_asset_classes"], "restricted_asset_classes"),
        _collection(data["restricted_sectors"], "restricted_sectors"),
        _collection(data["restricted_currencies"], "restricted_currencies"),
        _collection(data["preferred_markets"], "preferred_markets"), currency,
        _enum(DecisionFrequency, data["decision_frequency"], "decision_frequency"), review_date,
        _text(data["source_name"], "source_name", 200),
        _text(data["source_reference"], "source_reference", 500),
        _text(data["notes"], "notes", 2000, required=False),
    )


def import_decision_profile(file_name: str, content: bytes) -> DecisionProfile:
    if not content:
        raise DecisionContextValidationError("O arquivo de contexto decisório está vazio.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DecisionContextValidationError("O arquivo deve utilizar UTF-8.") from error
    try:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".json":
            payload = json.loads(decoded)
            if not isinstance(payload, dict) or set(payload) != {"profile"}:
                raise DecisionContextValidationError("JSON deve conter somente o objeto profile.")
            row = payload["profile"]
        elif suffix == ".csv":
            reader = csv.DictReader(io.StringIO(decoded))
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise DecisionContextValidationError("Os cabeçalhos CSV não correspondem ao contrato oficial.")
            rows = list(reader)
            if len(rows) != 1:
                raise DecisionContextValidationError("O CSV deve conter exatamente um perfil.")
            row = rows[0]
            for field in COLLECTION_FIELDS:
                row[field] = [] if not row[field] else row[field].split("|")
        else:
            raise DecisionContextValidationError("Envie um arquivo JSON ou CSV.")
    except (json.JSONDecodeError, csv.Error) as error:
        raise DecisionContextValidationError("O arquivo de contexto decisório é inválido.") from error
    return validate_decision_profile(row)
