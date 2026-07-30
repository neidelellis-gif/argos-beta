import base64
from email.parser import BytesParser
from email.policy import default as email_policy
import http.server
import json
import os
import secrets
import socketserver
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, TypedDict, cast

from backend.models import PortfolioPosition

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.dashboard import build_dashboard, load_dashboard
from backend.daily_http import DailyHttpAdapter, MAX_DAILY_REQUEST_BYTES
from backend.portfolio_import import import_portfolios

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PORT = 8080
SESSION_COOKIE = "argos_session"

class SessionPortfolio(TypedDict):
    positions: tuple[PortfolioPosition, ...]
    last_import_at: datetime


SESSION_PORTFOLIOS: dict[str, SessionPortfolio] = {}
DAILY_HTTP_ADAPTER = DailyHttpAdapter()


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
    file_path = _save_temp_file(
        _decode_file_payload(file_payload),
        suffix=Path(file_name).suffix,
    )
    try:
        positions = load_positions(file_path)
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
                self._send_json(legacy_cockpit_response(self._dashboard()))
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
                self._send_json(legacy_facts_response(self._dashboard()))
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
        if self.path == "/api/daily-experience":
            self._daily_experience()
            return
        if self.path == "/api/portfolios/import":
            self._import_portfolios()
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

        content_length = int(
            self.headers.get(
                "Content-Length",
                0
            )
        )

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
        content_length_value = self.headers.get("Content-Length")
        try:
            content_length = int(content_length_value or "0")
        except ValueError:
            content_length = -1
        if content_length < 0:
            response = DAILY_HTTP_ADAPTER.handle(
                self.command, dict(self.headers), b""
            )
        elif content_length > MAX_DAILY_REQUEST_BYTES:
            response = DAILY_HTTP_ADAPTER.handle(
                self.command,
                dict(self.headers),
                b" " * (MAX_DAILY_REQUEST_BYTES + 1),
            )
        else:
            body = self.rfile.read(content_length)
            response = DAILY_HTTP_ADAPTER.handle(
                self.command, dict(self.headers), body
            )
        self.send_response(response.status_code)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_DELETE(self):
        if self.path != "/api/portfolios":
            self.send_error(404, "Endpoint não encontrado")
            return

        session_id = self._session_id()
        if session_id:
            SESSION_PORTFOLIOS.pop(session_id, None)
        self._send_json({"ok": True, "dashboard": build_dashboard(())})

    def _session_id(self) -> str | None:
        cookie = self.headers.get("Cookie", "")
        for item in cookie.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == SESSION_COOKIE and value:
                return value
        return None

    def _dashboard(self):
        session_id = self._session_id()
        session = SESSION_PORTFOLIOS.get(session_id) if session_id is not None else None
        positions = session.get("positions") if session is not None else None
        last_import_at = session.get("last_import_at") if session is not None else None
        return (
            load_dashboard()
            if positions is None
            else build_dashboard(positions, last_import_at=last_import_at)
        )

    def _multipart_files(self) -> list[tuple[str, bytes]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            raise ValueError("Use multipart/form-data para enviar os arquivos.")
        content_length = int(self.headers.get("Content-Length", 0))
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
