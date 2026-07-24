from datetime import datetime


def get_global_overview():
    return {
        "generated_at": datetime.now().isoformat(),
        "status": "pending",
        "summary": "Panorama global ainda não atualizado.",
        "markets": {
            "usa": "Pendente",
            "brazil": "Pendente",
            "crypto": "Pendente",
            "rates": "Pendente"
        },
        "events": [],
        "highlights": []
    }