import logging
import re
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

from backend.models import PortfolioOwner, PortfolioPosition
from backend.connectors.errors import (
    ConnectorFileNotFoundError,
    EmptyPortfolioError,
    UnsupportedExtensionError,
    UnrecognizedFileError,
)
from backend.connectors.io import normalize_header, parse_decimal, read_tabular_rows

connector_id = "santander"
institution = "Santander"
owner = PortfolioOwner.JOLIKA
supported_extensions = frozenset({".xls", ".xlsx"})
SUPPORTED_EXTENSIONS = supported_extensions
SANTANDER_EXCEL_SOURCE = "Santander Excel Export"
ASSET_SUMMARY_TITLE = "RESUMO DE ATIVOS"
logger = logging.getLogger("argos.import.santander")


def _configure_import_logger():
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _log_santander(message, **details):
    _configure_import_logger()
    detail_text = " ".join(f"{key}={value!r}" for key, value in sorted(details.items()))
    logger.info("%s%s", message, f" {detail_text}" if detail_text else "")


def _normalize_header(value):
    return normalize_header(value)


def _parse_number(value):
    number = parse_decimal(value)
    return float(number) if number is not None else None


def _row_contains(row, expected):
    return any(_normalize_header(value) == expected for value in row)


def _xlsx_sheet_rows(path):
    main_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    package_relationship_namespace = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )

    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("O arquivo Santander não é um XLSX válido.") from exc

    with archive:
        try:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
        except (KeyError, ElementTree.ParseError) as exc:
            raise ValueError("O arquivo Santander não é um XLSX válido.") from exc

        targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships.findall(
                f"{{{package_relationship_namespace}}}Relationship"
            )
        }
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{main_namespace}}}si"):
                shared_strings.append(
                    "".join(
                        node.text or "" for node in item.iter(f"{{{main_namespace}}}t")
                    )
                )

        for sheet in workbook.findall(f".//{{{main_namespace}}}sheet"):
            relationship_id = sheet.attrib[f"{{{relationship_namespace}}}id"]
            target = targets[relationship_id].lstrip("/")
            worksheet_path = target if target.startswith("xl/") else f"xl/{target}"
            worksheet = ElementTree.fromstring(archive.read(worksheet_path))
            rows = []
            for row_node in worksheet.findall(f".//{{{main_namespace}}}row"):
                row = []
                for cell in row_node.findall(f"{{{main_namespace}}}c"):
                    reference = cell.attrib.get("r", "A1")
                    letters = "".join(
                        character for character in reference if character.isalpha()
                    )
                    column = 0
                    for letter in letters.upper():
                        column = column * 26 + ord(letter) - ord("A") + 1
                    while len(row) < column:
                        row.append(None)

                    cell_type = cell.attrib.get("t")
                    value_node = cell.find(f"{{{main_namespace}}}v")
                    if cell_type == "inlineStr":
                        value = "".join(
                            node.text or ""
                            for node in cell.iter(f"{{{main_namespace}}}t")
                        )
                    elif value_node is None:
                        value = None
                    elif cell_type == "s":
                        value = shared_strings[int(cast(str, value_node.text))]
                    else:
                        raw_value = cast(str, value_node.text)
                        try:
                            value = float(raw_value)
                        except (TypeError, ValueError):
                            value = raw_value
                    row[column - 1] = value
                rows.append(row)
            yield sheet.attrib.get("name", ""), rows


def inspect_excel_export(file_path):
    """Identifica exportações Santander com a mesma regra da importação."""
    path = Path(file_path)
    _log_santander(
        "inspect_excel_export called", file_name=path.name, suffix=path.suffix.lower()
    )
    if path.suffix.lower() != ".xlsx":
        raise ValueError("O arquivo Santander deve estar em XLSX.")
    if not path.exists():
        raise ValueError(f"Arquivo Santander não encontrado: {path.name}")

    rows = _read_rows(path)
    _log_santander(
        "inspect_excel_export read rows", file_name=path.name, row_count=len(rows)
    )
    if not any(_row_contains(row, ASSET_SUMMARY_TITLE) for row in rows):
        raise ValueError("Não encontrei a seção RESUMO DE ATIVOS no arquivo Santander.")

    positions = _parse_positions(
        rows, context="inspect_excel_export", source_file=path.name
    )
    _log_santander(
        "inspect_excel_export parsed positions",
        file_name=path.name,
        position_count=len(positions),
    )
    if not positions:
        raise ValueError("Nenhuma posição Santander foi encontrada no arquivo.")
    return {
        "source": SANTANDER_EXCEL_SOURCE,
        "position_count": len(positions),
    }


