"""Diagnostico manual das fontes publicas usadas pela Etapa 4."""

import logging
from datetime import datetime, timezone

from backend.public_market_news_provider import PublicMarketNewsProvider


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    provider = PublicMarketNewsProvider(timeout_seconds=3.0)
    result = provider.fetch_facts(datetime.now(timezone.utc), ())
    print(f"RESULTADO status={result.status.value} fatos_aceitos={len(result.items)}")
    for item in result.items:
        print(f"FATO fonte={item.source} data={item.occurred_at.isoformat()} titulo={item.title}")


if __name__ == "__main__":
    main()
