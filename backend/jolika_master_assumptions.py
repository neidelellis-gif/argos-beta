"""Official, versioned JOLIKA master assumptions used by ARGOS.

This module is a source of approved policy only. It contains no portfolio
analysis logic so the reference remains independent from its interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JolikaMasterAssumption:
    key: str
    title: str
    text: str


JOLIKA_MASTER_ASSUMPTIONS_VERSION = "1.0"
JOLIKA_MASTER_ASSUMPTIONS_APPROVED_ON = "2026-09-08"
JOLIKA_MASTER_ASSUMPTIONS_SOURCE = "docs/jolika/PREMISSAS_MESTRES_JOLIKA_v1.0.md"

JOLIKA_MASTER_ASSUMPTIONS = (
    JolikaMasterAssumption(
        key="patrimonial_objective",
        title="Objetivo Patrimonial",
        text=(
            "Preservar e ampliar o patrimônio da JOLIKA em termos reais ao longo do tempo, "
            "buscando retorno consistente e compatível com o risco assumido, sem depender de "
            "concentração excessiva em um único ativo, emissor, instituição, classe ou tese de investimento."
        ),
    ),
    JolikaMasterAssumption(
        key="expected_return",
        title="Retorno Esperado",
        text=(
            "A JOLIKA adota 12% ao ano em USD como meta-base de referência, e não como limite "
            "superior ou obrigação rígida de resultado. Retornos superiores são desejáveis quando "
            "decorrentes da seleção de teses de alta convicção, assimetrias favoráveis ou oportunidades "
            "de mercado, desde que o risco adicional seja identificado, compreendido e compatível com "
            "os objetivos patrimoniais da JOLIKA. Retornos inferiores à meta em determinados períodos "
            "não constituem, isoladamente, falha da estratégia; resultado, risco, qualidade das teses e "
            "ambiente de mercado devem ser avaliados em conjunto."
        ),
    ),
    JolikaMasterAssumption(
        key="acceptable_risk",
        title="Risco Aceitável",
        text=(
            "A JOLIKA aceita riscos e volatilidade acima da média quando houver potencial de retorno "
            "proporcionalmente superior. O risco deve ser controlado principalmente pela qualidade das "
            "teses, diversificação e prevenção de perdas permanentes relevantes de capital."
        ),
    ),
    JolikaMasterAssumption(
        key="allocation_diversification",
        title="Alocação e Diversificação",
        text=(
            "A JOLIKA deve manter uma carteira diversificada entre classes, setores, geografias e teses, "
            "evitando concentrações que possam comprometer o patrimônio. A diversificação deve reduzir "
            "riscos sem diluir excessivamente as melhores oportunidades."
        ),
    ),
    JolikaMasterAssumption(
        key="decision_rules",
        title="Regras de Decisão",
        text=(
            "As decisões da JOLIKA devem ser orientadas pela qualidade e evolução das teses, relação "
            "risco-retorno e impacto sobre a carteira como um todo. Preço, desempenho passado ou "
            "movimentos de curto prazo nunca devem ser avaliados isoladamente."
        ),
    ),
)


def get_jolika_master_assumptions() -> tuple[JolikaMasterAssumption, ...]:
    """Return the immutable approved reference in official order."""

    return JOLIKA_MASTER_ASSUMPTIONS