def _read_rows(path: Path):
    if path.suffix.lower() == ".xlsx":
        return [row for _sheet_name, rows in _xlsx_sheet_rows(path) for row in rows]
    return read_tabular_rows(
        path, institution=institution, extensions=supported_extensions
    )


def _has_header_markers(row):
    normalized = [_normalize_header(value) for value in row]
    has_value = any(_is_value_header(value) for value in normalized)
    has_name = any(
        value
        in {
            "NOME DA CARTEIRA",
            "NOME DO ATIVO",
            "ISIN",
            "TICKER",
            "CÓDIGO",
            "CODIGO",
            "TICKER/ISIN",
            "NUMERO DE CONTA",
            "NÚMERO DE CONTA",
        }
        for value in normalized
    )
    return has_value and has_name


def _is_blank_row(row):
    return all(cell is None or str(cell).strip() == "" for cell in row)


def _is_total_row(row):
    first = str(row[0] or "").strip().upper() if row else ""
    return first.startswith("TOTAL")


def _is_value_header(value: str) -> bool:
    return value in {
        "VALOR DO MERCADO",
        "SALDO MOEDA REFERÊNCIA",
        "SALDO NA MOEDA DE REFERÊNCIA",
        "VALOR ESTIMADO",
        "VALOR INVESTIDO",
        "SALDO",
    }


def _is_santander_block_title(value) -> bool:
    text = str(value or "").strip().upper()
    return (
        (
            text.startswith("RENDA FIXA")
            and ("TÍTULOS" in text or "TITULOS" in text or "FUNDOS" in text)
        )
        or (
            text.startswith("RENDA VARIÁVEL")
            and ("AÇÕES" in text or "ACOES" in text or "FUNDOS" in text)
        )
        or text.startswith("FUNDOS ALTERNATIVOS")
        or text.startswith("FUNDOS DE MERCADOS PRIVADOS")
        or text.startswith("LIQUIDEZ")
    )


def _class_from_block_name(title: str) -> str:
    text = str(title or "").strip().upper()
    if text.startswith("RENDA FIXA"):
        return "Renda Fixa"
    if "AÇÕES" in text:
        return "Ação"
    if "FUNDOS" in text and "RENDA VARIÁVEL" in text:
        return "ETF/Fundo"
    if text.startswith("FUNDOS ALTERNATIVOS"):
        return "Alternativos"
    if text.startswith("FUNDOS DE MERCADOS PRIVADOS"):
        return "Alternativos"
    if text.startswith("LIQUIDEZ"):
        return "Caixa"
    return "Outros"


def _map_block_headers(header):
    mapping = {}
    value_priority = {
        "SALDO MOEDA REFERÊNCIA": 0,
        "SALDO NA MOEDA DE REFERÊNCIA": 0,
        "SALDO": 0,
        "VALOR DO MERCADO": 1,
        "VALOR ESTIMADO": 2,
        "VALOR INVESTIDO": 3,
    }
    selected_value_priority = None
    if header and _is_santander_block_title(header[0]):
        mapping["description"] = 0
    for index, value in enumerate(header):
        normalized = _normalize_header(value)
        if normalized in {"ISIN", "TICKER", "CÓDIGO", "CODIGO", "TICKER/ISIN"}:
            mapping["symbol"] = index
        elif normalized in {
            "NOME DA CARTEIRA",
            "NOME DO ATIVO",
            "ATIVO",
            "DESCRIÇÃO",
            "DESCRICAO",
        }:
            mapping.setdefault("description", index)
        elif normalized in value_priority:
            priority = value_priority[normalized]
            if selected_value_priority is None or priority < selected_value_priority:
                mapping["value"] = index
                mapping["value_header"] = normalized
                selected_value_priority = priority
        elif normalized in {"PESO DA CONTA (%)", "% DO TOTAL"}:
            mapping["weight"] = index
        elif normalized in {
            "NUMERO DE CONTA",
            "NÚMERO DE CONTA",
            "ACCOUNT",
            "ACCOUNT NUMBER",
        }:
            mapping["account"] = index
        elif normalized == "MOEDA":
            mapping.setdefault("currency_candidates", []).append(index)
        elif normalized in {"ASSET CLASS", "CLASS", "CATEGORIA", "CATEGORY"}:
            mapping["asset_class"] = index
    return mapping


