"""Official remote connector for public Banco Central do Brasil data."""

from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.important_facts import FactCategory, FactImportance, MarketFact
from backend.market_agenda import (
    MarketAgendaEvent, MarketAgendaEventType, MarketAgendaImportance,
)
from backend.market_connectors.base import MarketConnector


_SGS_ENDPOINT = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1"
_COPOM_ENDPOINT = "https://www.bcb.gov.br/api/servico/sitebcb/copom/calendariocopom"


class BcbResponseError(ValueError):
    """Raised when an official BCB response cannot be normalized atomically."""


def _http_json(url: str, timeout: float) -> Any:
    separator = "&" if "?" in url else "?"
    request = Request(
        f"{url}{separator}{urlencode({'formato': 'json'})}",
        headers={"Accept": "application/json", "User-Agent": "ARGOS/0.4"},
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise BcbResponseError(f"BCB respondeu HTTP {response.status}.")
        return json.loads(response.read().decode("utf-8"))


class BcbMarketConnector(MarketConnector):
    """Fetch, validate and normalize the predefined SGS and Copom sources."""

    def __init__(self, transport: Callable[[str, float], Any] = _http_json, timeout: float = 2.0) -> None:
        self._transport, self._timeout = transport, timeout

    def is_available(self) -> bool:
        try:
            self._sgs()
            return True
        except Exception:
            return False

    def load_facts(self) -> tuple[MarketFact, ...]:
        row = self._sgs()
        reference = self._br_date(row.get("data"))
        value = self._number(row.get("valor"))
        published = datetime.combine(reference, datetime.min.time(), timezone.utc)
        return (MarketFact(
            id=f"bcb-sgs-selic-meta-{reference.isoformat()}",
            title="Meta da taxa Selic publicada pelo Banco Central",
            description=f"A série SGS 432 registra a meta da taxa Selic em {value:.2f}% a.a.",
            source="Banco Central do Brasil — SGS 432", published_at=published,
            importance=FactImportance.MEDIUM, urgency=FactImportance.MEDIUM,
            category=FactCategory.ECONOMY, related_currencies=("BRL",),
            related_institutions=("BCB",),
        ),)

    def load_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        payload = self._transport(_COPOM_ENDPOINT, self._timeout)
        rows = payload.get("conteudo", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            raise BcbResponseError("Calendário do Copom vazio ou inválido.")
        events = []
        for row in rows:
            if not isinstance(row, dict):
                raise BcbResponseError("Item inválido no calendário do Copom.")
            raw_date = row.get("dataReferencia") or row.get("data") or row.get("DataReferencia")
            reference = self._date(raw_date)
            events.append(MarketAgendaEvent(
                event_id=f"bcb-copom-{reference.isoformat()}", event_type=MarketAgendaEventType.CENTRAL_BANK,
                title="Reunião do Copom", event_date=reference, event_time=None, timezone="America/Sao_Paulo",
                all_day=True, institution="Banco Central do Brasil", asset_identifiers=(), asset_names=(),
                asset_classes=(), sectors=(), currencies=("BRL",), markets=("Brasil",), country="BR",
                importance=MarketAgendaImportance.HIGH, source_name="Banco Central do Brasil",
                source_reference="Calendário oficial do Copom", description="Reunião oficial do Copom.",
            ))
        return tuple(events)

    def metadata(self) -> Mapping[str, object]:
        return {"connector": "BCB", "source": "BCB", "source_type": "REMOTE"}

    def _sgs(self) -> dict[str, Any]:
        payload = self._transport(_SGS_ENDPOINT, self._timeout)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise BcbResponseError("Resposta inválida da série SGS 432.")
        return payload[0]

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError) as error:
            raise BcbResponseError("Valor inválido na série SGS 432.") from error

    @staticmethod
    def _br_date(value: Any) -> date:
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except (TypeError, ValueError) as error:
            raise BcbResponseError("Data inválida na série SGS 432.") from error

    @staticmethod
    def _date(value: Any) -> date:
        if not isinstance(value, str):
            raise BcbResponseError("Data inválida no calendário do Copom.")
        for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value[:19], pattern).date()
            except ValueError:
                pass
        raise BcbResponseError("Data inválida no calendário do Copom.")
