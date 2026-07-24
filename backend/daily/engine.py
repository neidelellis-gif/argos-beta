from datetime import datetime


def get_daily_status():
    return {
        "generated_at": datetime.now().isoformat(),
        "system": "operacional",
        "market": "pendente",
        "portfolios": "pendente",
        "intelligence": "pendente",
        "agenda": "pendente",
        "next_action": "Receber os arquivos das instituições."
    }