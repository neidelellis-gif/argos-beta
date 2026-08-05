
import json
from http import HTTPStatus

from backend import server
from tests.test_decision_context import profile_data


def test_save_decision_context_from_first_access_json(monkeypatch):
    captured = {}

    class Handler:
        headers = {"Content-Length": "0"}
        rfile = None

        def _content_length(self):
            return len(self.body)

        def _session_id(self):
            return "session-42"

        def _send_json(self, data, status=HTTPStatus.OK, extra_headers=None):
            captured["data"] = data
            captured["status"] = status
            captured["extra_headers"] = extra_headers

    payload = json.dumps({"profile": profile_data(profile_id="investor-first-access")}).encode()
    handler = Handler()
    handler.body = payload
    handler.rfile = type("Reader", (), {"read": lambda self, length: payload})()

    server.ArgosRequestHandler._save_decision_context(handler)

    assert captured["status"] == HTTPStatus.OK
    assert captured["data"]["ok"] is True
    assert captured["data"]["profile"]["profile_id"] == "investor-first-access"
    assert server.SESSION_DECISION_CONTEXT["session-42"].profile_id == "investor-first-access"
