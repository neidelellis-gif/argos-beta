import http.client
import json
import threading
from datetime import date
from decimal import Decimal
from http.server import ThreadingHTTPServer

from backend.models import PortfolioOwner, PortfolioPosition
from backend.server import ArgosRequestHandler, SESSION_PORTFOLIOS


def _nei_position() -> PortfolioPosition:
    return PortfolioPosition(
        institution="Bradesco",
        owner=PortfolioOwner.NEI,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name="NEI1",
        identifier="NEI1",
        identifier_type="ticker",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency="BRL",
        portfolio_weight=Decimal("100"),
        reference_date=date(2026, 7, 28),
        source_file="bradesco.csv",
    )


def test_jolika_consolidation_rejects_nei_only_session():
    SESSION_PORTFOLIOS.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        session_id = "nei-only-consolidation-test"
        SESSION_PORTFOLIOS[session_id] = {
            "positions": (_nei_position(),),
            "last_import_at": None,
            "completed_institutions": (),
            "consolidation_authorized": False,
        }

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/api/portfolios/consolidate",
            headers={"Cookie": f"argos_session={session_id}"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

        assert response.status == 400
        assert payload["ok"] is False
        assert "JOLIKA" in payload["error"]
        assert SESSION_PORTFOLIOS[session_id]["consolidation_authorized"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        SESSION_PORTFOLIOS.clear()
