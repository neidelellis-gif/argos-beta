# Hipóteses do gestor — não são dados de mercado nem projeções do ARGOS.
# Os valores de retorno são hipóteses de trabalho revisáveis pelo gestor a cada release.

META_BASE = 12.0  # % a.a. — meta-base da JOLIKA (definida em AGENTS.md)

BLOCK_ASSUMPTIONS = {
    "Caixa": {
        "return_low": 0.0,
        "return_high": 1.0,
        "function": "Reserva de liquidez imediata. Não gera retorno relevante.",
    },
    "Caixa Remunerado": {
        "return_low": 4.0,
        "return_high": 5.5,
        "function": "Liquidez com geração de renda. Sensível à taxa de juros americana.",
    },
    "Renda Fixa": {
        "return_low": 5.0,
        "return_high": 8.0,
        "function": "Âncora de renda previsível. Amortece volatilidade do portfólio.",
    },
    "ETF": {
        "return_low": 8.0,
        "return_high": 15.0,
        "function": "Exposição diversificada a mercados. Alta variância entre mandatos.",
    },
    "Ação": {
        "return_low": 10.0,
        "return_high": 20.0,
        "function": "Potencial de valorização de longo prazo. Maior volatilidade.",
    },
    "Fundo": {
        "return_low": 6.0,
        "return_high": 12.0,
        "function": "Gestão ativa ou temática. Retorno depende do mandato específico.",
    },
    "Alternativos": {
        "return_low": 7.0,
        "return_high": 13.0,
        "function": "Descorrelação e retorno absoluto. Baixa liquidez.",
    },
}
