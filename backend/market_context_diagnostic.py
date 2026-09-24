"""Diagnostico manual das fontes publicas usadas pela Etapa 4."""

from datetime import datetime, timedelta, timezone

from backend.jolika_market_context_analysis import build_market_context_stage
from backend.jolika_market_fact_sources import load_market_context_facts
from backend.public_market_news_provider import (
    BEA_NEWS_RSS,
    FED_MONETARY_RSS,
    SEC_PRESS_RSS,
    PublicMarketNewsProvider,
)


def main() -> None:
    provider = PublicMarketNewsProvider(timeout_seconds=3.0)
    reference = datetime.now(timezone.utc)
    recent_cutoff = reference - timedelta(hours=24)
    macro_cutoff = reference - timedelta(days=45)
    sources = (
        (FED_MONETARY_RSS, "Federal Reserve", True),
        (BEA_NEWS_RSS, "BEA", True),
        (SEC_PRESS_RSS, "SEC", False),
    )

    try:
        bls_items = provider._fetch_bls_api(reference)
        print(f"BLS API: acesso=OK series={len(bls_items)}")
        for item in bls_items:
            print(f"  - {item.occurred_at.isoformat()} | {item.title} | {item.summary}")
    except Exception as exc:
        print(f"BLS API: acesso=FALHOU erro={type(exc).__name__}: {exc}")

    total = 0
    for url, source, macro in sources:
        try:
            payload = provider._read(url)
            parsed = provider._parse_feed(payload, source, (), macro)
            cutoff = macro_cutoff if macro else recent_cutoff
            accepted = tuple(
                item for item in parsed
                if cutoff <= item.occurred_at <= reference
            )
            total += len(accepted)
            print(
                f"{source}: acesso=OK lidos={len(parsed)} "
                f"aceitos_{'45d_macro' if macro else '24h_eventos'}={len(accepted)}"
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
    canonical = load_market_context_facts((), (), provider, now=reference)
    stage = build_market_context_stage((), canonical)
    print(f"CANONICOS total={len(canonical)} fontes={sorted({fact.source for fact in canonical})}")
    print(f"ETAPA4 status={stage.status} itens={len(stage.items)}")
    for item in stage.items:
        print(f"  - bloco={item.title} leitura={item.reading}")
    print(
        f"RESULTADO status={result.status} fatos_aceitos={len(result.items)} "
        f"erros={result.error or 'nenhum'} total_fontes_aceitas={total}"
    )


if __name__ == "__main__":
    main()
