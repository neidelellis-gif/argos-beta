"""Parser do relatório textual de posições do Bradesco Private."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.connectors.errors import (
    ConnectorFileNotFoundError,
    EmptyPortfolioError,
    UnsupportedExtensionError,
    UnrecognizedFileError,
)
from backend.models import PortfolioOwner, PortfolioPosition


connector_id = "bradesco"
institution = "Bradesco"
owner = PortfolioOwner.NEI
supported_extensions = frozenset({".txt"})
SUPPORTED_EXTENSIONS = supported_extensions

_REPORT_TITLE = "POSICAO DETALHADA DOS INVESTIMENTOS"
_MAJOR_CLASSES = {
    "RENDA FIXA": "Renda Fixa",
    "RENDA VARIÁVEL": "Renda Variável",
    "ALTERNATIVOS": "Alternativos",
}
_SUBCLASSES = {
    "PÓS-FIXADO", "PRÉ-FIXADO", "JURO REAL - INFLAÇÃO", "RENDA VARIÁVEL",
    "MULTIMERCADOS", "REAL ESTATE", "PRIVATE EQUITY",
}
_STARTS = (
    "BRADESCO PRIVATE PERFORMANCE", "CDB - ", "DEBÊNTURES - ",
    "IT NOW IMA-BF11", "AZ QUEST TOP LONG", "AÇÕES ", "GX CYBER",
    "ISHARES SP 500", "IT NOW SP+RF", "PALANTIR", "VINCI GAS",
    "WESTERN ASSET", "MM ", "AZ QUEST TR", "BLACKROCK GLOBAL",
    "BRL IE ", "OAKTREE GLOBAL", "FIC MM ", "FII ", "FUNDO CSHG",
    "BRADESCO EXPLORER PE ", "BRADESCO EXPLORER PRIVATE",
    "EQUITY FIP ",
)
_DATE = r"\d{2}/\d{2}/\d{2}"
_NUMBER = r"(?:\([\d.,]+\)|[\d.,]+)"


def _plain(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.upper())
        if not unicodedata.combining(character)
    )


def _decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(".", "").replace(",", ".")
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return -result if negative else result


def _is_position_start(line: str) -> bool:
    upper = line.upper()
    return any(upper.startswith(prefix) for prefix in _STARTS)


def _is_noise(line: str) -> bool:
    plain = _plain(line)
    return (
        not line
        or plain.startswith(("CODIGO DA CARTEIRA:", "PAGINA ", "TOTAL "))
        or plain in {
            "POSICAO DETALHADA DOS INVESTIMENTOS", "DATA DE", "EMISSAO",
            "APLICACAO", "VENCIMENTO", "INICIAL R$", "TX %", "EMIS.",
            "A.A. QUANTIDADE PRECO", "ATUAL", "VALOR", "BRUTO ATUAL IMPOSTOS ALIQ.",
            "LIQUIDO ATUAL", "PART %", "PFOLIO", "RENTABILIDADE", "MES INICIO",
        }
        or plain.startswith("POSICAO ANALITICA DOS INVESTIMENTOS - PREVIDENCIA")
    )


def recognize(path: Path) -> bool:
    path = Path(path)
    if path.suffix.lower() not in supported_extensions or not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False
    plain = _plain(text)
    return _REPORT_TITLE in plain and "CODIGO DA CARTEIRA:" in plain


def _records(text: str):
    """Une somente quebras de linha internas de uma posição impressa."""
    asset_class = None
    subclass = None
    current = []
    current_context = (None, None)

    def flush():
        nonlocal current
        if current:
            result = (" ".join(current), *current_context)
            current = []
            return result
        return None

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        plain = _plain(line)
        major_key = next(
            (key for key in _MAJOR_CLASSES if plain.startswith(_plain(key) + " ") or plain == _plain(key)),
            None,
        )
        if major_key:
            item = flush()
            if item:
                yield item
            asset_class = _MAJOR_CLASSES[major_key]
            subclass = "RENDA VARIÁVEL" if major_key == "RENDA VARIÁVEL" else None
            continue
        if plain in {_plain(item) for item in _SUBCLASSES}:
            item = flush()
            if item:
                yield item
            subclass = next(item for item in _SUBCLASSES if _plain(item) == plain)
            continue
        if _is_noise(line):
            continue
        if current and re.fullmatch(_NUMBER, line):
            # Percentuais de participação/rentabilidade podem ser deslocados
            # para antes da continuação do nome pela extração do PDF.
            continue
        if _is_position_start(line):
            # Linhas de continuação conhecidas não iniciam uma nova posição.
            continuation = line.startswith(("AÇÕES ", "MM ", "BRL IE ", "FIC MM ", "EQUITY FIP "))
            if current and not continuation:
                yield (" ".join(current), *current_context)
                current = []
            if not current:
                current_context = (asset_class, subclass)
            current.append(line)
        elif current:
            current.append(line)
    item = flush()
    if item:
        yield item


def _parse_record(record: str):
    # Layout sem datas: nome, quantidade, preço, bruto, líquido e campos finais.
    simple = None if re.search(_DATE, record) else re.match(
        rf"^(?P<name>.+?) (?P<quantity>{_NUMBER}) (?P<price>{_NUMBER}) "
        rf"(?P<gross>{_NUMBER}) (?P<net>{_NUMBER})(?: |$)", record
    )
    if simple:
        values = simple.groupdict()
        return values["name"], _decimal(values["quantity"]), _decimal(values["price"]), _decimal(values["gross"]), None

    dates = list(re.finditer(_DATE, record))
    if not dates:
        return None
    name = record[: dates[0].start()].strip()
    tail = record[dates[-1].end():]
    numbers = re.findall(_NUMBER, tail)
    if len(numbers) < 4:
        return None

    # Nos lotes datados, os quatro números após a aplicação inicial são
    # quantidade, preço da cota, valor bruto e impostos.
    if "CDB - " in name or "DEBÊNTURES - " in name:
        # Após taxa textual: quantidade, preço, bruto, impostos, alíquota, líquido, participação.
        rate_end = re.search(r"(?:CDI - [\d.]+|PRE)", tail)
        financial = re.findall(_NUMBER, tail[rate_end.end():] if rate_end else tail)
        if len(financial) < 6:
            return None
        quantity = _decimal(financial[0])
        price = _decimal(financial[1])
        gross = _decimal(financial[3])
        weight = _decimal(financial[7]) if len(financial) > 7 else None
        return name, quantity, price, gross, weight

    if len(numbers) < 5:
        return None
    quantity, price, gross = map(_decimal, numbers[1:4])
    weight = _decimal(numbers[7]) if len(numbers) > 7 else None
    return name, quantity, price, gross, weight


def _asset_class(name: str, report_subclass: str | None) -> str:
    """Mapeia somente categorias explicitamente identificáveis no relatório."""
    upper = name.upper()
    if upper.startswith("CDB - "):
        return "CDB"
    if upper.startswith("DEBÊNTURES - "):
        return "Debêntures"
    if report_subclass == "PRIVATE EQUITY":
        return "Private Equity"
    if report_subclass == "MULTIMERCADOS":
        return "Multimercados"
    if upper.startswith(("FII ", "FUNDO CSHG")):
        return "FIIs"
    if upper.startswith(("IT NOW ", "GX CYBER")):
        return "ETF"
    if upper.startswith("PALANTIR"):
        return "Ações"
    return "Fundos"


def _to_portfolio_position(position, source_file):
    """Converte uma linha Bradesco já extraída para o modelo universal."""
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=None,
        asset_class=position.get("asset_class"),
        asset_subclass=position.get("asset_subclass"),
        asset_name=position.get("name"),
        identifier=None,
        identifier_type=None,
        quantity=_decimal(position.get("quantity")),
        unit_price=_decimal(position.get("price")),
        market_value=_decimal(position.get("gross")),
        currency="BRL",
        portfolio_weight=_decimal(position.get("weight")),
        reference_date=None,
        source_file=source_file,
    )


def load_positions(file_path: Path) -> tuple[PortfolioPosition, ...]:
    path = Path(file_path)
    if path.suffix.lower() not in supported_extensions:
        raise UnsupportedExtensionError("O relatório Bradesco deve estar em TXT.")
    if not path.exists():
        raise ConnectorFileNotFoundError(f"Arquivo Bradesco não encontrado: {path.name}")
    text = path.read_text(encoding="utf-8-sig")
    if _REPORT_TITLE not in _plain(text):
        raise UnrecognizedFileError("Não encontrei a seção de posições do relatório Bradesco.")

    positions = []
    for record, asset_class, subclass in _records(text):
        parsed = _parse_record(record)
        if not parsed:
            continue
        name, quantity, price, gross, weight = parsed
        positions.append(_to_portfolio_position({
            "name": name, "asset_class": _asset_class(name, subclass),
            "asset_subclass": subclass,
            "quantity": quantity, "price": price, "gross": gross, "weight": weight,
        }, path.name))
    if not positions:
        raise EmptyPortfolioError("Nenhuma posição Bradesco foi encontrada no relatório.")
    return tuple(positions)