def _safe_get(row, index):
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def _find_reference_currency(rows):
    for row in rows:
        if not _is_total_row(row):
            continue
        for value in row:
            currency = str(value or "").strip().upper()
            if currency in {"USD", "BRL", "EUR"}:
                return currency
    return "USD"


def _find_currency(row, value_index, currency_indices, value_header, reference_currency):
    if value_header in {"SALDO MOEDA REFERÊNCIA", "SALDO NA MOEDA DE REFERÊNCIA"}:
        return reference_currency
    if currency_indices:
        for index in currency_indices:
            currency = _safe_get(row, index)
            if currency and str(currency).strip().upper() in {"USD", "BRL", "EUR"}:
                return str(currency).strip().upper()
    next_cell = _safe_get(row, value_index + 1)
    if next_cell and str(next_cell).strip().upper() in {"USD", "BRL", "EUR"}:
        return str(next_cell).strip().upper()
    return reference_currency


def _looks_like_account_or_category(value) -> bool:
    text = str(value or "").strip().upper()
    if not text or text in {"N/A", "NONE", "NA"}:
        return True
    if "ADVISORY" in text or "ACCOUNT" in text or "CARTEIRA" in text:
        return True
    if text in {
        "RENDA FIXA",
        "RENDA VARIÁVEL",
        "ALTERNATIVOS",
        "CURTO PRAZO",
        "LIQUIDEZ",
        "TOTAL",
    }:
        return True
    return False


def _extract_coupon(value):
    if value is None:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    return round(float(match.group(1).replace(",", ".")), 2)


def _extract_year(value):
    if value is None:
        return None
    match = re.search(r"(\d{4})", str(value))
    return match.group(1) if match else None


def _build_display_name(row, mapping, symbol):
    first_cell = str(_safe_get(row, 0) or "").strip()
    fallback_name = str(_safe_get(row, mapping.get("description", 0)) or "").strip()

    if _looks_like_account_or_category(fallback_name):
        fallback_name = first_cell

    if not fallback_name or _looks_like_account_or_category(fallback_name):
        fallback_name = first_cell or symbol or "Ativo"

    coupon = _extract_coupon(_safe_get(row, 2))
    maturity_year = _extract_year(_safe_get(row, 5))

    if coupon is not None and maturity_year:
        issuer = fallback_name or first_cell or symbol or "Ativo"
        return f"{issuer} {coupon:.2f}% {maturity_year}"

    if not fallback_name or _looks_like_account_or_category(fallback_name):
        return symbol or "Ativo"

    return fallback_name


def _find_block_headers(rows):
    headers = []
    for index, row in enumerate(rows):
        if not row:
            continue
        if _is_santander_block_title(row[0]) and _has_header_markers(row):
            headers.append(index)
    return headers


