from decimal import Decimal
from pathlib import Path

from backend.models import PortfolioOwner, PortfolioPosition
from backend.connectors.errors import (
    ConnectorFileNotFoundError,
    EmptyPortfolioError,
    UnsupportedExtensionError,
    UnrecognizedFileError,
)
from backend.connectors.io import normalize_header, parse_decimal, read_tabular_rows

DEFAULT_FILE_PATH = Path(__file__).with_name("UBS_Holdings_08_07_2026.csv")
connector_id = "ubs"
institution = "UBS"
owner = PortfolioOwner.JOLIKA
supported_extensions = frozenset({".csv", ".xls", ".xlsx"})
SUPPORTED_EXTENSIONS = supported_extensions


def classify_asset(symbol, description):
    text = str(description or "").upper()

    if "SAVINGS" in text or "SWEEP" in text:
        return "Caixa"
    if "MATURES" in text or "CALLABLE" in text or "RATE" in text or "NTS" in text:
        return "Renda Fixa"
    if "ETF" in text:
        return "ETF"
    if "FUND" in text:
        return "Fundo"
    if symbol and symbol != "N/A":
        return "Ação"
    return "Outros"


def get_display_name(symbol, description):
    return symbol if symbol and symbol != "N/A" else description


def _normalize_header(value):
    return normalize_header(value)


def _parse_number(value):
    number = parse_decimal(value)
    return float(number) if number is not None else None


def _read_rows(path: Path):
    return read_tabular_rows(path, institution=institution, extensions=supported_extensions)


def _find_header_row(rows):
    required = {"ACCOUNT NUMBER", "DESCRIPTION", "SYMBOL"}

    for index, row in enumerate(rows):
        normalized = {_normalize_header(value) for value in row}
        if required.issubset(normalized):
            value_candidates = [
                "VALUE",
                "ACCOUNT VALUE",
                "MARKET VALUE",
                "AMOUNT",
                "BALANCE",
                "TOTAL VALUE",
            ]
            for candidate in value_candidates:
                if candidate in normalized:
                    return index

    raise UnrecognizedFileError(
        "Não encontrei os cabeçalhos esperados no arquivo UBS."
    )


def _to_portfolio_position(position, source_file):
    """Converte uma posição lida da UBS para o MPU."""
    identifier = position.get("symbol")
    if not identifier or identifier == "N/A":
        identifier = None

    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=position.get("account") or None,
        asset_class=position["asset_class"],
        asset_subclass=None,
        asset_name=position["name"],
        identifier=identifier,
        identifier_type=None,
        quantity=None,
        unit_price=None,
        market_value=Decimal(str(position["value"])),
        currency=position["currency"],
        portfolio_weight=(
            Decimal(str(position["weight"]))
            if position.get("weight") is not None
            else None
        ),
        reference_date=None,
        source_file=source_file,
    )


def recognize(path: Path) -> bool:
    path = Path(path)
    if path.suffix.lower() not in supported_extensions or not path.exists():
        return False
    try:
        _find_header_row(_read_rows(path))
    except (OSError, ValueError):
        return False
    return True


def load_positions(file_path: Path) -> tuple[PortfolioPosition, ...]:
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedExtensionError(
            "O arquivo UBS deve estar em CSV, XLS ou XLSX."
        )
    if not path.exists():
        raise ConnectorFileNotFoundError(
            f"Arquivo UBS não encontrado: {path.name}"
        )

    rows = _read_rows(path)
    header_index = _find_header_row(rows)
    header = [_normalize_header(value) for value in rows[header_index]]

    account_idx = header.index("ACCOUNT NUMBER")
    description_idx = header.index("DESCRIPTION")
    symbol_idx = header.index("SYMBOL")

    value_idx = None
    for candidate in ["VALUE", "ACCOUNT VALUE", "MARKET VALUE", "AMOUNT", "BALANCE", "TOTAL VALUE"]:
        if candidate in header:
            value_idx = header.index(candidate)
            break

    if value_idx is None:
        raise ValueError("Não encontrei a coluna de valor no arquivo UBS.")

    positions = []

    for row in rows[header_index + 1 :]:
        if len(row) <= value_idx:
            continue

        account = str(row[account_idx] or "").strip()
        description = str(row[description_idx] or "").strip()
        symbol = str(row[symbol_idx] or "").strip() or "N/A"
        value = _parse_number(row[value_idx])

        if value is None or not description:
            continue

        positions.append({
            "institution": "UBS",
            "account": account,
            "symbol": symbol,
            "name": get_display_name(symbol, description),
            "description": description,
            "asset_class": classify_asset(symbol, description),
            "currency": "USD",
            "value": value,
            "weight": None,
        })

    if not positions:
        raise EmptyPortfolioError("Nenhuma posição UBS foi encontrada no arquivo.")

    return tuple(
        _to_portfolio_position(position, path.name)
        for position in positions
    )
