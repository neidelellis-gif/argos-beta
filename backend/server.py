import base64
from email.parser import BytesParser
from email.policy import default as email_policy
import http.server
import logging
import json
import os
import secrets
import socketserver
import sys
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, TypedDict, cast

from backend.models import PortfolioOwner, PortfolioPosition

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.dashboard import build_dashboard
from backend.canonical_portfolio import serialize_portfolio_positions
from backend.daily_http import DailyHttpAdapter, MAX_DAILY_REQUEST_BYTES
from backend.daily_api import DailyApiFacade
from backend.ubs_daily_intelligence import UBSDailyIntelligenceService
from backend.santander_daily_intelligence import SantanderDailyIntelligenceService
from backend.jolika_daily_intelligence import JolikaDailyIntelligenceService
from backend.market.market_connector import MarketConnector
from backend.market.finnhub_provider import FinnhubMarketProvider
from backend.market.twelve_data_provider import TwelveDataMarketProvider
from backend.portfolio_import import import_portfolios
from backend.pasted_portfolio import parse_pasted_portfolio
from backend.portfolio_classification import classify_jolika_positions
from backend.asset_resolution import resolve_jolika_positions
from backend.market_agenda import MarketAgendaEvent, import_market_agenda
from backend.market_agenda_serializer import serialize_market_agenda
from backend.decision_context import DecisionProfile, import_decision_profile, validate_decision_profile
from backend.decision_context_serializer import serialize_decision_profile
from backend.market_connectors import BcbMarketConnector, ConnectorManager, LocalMarketConnector

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PORT = 8080
SESSION_COOKIE = "argos_session"
logger = logging.getLogger("argos.import.server")


def _log_server_import(message, **details):
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    detail_text = " ".join(
        f"{key}={value!r}" for key, value in sorted(details.items())
    )
    logger.info("%s%s", message, f" {detail_text}" if detail_text else "")


class SessionPortfolio(TypedDict):
    positions: tuple[PortfolioPosition, ...]
    last_import_at: datetime


SESSION_PORTFOLIOS: dict[str, SessionPortfolio] = {}
SESSION_MARKET_AGENDA: dict[str, tuple[MarketAgendaEvent, ...]] = {}
SESSION_DECISION_CONTEXT: dict[str, DecisionProfile] = {}

PORTFOLIO_MARKET_CONNECTOR = MarketConnector(
    providers=[
        FinnhubMarketProvider(),
        TwelveDataMarketProvider(),
    ]
)

DAILY_HTTP_ADAPTER = DailyHttpAdapter(
    DailyApiFacade(
        ubs_intelligence_service=UBSDailyIntelligenceService(
            PORTFOLIO_MARKET_CONNECTOR,
            history_days=252,
        ),
        santander_intelligence_service=SantanderDailyIntelligenceService(
            PORTFOLIO_MARKET_CONNECTOR,
            history_days=252,
        ),
        jolika_intelligence_service=JolikaDailyIntelligenceService(),
    )
)

MARKET_CONNECTOR_MANAGER = ConnectorManager()
MARKET_CONNECTOR_MANAGER.register("BCB", BcbMarketConnector(), active=True)
MARKET_CONNECTOR_MANAGER.register("LOCAL", LocalMarketConnector())
MARKET_CONNECTOR_MANAGER.configure_fallback("BCB", "LOCAL")


def _decode_file_payload(file_payload: Dict[str, str]) -> bytes:
    if not isinstance(file_payload, dict):
        raise ValueError("Payload de arquivo inválido.")

    content = file_payload.get("content")

    if not content:
        raise ValueError("Conteúdo do arquivo não foi enviado.")

    return base64.b64decode(content)


def _save_temp_file(content: bytes, suffix: str) -> Path:
    file_obj = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix
    )

    file_obj.write(content)
    file_obj.flush()
    file_obj.close()

    return Path(file_obj.name)


def legacy_facts_response(dashboard: Dict) -> Dict:
    """Adapt the official dashboard to the retained legacy HTTP contract."""
    return {"ok": True, "facts": dashboard["daily"]["important_facts"]}


def legacy_cockpit_response(dashboard: Dict) -> Dict:
    """Adapt the official dashboard to the retained legacy HTTP contract."""
    return {"ok": True, "cockpit": dashboard}


