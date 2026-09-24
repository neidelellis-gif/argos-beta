"""Diagnostico manual das fontes publicas usadas pela Etapa 4."""

from datetime import datetime, timedelta, timezone

from backend.public_market_news_provider import (
    BEA_NEWS_RSS,
    BLS_LATEST_RSS,
    FED_MONETARY_RSS,
    SEC_PRESS_RSS,
    PublicMarketNewsProvider,
)


def main() -> None:
    provider = PublicMarketNewsProvider(timeout_seconds=3.0)
    reference = datetime.now(timezone.utc)
    cutoff = reference - timedelta(hours=48)
    sources = (
        (FED_MONETARY_RSS, "Federal Reserve", True),
        (BLS_LATEST_RSS, "BLS", True),
        (BEA_NEWS_RSS, "BEA", True),
        (SEC_PRESS_RSS, "SEC", False),
    )

    total = 0
    for url, source, macro in sources:
        try:
            payload = provider._read(url)
            parsed = provider._parse_feed(payload, source, (), macro)
            accepted = tuple(
                item for item in parsed
                if cutoff <= item.occurred_at <= reference
            )
            total += len(accepted)
            print(
                f"{source}: acesso=OK lidos={len(parsed)} "
                f"aceitos_48h={len(accepted)}"
            )
            for item in accepted[:5]:
                print(
                    f"  - {item.occurred_at.isoformat()} | "
                    f"{item.title}"
                )
        except Exception as exc:
            print(
                f"{source}: acesso=FALHOU erro={type(exc).__name__}: {exc}"
            )

    result = provider.fetch_facts(reference, ())
    print(
        f"RESULTADO status={result.status} fatos_aceitos={len(result.items)} "
        f"erros={result.error or 'nenhum'} total_fontes_48h={total}"
    )


if __name__ == "__main__":
    main()