def _parse_positions(rows, *, context="load_positions", source_file=None):
    positions = []
    block_headers = _find_block_headers(rows)
    _log_santander(
        "Santander parser block headers found",
        context=context,
        source_file=source_file,
        block_count=len(block_headers),
        header_indexes=block_headers,
    )
    skipped_rows = {"missing_value": 0, "missing_name": 0, "total_row": 0}
    reference_currency = _find_reference_currency(rows)
    for header_index in block_headers:
        header_row = rows[header_index]
        asset_class = _class_from_block_name(header_row[0])
        mapping = _map_block_headers(header_row)
        if "value" not in mapping:
            _log_santander(
                "Santander parser skipped block without value header",
                context=context,
                source_file=source_file,
                header_index=header_index,
                asset_class=asset_class,
                mapped_columns=mapping,
            )
            continue

        for row in rows[header_index + 1 :]:
            if _is_blank_row(row) or _has_header_markers(row):
                break
            if _is_total_row(row):
                skipped_rows["total_row"] += 1
                continue

            value = _parse_number(_safe_get(row, mapping["value"]))
            if value is None:
                skipped_rows["missing_value"] += 1
                continue

            symbol = str(_safe_get(row, mapping.get("symbol", -1)) or "").strip()
            if not symbol or symbol.upper() == "N/A":
                symbol = str(_safe_get(row, 0) or "").strip() or ""

            name = _build_display_name(row, mapping, symbol)
            if not name:
                skipped_rows["missing_name"] += 1
                continue

            account = str(_safe_get(row, mapping.get("account", -1)) or "").strip()
            currency = _find_currency(
                row,
                mapping["value"],
                mapping.get("currency_candidates", []),
                mapping.get("value_header"),
                reference_currency,
            )
            weight = _parse_number(_safe_get(row, mapping.get("weight")))

            positions.append(
                {
                    "institution": "Santander",
                    "account": account,
                    "symbol": symbol,
                    "name": name,
                    "description": name,
                    "asset_class": asset_class,
                    "currency": currency,
                    "value": value,
                    "weight": weight,
                }
            )

    total_value = sum(Decimal(str(position["value"])) for position in positions)
    _log_santander(
        "Santander parser calculated total value",
        context=context,
        source_file=source_file,
        position_count=len(positions),
        total_value=str(total_value),
        skipped_rows=skipped_rows,
        single_position_reason=(
            "only one parsed row survived header/value/name filters"
            if len(positions) == 1
            else None
        ),
        single_position_asset=(positions[0]["name"] if len(positions) == 1 else None),
        single_position_value=(positions[0]["value"] if len(positions) == 1 else None),
    )
    if total_value:
        for position in positions:
            if position.get("weight") is None:
                position["weight"] = (
                    Decimal(str(position["value"])) / total_value * Decimal("100")
                )
    return positions


def _to_portfolio_position(position, source_file):
    """Converte uma posição lida do Santander para o MPU."""
    identifier = position.get("symbol") or None
    account = position.get("account") or None

    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=account,
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


def load_positions(file_path: Path) -> tuple[PortfolioPosition, ...]:
    path = Path(file_path)
    _log_santander(
        "load_positions called", file_name=path.name, suffix=path.suffix.lower()
    )
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedExtensionError(
            "O arquivo Santander deve estar em XLS ou XLSX."
        )
    if not path.exists():
        raise ConnectorFileNotFoundError(
            f"Arquivo Santander não encontrado: {path.name}"
        )

    rows = _read_rows(path)
    block_headers = _find_block_headers(rows)
    _log_santander(
        "load_positions read rows",
        file_name=path.name,
        row_count=len(rows),
        block_count=len(block_headers),
        recognized_as_santander=bool(block_headers),
    )
    if not block_headers:
        raise UnrecognizedFileError(
            "Não encontrei blocos Santander com cabeçalhos esperados."
        )

    positions = _parse_positions(rows, context="load_positions", source_file=path.name)
    _log_santander(
        "load_positions parsed raw positions",
        file_name=path.name,
        position_count=len(positions),
    )
    if not positions:
        raise EmptyPortfolioError(
            "Nenhuma posição Santander foi encontrada no arquivo."
        )

    portfolio_positions = tuple(
        _to_portfolio_position(position, path.name) for position in positions
    )
    total_market_value = sum(position.market_value for position in portfolio_positions)
    _log_santander(
        "load_positions returned MPU positions",
        file_name=path.name,
        position_count=len(portfolio_positions),
        total_market_value=str(total_market_value),
        ten_thousand_sources=[
            position.asset_name
            for position in portfolio_positions
            if position.market_value == Decimal("10000")
        ],
    )
    return portfolio_positions


def recognize(path: Path) -> bool:
    path = Path(path)
    _log_santander(
        "recognize called",
        file_name=path.name,
        suffix=path.suffix.lower(),
        exists=path.exists(),
    )
    if path.suffix.lower() not in supported_extensions or not path.exists():
        _log_santander(
            "recognize result",
            file_name=path.name,
            recognized_as_santander=False,
            reason="unsupported extension or missing file",
        )
        return False
    try:
        rows = _read_rows(path)
        block_headers = _find_block_headers(rows)
        recognized = bool(block_headers)
        _log_santander(
            "recognize result",
            file_name=path.name,
            recognized_as_santander=recognized,
            row_count=len(rows),
            block_count=len(block_headers),
            header_indexes=block_headers,
        )
        return recognized
    except (OSError, ValueError) as exc:
        _log_santander(
            "recognize result",
            file_name=path.name,
            recognized_as_santander=False,
            reason=str(exc),
        )
        return False