def analyze_request(data: Dict) -> Dict:
    portfolio = data.get("portfolio")

    if portfolio != "JOLIKA":
        raise ValueError(
            "Somente a análise JOLIKA está disponível nesta release."
        )

    files = data.get("files")

    if not isinstance(files, dict):
        raise ValueError("Formato de arquivos inválido.")

    ubs_payload = files.get("ubs")
    santander_payload = files.get("santander")

    if not ubs_payload or not santander_payload:
        raise ValueError(
            "Os arquivos UBS e Santander são necessários."
        )

    ubs_name = ubs_payload.get("name", "ubs.csv")
    santander_name = santander_payload.get(
        "name",
        "santander.xlsx"
    )

    ubs_bytes = _decode_file_payload(ubs_payload)
    santander_bytes = _decode_file_payload(
        santander_payload
    )

    ubs_path = _save_temp_file(
        ubs_bytes,
        suffix=Path(ubs_name).suffix
    )

    santander_path = _save_temp_file(
        santander_bytes,
        suffix=Path(santander_name).suffix
    )

    try:
        imported = import_portfolios((ubs_path, santander_path))
        return {"ok": True, "result": imported["dashboard"]}

    finally:
        for path in (
            ubs_path,
            santander_path
        ):
            try:
                path.unlink()
            except OSError:
                pass


def inspect_santander_request(data: Dict) -> Dict:
    from backend.connectors.santander_connector import load_positions

    file_payload = data.get("file")
    if not isinstance(file_payload, dict):
        raise ValueError("Payload de arquivo inválido.")
    file_name = file_payload.get("name", "santander.xlsx") \
        if isinstance(file_payload, dict) else "santander.xlsx"
    _log_server_import(
        "Santander inspect request received",
        original_file_name=file_name,
        recognized_by_endpoint=True,
        inspect_excel_export_called=False,
        load_positions_called=True,
    )
    file_path = _save_temp_file(
        _decode_file_payload(file_payload),
        suffix=Path(file_name).suffix,
    )
    try:
        positions = load_positions(file_path)
        _log_server_import(
            "Santander inspect request load_positions returned",
            original_file_name=file_name,
            temp_file_name=file_path.name,
            position_count=len(positions),
            total_market_value=str(
                sum(position.market_value for position in positions)
            ),
            ten_thousand_sources=[
                position.asset_name
                for position in positions
                if position.market_value == Decimal("10000")
            ],
        )
        return {
            "ok": True,
            "source": "Exportação de posições Santander",
            "position_count": len(positions),
        }
    finally:
        try:
            file_path.unlink()
        except OSError:
            pass


