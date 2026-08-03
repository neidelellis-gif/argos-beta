"""Load and validate the versioned official portfolio repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

from backend.models import PortfolioOwner, PortfolioPosition


DEFAULT_PORTFOLIO_ROOT = Path(__file__).resolve().parent.parent / "data" / "portfolios"
_PORTFOLIO_FIELDS = {
    "portfolio_id", "portfolio_name", "portfolio_type", "base_currency",
    "institution", "reference_date", "origin", "positions",
}
_POSITION_FIELDS = {
    "account", "asset_class", "asset_subclass", "asset_name", "identifier",
    "identifier_type", "quantity", "unit_price", "market_value", "currency",
    "portfolio_weight",
}


class OfficialPortfolioValidationError(ValueError):
    """Validation failure using identifiers shared with DataQualityEngine."""

    def __init__(self, diagnostic_id: str, message: str, affected_items: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.diagnostic_id = diagnostic_id
        self.affected_items = affected_items


@dataclass(frozen=True)
class OfficialPortfolio:
    portfolio_id: str
    portfolio_name: str
    portfolio_type: str
    base_currency: str
    institution: str
    reference_date: date
    origin: str
    positions: tuple[PortfolioPosition, ...]


class OfficialPortfolioLoader:
    """Locate and translate official files without analysing or changing them."""

    def __init__(self, root: Path = DEFAULT_PORTFOLIO_ROOT) -> None:
        self.root = Path(root)

    def load_all(self) -> tuple[OfficialPortfolio, ...]:
        files = tuple(sorted(self.root.glob("*/*.json")))
        if not files:
            raise OfficialPortfolioValidationError(
                "portfolio.missing", "Nenhuma carteira oficial foi encontrada."
            )
        portfolios = tuple(self.load(path) for path in files)
        identifiers: dict[str, int] = {}
        for portfolio in portfolios:
            identifiers[portfolio.portfolio_id] = identifiers.get(portfolio.portfolio_id, 0) + 1
        duplicates = tuple(key for key, count in identifiers.items() if count > 1)
        if duplicates:
            raise OfficialPortfolioValidationError(
                "portfolio.duplicates", "Há identificadores de carteira repetidos.", duplicates
            )
        return portfolios

    def load_positions(self) -> tuple[PortfolioPosition, ...]:
        return tuple(position for portfolio in self.load_all() for position in portfolio.positions)

    def load(self, path: Path) -> OfficialPortfolio:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise OfficialPortfolioValidationError(
                "portfolio.invalid", f"Arquivo de carteira oficial inválido: {Path(path).name}."
            ) from error
        if not isinstance(payload, dict) or set(payload) != _PORTFOLIO_FIELDS:
            raise OfficialPortfolioValidationError(
                "portfolio.invalid", f"Estrutura inválida na carteira {Path(path).name}."
            )
        portfolio_id = self._required(payload, "portfolio_id", "portfolio.missing_identifier")
        portfolio_name = self._required(payload, "portfolio_name", "portfolio.invalid")
        portfolio_type = self._required(payload, "portfolio_type", "portfolio.invalid")
        if portfolio_type not in {"PERSONAL", "COMPANY"}:
            raise OfficialPortfolioValidationError("portfolio.invalid", "portfolio_type deve ser PERSONAL ou COMPANY.")
        base_currency = self._required(payload, "base_currency", "portfolio.missing_currency")
        institution = self._required(payload, "institution", "portfolio.missing_institution")
        origin = self._required(payload, "origin", "portfolio.invalid")
        reference_date = self._date(payload.get("reference_date"))
        owner = PortfolioOwner.NEI if portfolio_type == "PERSONAL" else PortfolioOwner.JOLIKA
        raw_positions = payload.get("positions")
        if not isinstance(raw_positions, list) or not raw_positions:
            raise OfficialPortfolioValidationError("portfolio.missing", "A carteira oficial não contém posições.")
        positions = tuple(
            self._position(item, institution, owner, reference_date, Path(path).name)
            for item in raw_positions
        )
        identities: dict[tuple[str, str, str], int] = {}
        for position in positions:
            identity = (position.institution, position.account or "", position.identifier or "")
            identities[identity] = identities.get(identity, 0) + 1
        duplicates = tuple("/".join(item) for item, count in identities.items() if count > 1)
        if duplicates:
            raise OfficialPortfolioValidationError(
                "portfolio.duplicates", "Há posições com a mesma identidade canônica.", duplicates
            )
        return OfficialPortfolio(
            portfolio_id, portfolio_name, portfolio_type, base_currency,
            institution, reference_date, origin, positions,
        )

    @staticmethod
    def _required(payload: dict[str, Any], field: str, diagnostic_id: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OfficialPortfolioValidationError(diagnostic_id, f"O campo {field} é obrigatório.")
        return value.strip()

    @staticmethod
    def _date(value: object) -> date:
        if not isinstance(value, str):
            raise OfficialPortfolioValidationError("portfolio.invalid_date", "Data de referência inválida.")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise OfficialPortfolioValidationError("portfolio.invalid_date", "Data de referência inválida.") from error

    def _position(
        self, value: object, institution: str, owner: PortfolioOwner,
        reference_date: date, source_file: str,
    ) -> PortfolioPosition:
        if not isinstance(value, dict) or set(value) != _POSITION_FIELDS:
            raise OfficialPortfolioValidationError("portfolio.invalid", "Posição oficial inválida.")
        identifier = value.get("identifier")
        currency = value.get("currency")
        if not isinstance(identifier, str) or not identifier.strip():
            raise OfficialPortfolioValidationError("portfolio.missing_identifier", "Ativo sem identificador.")
        if not isinstance(currency, str) or not currency.strip():
            raise OfficialPortfolioValidationError("portfolio.missing_currency", "Posição sem moeda.")
        try:
            decimals = {
                field: None if value[field] is None else Decimal(str(value[field]))
                for field in ("quantity", "unit_price", "market_value", "portfolio_weight")
            }
        except (InvalidOperation, ValueError) as error:
            raise OfficialPortfolioValidationError("portfolio.invalid", "Valor numérico de posição inválido.") from error
        quantity = decimals["quantity"]
        market_value = decimals["market_value"]
        if (quantity is not None and quantity < 0) or (market_value is not None and market_value < 0):
            raise OfficialPortfolioValidationError("portfolio.invalid", "Quantidade e valor de mercado não podem ser negativos.")
        return PortfolioPosition(
            institution=institution, owner=owner,
            account=self._optional(value, "account"), asset_class=self._optional(value, "asset_class"),
            asset_subclass=self._optional(value, "asset_subclass"), asset_name=self._optional(value, "asset_name"),
            identifier=identifier.strip(), identifier_type=self._optional(value, "identifier_type"),
            quantity=decimals["quantity"], unit_price=decimals["unit_price"],
            market_value=decimals["market_value"], currency=currency.strip().upper(),
            portfolio_weight=decimals["portfolio_weight"], reference_date=reference_date,
            source_file=source_file,
        )

    @staticmethod
    def _optional(payload: dict[str, Any], field: str) -> str | None:
        value = payload.get(field)
        if value is None:
            return None
        if not isinstance(value, str):
            raise OfficialPortfolioValidationError("portfolio.invalid", f"O campo {field} é inválido.")
        return value.strip() or None
