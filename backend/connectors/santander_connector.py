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


def _normalize_header(value):
    return normalize_header(value)


def _parse_number(value):
    number = parse_decimal(value)
    return float(number) if number is not None else None


def _row_contains(row, expected):
    return any(_normalize_header(value) == expected for value in row)


def _count_asset_summary_positions(rows, title_index):
    header_index = next(
        (
            index
            for index in range(title_index + 1, len(rows))
            if _has_header_markers(rows[index])
        ),
        None,
    )
    if header_index is None:
        raise ValueError(
            "Não encontrei o início da tabela de posições em RESUMO DE ATIVOS."
        )

    mapping = _map_block_headers(rows[header_index])
    value_index = mapping.get("value")
    if value_index is None:
        raise ValueError(
            "Não encontrei a coluna de valor da tabela em RESUMO DE ATIVOS."
        )

    count = 0
    table_started = False
    for row in rows[header_index + 1 :]:
        if _is_total_row(row):
            return count
        if _is_blank_row(row):
            if table_started:
                return count
            continue
        if _has_header_markers(row):
            break

        table_started = True
        if _parse_number(_safe_get(row, value_index)) is not None:
            count += 1

    if not table_started:
        raise ValueError("A tabela RESUMO DE ATIVOS não contém posições.")
    return count


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
            shared_root = ElementTree.fromstring(
                archive.read("xl/sharedStrings.xml")
            )
            for item in shared_root.findall(f"{{{main_namespace}}}si"):
                shared_strings.append("".join(
                    node.text or ""
                    for node in item.iter(f"{{{main_namespace}}}t")
                ))

        for sheet in workbook.findall(f".//{{{main_namespace}}}sheet"):
            relationship_id = sheet.attrib[f"{{{relationship_namespace}}}id"]
            target = targets[relationship_id].lstrip("/")
            worksheet_path = (
                target if target.startswith("xl/") else f"xl/{target}"
            )
            worksheet = ElementTree.fromstring(archive.read(worksheet_path))
            rows = []
            for row_node in worksheet.findall(f".//{{{main_namespace}}}row"):
                row = []
                for cell in row_node.findall(f"{{{main_namespace}}}c"):
                    reference = cell.attrib.get("r", "A1")
                    letters = "".join(
                        character
                        for character in reference
                        if character.isalpha()
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
    """Identifica a tabela RESUMO DE ATIVOS sem converter suas posições."""
    path = Path(file_path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("O arquivo Santander deve estar em XLSX.")
    if not path.exists():
        raise ValueError(f"Arquivo Santander não encontrado: {path.name}")

    for _sheet_name, rows in _xlsx_sheet_rows(path):
        title_index = next(
            (
                index
                for index, row in enumerate(rows)
                if _row_contains(row, ASSET_SUMMARY_TITLE)
            ),
            None,
        )
        if title_index is not None:
            return {
                "source": SANTANDER_EXCEL_SOURCE,
                "position_count": _count_asset_summary_positions(
                    rows, title_index
                ),
            }

    raise ValueError("Não encontrei a seção RESUMO DE ATIVOS no arquivo Santander.")


def _read_rows(path: Path):
    if path.suffix.lower() == ".xlsx":
        return [row for _sheet_name, rows in _xlsx_sheet_rows(path) for row in rows]
    return read_tabular_rows(
        path, institution=institution, extensions=supported_extensions
    )


def _has_header_markers(row):
    normalized = [_normalize_header(value) for value in row]
    has_value = any(
        "SALDO MOEDA REFERÊNCIA" in value or
        "SALDO NA MOEDA DE REFERÊNCIA" in value
        for value in normalized
    )
    has_weight = any(
        "PESO DA CONTA (%)" in value or "% DO TOTAL" in value
        for value in normalized
    )
    has_name = any(
        value in {
            "NOME DA CARTEIRA",
            "NOME DO ATIVO",
            "ISIN",
            "VALOR DO MERCADO",
            "PREÇO ATUAL",
            "NUMERO DE CONTA",
            "NÚMERO DE CONTA",
            "SALDO",
        }
        for value in normalized
    )
    return has_value and has_weight and has_name


def _is_blank_row(row):
    return all(cell is None or str(cell).strip() == "" for cell in row)


def _is_total_row(row):
    first = str(row[0] or "").strip().upper() if row else ""
    return first.startswith("TOTAL")


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
    for index, value in enumerate(header):
        normalized = _normalize_header(value)
        if normalized in {"ISIN", "TICKER", "CÓDIGO", "CODIGO", "TICKER/ISIN"}:
            mapping["symbol"] = index
        elif normalized in {"NOME DA CARTEIRA", "NOME DO ATIVO", "ATIVO", "DESCRIÇÃO", "DESCRICAO"}:
            mapping["description"] = index
        elif normalized in {"SALDO MOEDA REFERÊNCIA", "SALDO NA MOEDA DE REFERÊNCIA", "SALDO"}:
            mapping["value"] = index
        elif normalized in {"PESO DA CONTA (%)", "% DO TOTAL"}:
            mapping["weight"] = index
        elif normalized in {"NUMERO DE CONTA", "NÚMERO DE CONTA", "ACCOUNT", "ACCOUNT NUMBER"}:
            mapping["account"] = index
        elif normalized == "MOEDA":
            mapping.setdefault("currency_candidates", []).append(index)
        elif normalized in {"ASSET CLASS", "CLASS", "CATEGORIA", "CATEGORY"}:
            mapping["asset_class"] = index
        elif normalized in {"VALOR DO MERCADO", "VALOR ESTIMADO", "VALOR INVESTIDO"} and "value" not in mapping:
            mapping["value"] = index
    return mapping


def _safe_get(row, index):
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def _find_currency(row, value_index, currency_indices):
    if currency_indices:
        for index in currency_indices:
            currency = _safe_get(row, index)
            if currency and str(currency).strip().upper() in {"USD", "BRL", "EUR"}:
                return str(currency).strip().upper()
    next_cell = _safe_get(row, value_index + 1)
    if next_cell and str(next_cell).strip().upper() in {"USD", "BRL", "EUR"}:
        return str(next_cell).strip().upper()
    return "USD"


def _looks_like_account_or_category(value) -> bool:
    text = str(value or "").strip().upper()
    if not text or text in {"N/A", "NONE", "NA"}:
        return True
    if "ADVISORY" in text or "ACCOUNT" in text or "CARTEIRA" in text:
        return True
    if text in {"RENDA FIXA", "RENDA VARIÁVEL", "ALTERNATIVOS", "CURTO PRAZO", "LIQUIDEZ", "TOTAL"}:
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
        first = str(row[0] or "").strip().upper()
        if _has_header_markers(row) and first:
            headers.append(index)
    return headers


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
    if not block_headers:
        raise UnrecognizedFileError(
            "Não encontrei blocos Santander com cabeçalhos esperados."
        )

    positions = []
    for header_index in block_headers:
        header_row = rows[header_index]
        asset_class = _class_from_block_name(header_row[0])
        mapping = _map_block_headers(header_row)
        if "value" not in mapping or "weight" not in mapping:
            continue

        for row in rows[header_index + 1 :]:
            if _is_blank_row(row) or _has_header_markers(row):
                break
            if _is_total_row(row):
                continue

            value = _parse_number(_safe_get(row, mapping["value"]))
            if value is None:
                continue

            symbol = str(_safe_get(row, mapping.get("symbol", -1)) or "").strip()
            if not symbol or symbol.upper() == "N/A":
                symbol = str(_safe_get(row, 0) or "").strip() or ""

            name = _build_display_name(row, mapping, symbol)
            if not name:
                continue

            account = str(_safe_get(row, mapping.get("account", -1)) or "").strip()
            currency = _find_currency(row, mapping["value"], mapping.get("currency_candidates", []))
            weight = _parse_number(_safe_get(row, mapping["weight"]))

            positions.append({
                "institution": "Santander",
                "account": account,
                "symbol": symbol,
                "name": name,
                "description": name,
                "asset_class": asset_class,
                "currency": currency,
                "value": value,
                "weight": weight,
            })

    if not positions:
        raise EmptyPortfolioError(
            "Nenhuma posição Santander foi encontrada no arquivo."
        )

    return tuple(
        _to_portfolio_position(position, path.name)
        for position in positions
    )


def recognize(path: Path) -> bool:
    path = Path(path)
    if path.suffix.lower() not in supported_extensions or not path.exists():
        return False
    try:
        return bool(_find_block_headers(_read_rows(path)))
    except (OSError, ValueError):
        return False