class ArgosRequestHandler(
    http.server.SimpleHTTPRequestHandler
):
    def __init__(
        self,
        *args,
        directory: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            *args,
            directory=str(FRONTEND_DIR),
            **kwargs
        )

    def end_headers(self):
        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate"
        )
        self.send_header(
            "Pragma",
            "no-cache"
        )
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/market/status":
            self._send_json(MARKET_CONNECTOR_MANAGER.status())
            return
        if self.path == "/api/decision-context":
            profile = SESSION_DECISION_CONTEXT.get(self._session_id() or "")
            self._send_json({"ok": True, "profile": serialize_decision_profile(profile) if profile else None})
            return
        if self.path == "/api/market-agenda":
            events = SESSION_MARKET_AGENDA.get(self._session_id() or "", ())
            self._send_json({"ok": True, "events": serialize_market_agenda(events), "count": len(events)})
            return
        if self.path == "/api/daily-experience":
            self._daily_experience()
            return
        # Official flow:
        # Dashboard -> DailyOrchestrator -> DailyContextService.
        # Cockpit and facts are compatibility-only projections of Dashboard.
        if self.path == "/api/dashboard":
            try:
                self._send_json(self._dashboard(), status=200)
            except Exception as exc:
                self._send_json(
                    {"error": str(exc)},
                    status=500
                )
            return

        if self.path == "/api/cockpit":
            try:
                self._send_json(legacy_cockpit_response(self._dashboard(False)))
            except Exception as exc:
                self._send_json(
                    {
                        "ok": False,
                        "error": str(exc)
                    },
                    status=500
                )

            return

        if self.path == "/api/facts":
            try:
                self._send_json(legacy_facts_response(self._dashboard(False)))
            except Exception as exc:
                self._send_json(
                    {
                        "ok": False,
                        "error": str(exc)
                    },
                    status=500
                )

            return

        if self.path.startswith("/api/"):
            self.send_error(
                404,
                "Endpoint não encontrado"
            )
            return

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/market/reload":
            try:
                MARKET_CONNECTOR_MANAGER.reload()
                self._send_json(MARKET_CONNECTOR_MANAGER.status())
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=503)
            return
        if self.path == "/api/decision-context/import":
            self._import_decision_context()
            return
        if self.path == "/api/decision-context":
            self._save_decision_context()
            return
        if self.path == "/api/market-agenda/import":
            self._import_market_agenda()
            return
        if self.path == "/api/daily-experience":
            self._daily_experience()
            return
        if self.path == "/api/portfolios/import":
            self._import_portfolios()
            return
        if self.path == "/api/portfolios/paste":
            self._paste_portfolio()
            return

        handlers = {
            # Compatibility only: delegates to the official import/dashboard flow.
            "/api/analyze": analyze_request,
            "/api/santander/inspect": inspect_santander_request,
        }
        if self.path not in handlers:
            self.send_error(
                404,
                "Endpoint não encontrado"
            )
            return

        try:
            content_length = self._content_length()
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return

        raw_body = self.rfile.read(
            content_length
        )

        try:
            payload = json.loads(
                raw_body.decode("utf-8")
            )
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": (
                        f"Corpo JSON inválido: {exc}"
                    )
                },
                status=400
            )
            return

        try:
            response = handlers[self.path](payload)
            self._send_json(response, status=200)
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=400
            )

    def do_PUT(self):
        if self.path == "/api/daily-experience":
            self._daily_experience()
            return
        self.send_error(501, "Unsupported method")

    def _daily_experience(self) -> None:
        market_facts = MARKET_CONNECTOR_MANAGER.load_facts()
        market_agenda = self._session_agenda()
        session_positions = self._session_positions()
        try:
            content_length = self._content_length()
        except ValueError:
            content_length = -1
        if content_length < 0:
            response = DAILY_HTTP_ADAPTER.handle(
                self.command, dict(self.headers), b"", market_agenda, self._session_decision_profile(),
                session_positions,
                market_facts,
            )
        elif content_length > MAX_DAILY_REQUEST_BYTES:
            response = DAILY_HTTP_ADAPTER.handle(
                self.command,
                dict(self.headers),
                b" " * (MAX_DAILY_REQUEST_BYTES + 1),
                market_agenda,
                self._session_decision_profile(),
                session_positions,
                market_facts,
            )
        else:
            body = self.rfile.read(content_length)
            response = DAILY_HTTP_ADAPTER.handle(
                self.command, dict(self.headers), body, market_agenda, self._session_decision_profile(),
                session_positions,
                market_facts,
            )
        self.send_response(response.status_code)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_DELETE(self):
        if self.path == "/api/decision-context":
            session_id = self._session_id()
            if session_id:
                SESSION_DECISION_CONTEXT.pop(session_id, None)
            self._send_json({"ok": True, "profile": None})
            return
        if self.path == "/api/market-agenda":
            session_id = self._session_id()
            if session_id:
                SESSION_MARKET_AGENDA.pop(session_id, None)
            self._send_json({"ok": True, "events": [], "count": 0})
            return
        if self.path != "/api/portfolios":
            self.send_error(404, "Endpoint não encontrado")
            return

        session_id = self._session_id()
        if session_id:
            SESSION_PORTFOLIOS.pop(session_id, None)
        self._send_json({
            "ok": True,
            "dashboard": build_dashboard(()),
            "positions": [],
        })

    def _session_id(self) -> str | None:
        cookie = self.headers.get("Cookie", "")
        for item in cookie.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == SESSION_COOKIE and value:
                return value
        return None

    def _content_length(self) -> int:
        """Return a validated request length, treating an empty header as no body."""
        raw_value = self.headers.get("Content-Length")
        value = raw_value.strip() if raw_value is not None else ""
        if not value:
            return 0
        if not value.isdecimal():
            raise ValueError("Content-Length deve ser um número inteiro não negativo.")
        return int(value)

    def _session_agenda(self) -> tuple[MarketAgendaEvent, ...]:
        return SESSION_MARKET_AGENDA.get(self._session_id() or "", ())

    def _session_decision_profile(self) -> DecisionProfile | None:
        return SESSION_DECISION_CONTEXT.get(self._session_id() or "")

    def _session_portfolio(self) -> SessionPortfolio | None:
        session_id = self._session_id()
        if not session_id:
            return None
        return SESSION_PORTFOLIOS.get(session_id)

    def _session_positions(self) -> tuple[PortfolioPosition, ...]:
        portfolio = self._session_portfolio()
        return portfolio["positions"] if portfolio is not None else ()

    def _dashboard(self, include_positions: bool = True):
        portfolio = self._session_portfolio()
        positions = portfolio["positions"] if portfolio is not None else ()
        last_import_at = (
            portfolio["last_import_at"] if portfolio is not None else None
        )
        dashboard = build_dashboard(positions, last_import_at=last_import_at)
        if include_positions:
            dashboard["positions"] = serialize_portfolio_positions(positions)
        return dashboard

    def _multipart_files(self) -> list[tuple[str, bytes]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            raise ValueError("Use multipart/form-data para enviar os arquivos.")
        content_length = self._content_length()
        if content_length <= 0:
            raise ValueError("Envie ao menos um arquivo para importação.")
        body = self.rfile.read(content_length)
        message = BytesParser(policy=email_policy).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
            + body
        )
        files: list[tuple[str, bytes]] = []
        for part in message.iter_parts():
            file_name = part.get_filename()
            if part.get_content_disposition() != "form-data" or not file_name:
                continue
            # The email API's overload does not narrow decode=True, although it
            # returns bytes for the binary multipart payload accepted here.
            content = cast(bytes, part.get_payload(decode=True))
            files.append((file_name, content))
        return files

    def _paste_portfolio(self):
        try:
            content_length = self._content_length()
            if content_length <= 0:
                raise ValueError("Cole uma carteira antes de continuar.")

            payload = json.loads(
                self.rfile.read(content_length).decode("utf-8")
            )

            if not isinstance(payload, dict):
                raise ValueError("Dados da carteira inválidos.")

            text = payload.get("text")
            owner_value = payload.get("owner")

            if not isinstance(text, str) or not text.strip():
                raise ValueError("Cole uma carteira antes de continuar.")

            try:
                owner = PortfolioOwner(owner_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Titular da carteira inválido.") from exc

            positions = parse_pasted_portfolio(
                text,
                owner=owner,
            )

            if owner is PortfolioOwner.JOLIKA:
                positions = resolve_jolika_positions(
                    classify_jolika_positions(positions)
                )

            imported_institutions = {
                position.institution for position in positions
            }

            session_id = self._session_id() or secrets.token_urlsafe(24)
            imported_at = datetime.now(timezone.utc)

            current_session = SESSION_PORTFOLIOS.get(session_id)
            current_positions = (
                current_session["positions"]
                if current_session is not None
                else ()
            )

            preserved_positions = tuple(
                position
                for position in current_positions
                if position.institution not in imported_institutions
            )

            session_positions = preserved_positions + tuple(positions)

            SESSION_PORTFOLIOS[session_id] = {
                "positions": session_positions,
                "last_import_at": imported_at,
            }

            dashboard = build_dashboard(
                session_positions,
                last_import_at=imported_at,
            )

            self._send_json(
                {
                    "ok": True,
                    "source": "pasted",
                    "dashboard": dashboard,
                    "positions": serialize_portfolio_positions(
                        session_positions
                    ),
                },
                status=200,
                extra_headers={
                    "Set-Cookie": (
                        f"{SESSION_COOKIE}={session_id}; Path=/; "
                        "HttpOnly; SameSite=Strict"
                    )
                },
            )

        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "dashboard": build_dashboard(()),
                    "positions": [],
                },
                status=400,
            )

    def _import_portfolios(self):
        paths = []
        with tempfile.TemporaryDirectory() as directory:
            try:
                for index, (file_name, content) in enumerate(
                    self._multipart_files()
                ):
                    safe_name = Path(file_name).name
                    upload_directory = Path(directory) / str(index)
                    upload_directory.mkdir()
                    path = upload_directory / safe_name
                    path.write_bytes(content)
                    paths.append(path)

                result = import_portfolios(paths)
                session_id = self._session_id() or secrets.token_urlsafe(24)
                imported_at = datetime.now(timezone.utc)
                imported_positions = cast(
                    tuple[PortfolioPosition, ...], result.pop("positions")
                )
                imported_institutions = {
                    position.institution for position in imported_positions
                }
                current_session = SESSION_PORTFOLIOS.get(session_id)
                current_positions = (
                    current_session["positions"] if current_session is not None else ()
                )
                preserved_positions = tuple(
                    position for position in current_positions
                    if position.institution not in imported_institutions
                )
                SESSION_PORTFOLIOS[session_id] = {
                    "positions": preserved_positions + imported_positions,
                    "last_import_at": imported_at,
                }
                result["dashboard"] = build_dashboard(
                    SESSION_PORTFOLIOS[session_id]["positions"],
                    last_import_at=imported_at,
                )
                result["positions"] = serialize_portfolio_positions(
                    SESSION_PORTFOLIOS[session_id]["positions"]
                )
                self._send_json(
                    {"ok": True, **result},
                    status=200,
                    extra_headers={
                        "Set-Cookie": (
                            f"{SESSION_COOKIE}={session_id}; Path=/; "
                            "HttpOnly; SameSite=Strict"
                        )
                    },
                )
            except Exception as exc:
                session_id = self._session_id()
                if session_id:
                    SESSION_PORTFOLIOS.pop(session_id, None)
                empty_dashboard = build_dashboard(())
                self._send_json({
                    "ok": False,
                    "error": str(exc),
                    "dashboard": empty_dashboard,
                    "positions": [],
                }, status=400)

    def _import_market_agenda(self) -> None:
        try:
            files = self._multipart_files()
            if len(files) != 1:
                raise ValueError("Envie exatamente um arquivo de agenda.")
            events = import_market_agenda(*files[0])
            session_id = self._session_id() or secrets.token_urlsafe(24)
            SESSION_MARKET_AGENDA[session_id] = events
            self._send_json(
                {"ok": True, "events": serialize_market_agenda(events),
                 "count": len(events), "diagnostics": []},
                extra_headers={"Set-Cookie": (
                    f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Strict"
                )},
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)


    def _save_decision_context(self) -> None:
        try:
            content_length = self._content_length()
            if content_length <= 0:
                raise ValueError("Envie o perfil do investidor em JSON.")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"profile"}:
                raise ValueError("JSON deve conter somente o objeto profile.")
            profile = validate_decision_profile(payload["profile"])
            session_id = self._session_id() or secrets.token_urlsafe(24)
            SESSION_DECISION_CONTEXT[session_id] = profile
            self._send_json(
                {"ok": True, "profile": serialize_decision_profile(profile), "diagnostics": []},
                extra_headers={"Set-Cookie": (
                    f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Strict"
                )},
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _import_decision_context(self) -> None:
        try:
            files = self._multipart_files()
            if len(files) != 1:
                raise ValueError("Envie exatamente um arquivo de contexto decisório.")
            profile = import_decision_profile(*files[0])
            session_id = self._session_id() or secrets.token_urlsafe(24)
            SESSION_DECISION_CONTEXT[session_id] = profile
            self._send_json(
                {"ok": True, "profile": serialize_decision_profile(profile), "diagnostics": []},
                extra_headers={"Set-Cookie": (
                    f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Strict"
                )},
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _send_json(
        self,
        data: Dict,
        status: int = 200,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        response_body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)

        self.send_header(
            "Content-Length",
            str(len(response_body))
        )

        self.end_headers()
        self.wfile.write(response_body)


if __name__ == "__main__":
    os.chdir(str(FRONTEND_DIR))

    with socketserver.TCPServer(
        ("localhost", PORT),
        ArgosRequestHandler
    ) as httpd:
        print(
            f"ARGOS server running at "
            f"http://localhost:{PORT}"
        )

        print(
            "Serving frontend, /api/dashboard, "
            "/api/cockpit, /api/facts and /api/analyze"
        )

        httpd.serve_forever()
