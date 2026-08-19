"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { InstitutionAnalysis } = require("./institution_analysis.js");
const helpers = InstitutionAnalysis._test;

function installWindow({ profile, dashboard, importStatus } = {}) {
    const originalWindow = global.window;
    const storage = new Map();
    if (profile !== undefined) storage.set("argos.investor-profile", JSON.stringify({ profile }));
    if (importStatus !== undefined) storage.set("argos.institution-import-status", JSON.stringify(importStatus));
    global.window = {
        localStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, value); }
        }
    };
    if (dashboard !== undefined) helpers.setDashboardForTest(dashboard);
    return () => {
        helpers.setDashboardForTest(null);
        global.window = originalWindow;
    };
}

function validProfile(overrides = {}) {
    return {
        profile_name: "Perfil teste",
        risk_level: "MODERATE",
        investment_horizon: "LONG_TERM",
        liquidity_needs: "MODERATE",
        capital_preservation_level: "MODERATE",
        review_date: "2027-08-05",
        ...overrides
    };
}

function completeInstitution(overrides = {}) {
    return {
        name: "Santander",
        position_count: 3,
        currencies: ["BRL"],
        totals_by_currency: { BRL: 1000 },
        warnings: [],
        asset_symbols: ["AAA", "BBB", "CCC"],
        intelligence: {
            portfolio_reading:
                "A carteira está bem distribuída e, no momento, não há nenhum ponto estrutural dominante.",
            priority: {
                level: "Baixa",
                reasons: []
            },
            materiality: {
                level: "Baixa",
                max_position_weight: "0.20",
                driver: null
            },
            diversification: {
                level: "Alta",
                asset_hhi: "0.20",
                class_hhi: "0.20",
                driver: null
            },
            coverage: {
                consolidated_asset_count: 3,
                assets_with_economic_class: 3
            },
            concentration_by_currency: [{
                currency: "BRL",
                top_1_weight: "0.20"
            }],
            duplicate_exposures: []
        },
        ...overrides
    };
}

const fullDashboard = {
    daily: {
        lookback_hours: 24,
        important_facts: [{
            title: "Juros locais",
            context_type: "macro",
            context: "macro",
            summary: "curva de juros abriu no dia",
            source: "Boletim diário"
        }],
        analyses: [{
            title: "Tese de crédito",
            status: "carteira macro",
            related_to: "AAA",
            reason: "spreads seguem sob acompanhamento",
            confidence: "média"
        }]
    },
    consolidated: { repeated_asset_count: 0 }
};

test("blocks conclusions when institution import is incomplete", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: fullDashboard });
    try {
        const institution = completeInstitution({ position_count: 0, currencies: [], totals_by_currency: {}, warnings: ["Carteira ainda não carregada para esta instituição."] });
        assert.equal(helpers.isImportIncomplete(institution), true);
        assert.match(helpers.buildSummary(institution), /Dados insuficientes/);
        assert.match(helpers.attentionItems(institution)[0].description, /importação.*incompleta/i);
        assert.match(helpers.riskItems(institution)[0].title, /Dados insuficientes/);
        assert.match(helpers.favorableItems(institution)[0].title, /Dados insuficientes/);
    } finally { restore(); }
});

test("blocks diagnosis when investor profile is absent", () => {
    const restore = installWindow({ dashboard: fullDashboard });
    try {
        assert.match(helpers.buildSummary(completeInstitution()), /Perfil Estratégico obrigatório/);
        assert.match(helpers.attentionItems(completeInstitution())[0].title, /Perfil Estratégico obrigatório/);
    } finally { restore(); }
});

test("blocks diagnosis when investor profile review is over one year old or expired", () => {
    const restore = installWindow({ profile: validProfile({ review_date: "2025-08-04" }), dashboard: fullDashboard });
    try {
        assert.equal(helpers.isProfileValid(helpers.investorProfile(), new Date("2026-08-05T00:00:00Z")), false);
        assert.match(helpers.buildSummary(completeInstitution()), /dentro do prazo de revisão anual/);
        assert.match(helpers.attentionItems(completeInstitution())[0].title, /vencido/);
    } finally { restore(); }
});

test("uses evidence-based diagnosis wording after complete import and valid profile", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: fullDashboard });
    try {
        const summary = helpers.buildSummary(completeInstitution());
        assert.match(summary, /Leitura:/);
        assert.match(summary, /não há nenhum ponto estrutural dominante/i);
        assert.match(summary, /Inferência:/);
        assert.match(summary, /Evidência:/);
        assert.doesNotMatch(summary, /motor/i);
        assert.doesNotMatch(summary, /comprar|vender/i);
    } finally { restore(); }
});

test("absence of macro data lowers confidence and blocks public projection", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: { daily: { important_facts: [], analyses: [], lookback_hours: 24 } } });
    try {
        const projection = helpers.buildHealthReport(completeInstitution()).projection[0].description;
        assert.match(
            projection,
            /não publica uma faixa de retorno/i
        );
        assert.match(
            helpers.riskItems(completeInstitution()).map((item) => item.description).join(" "),
            /cenário macroeconômico atual ainda não está disponível/
        );
    } finally { restore(); }
});

test("absence of asset data is declared clearly", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: { daily: { important_facts: [{ context_type: "macro", summary: "macro atual" }], analyses: [] } } });
    try {
        const institution = completeInstitution({ asset_symbols: [] });
        assert.match(helpers.favorableItems(institution)[0].title, /sem evidência suficiente/i);
        assert.match(helpers.buildHealthReport(institution).attention.at(-1).description, /Faltam dados atuais dos ativos/);
    } finally { restore(); }
});

test("does not publish fixed 12-month return ranges without quantitative modelling", () => {
    const restore = installWindow({
        profile: validProfile(),
        dashboard: fullDashboard
    });

    try {
        const text = helpers
            .buildHealthReport(completeInstitution())
            .projection[0]
            .description;

        assert.match(text, /modelagem quantitativa da carteira/);
        assert.match(text, /não publica uma faixa de retorno/i);
        assert.doesNotMatch(text, /-3%|0% a 4%|5% a 9%|6% a 12%|13% a 18%/);
    } finally {
        restore();
    }
});

test("prohibits buy and sell recommendation language in visible diagnosis", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: fullDashboard });
    try {
        const report = helpers.buildHealthReport(completeInstitution({ position_count: 1, asset_symbols: ["AAA"] }));
        const visible = JSON.stringify(report);
        assert.doesNotMatch(visible, /recomendação de compra|recomendação de venda|comprar|vender|produto específico/i);
        assert.match(visible, /sem ordem de execução|Não há ordem de execução/i);
    } finally { restore(); }
});

test("all executive conclusions include traceable evidence and fact-inference separation", () => {
    const restore = installWindow({ profile: validProfile(), dashboard: fullDashboard });
    try {
        const report = helpers.buildHealthReport(completeInstitution());
        const items = [...report.attention, ...report.risks, ...report.theses, ...report.changes];
        assert.ok(items.length > 0);
        items.forEach((item) => {
            assert.match(item.description, /Fato:/);
            assert.match(item.description, /Inferência:/);
            assert.match(item.description, /Evidência:|Fonte:/);
            assert.match(item.description, /Confiança:/);
        });
    } finally { restore(); }
});

test("uses strategic profile to identify liquidity and currency mismatch", () => {
    const restore = installWindow({ profile: validProfile({ risk_level: "LOW", liquidity_needs: "HIGH", capital_preservation_level: "CRITICAL" }), dashboard: fullDashboard });
    try {
        const institution = completeInstitution({
            position_count: 2,
            currencies: ["BRL", "USD"],
            asset_symbols: ["AAA", "BBB"],
            intelligence: {
                portfolio_reading:
                    "A carteira está concentrada em poucos ativos e isso merece mais atenção agora.",
                priority: {
                    level: "Alta",
                    reasons: ["concentration"]
                },
                materiality: {
                    level: "Alta",
                    max_position_weight: "0.70",
                    driver: "concentration"
                },
                diversification: {
                    level: "Baixa",
                    asset_hhi: "0.58",
                    class_hhi: "0.58",
                    driver: "asset_and_class_concentration"
                },
                coverage: {
                    consolidated_asset_count: 2,
                    assets_with_economic_class: 2
                },
                concentration_by_currency: [{
                    currency: "BRL",
                    top_1_weight: "0.70"
                }],
                duplicate_exposures: []
            }
        });

        const risks = helpers.riskItems(institution)
            .map((item) => item.description)
            .join(" ");

        assert.match(risks, /70\.0% da moeda mais concentrada/);
        assert.match(risks, /efeito cambial merece ser acompanhado/);
        assert.match(
            helpers.buildSummary(institution),
            /análise mais aprofundada/
        );
    } finally { restore(); }
});



test("does not call a many-position portfolio fragmented without structural evidence", () => {
    const restore = installWindow({
        profile: validProfile(),
        dashboard: fullDashboard
    });

    try {
        const institution = completeInstitution({
            position_count: 40,
            asset_symbols: Array.from(
                { length: 40 },
                (_, index) => `A${index + 1}`
            ),
            intelligence: {
                portfolio_reading:
                    "A carteira está bem distribuída e, no momento, não há nenhum ponto estrutural dominante.",
                priority: {
                    level: "Baixa",
                    reasons: []
                },
                materiality: {
                    level: "Baixa",
                    max_position_weight: "0.05",
                    driver: null
                },
                diversification: {
                    level: "Alta",
                    asset_hhi: "0.025",
                    class_hhi: "0.20",
                    driver: null
                },
                coverage: {
                    consolidated_asset_count: 40,
                    assets_with_economic_class: 40
                },
                concentration_by_currency: [{
                    currency: "BRL",
                    top_1_weight: "0.05"
                }],
                duplicate_exposures: []
            }
        });

        const visible = JSON.stringify(
            helpers.buildHealthReport(institution)
        );

        assert.doesNotMatch(
            visible,
            /fragmentação excessiva|fragmentada/i
        );
        assert.doesNotMatch(
            visible,
            /concentração elevada/i
        );
    } finally {
        restore();
    }
});


test("does not call a few-position portfolio concentrated without dominant weight", () => {
    const restore = installWindow({
        profile: validProfile(),
        dashboard: fullDashboard
    });

    try {
        const institution = completeInstitution({
            position_count: 3,
            asset_symbols: ["AAA", "BBB", "CCC"],
            intelligence: {
                portfolio_reading:
                    "A carteira está bem distribuída e, no momento, não há nenhum ponto estrutural dominante.",
                priority: {
                    level: "Baixa",
                    reasons: []
                },
                materiality: {
                    level: "Baixa",
                    max_position_weight: "0.20",
                    driver: null
                },
                diversification: {
                    level: "Alta",
                    asset_hhi: "0.25",
                    class_hhi: "0.25",
                    driver: null
                },
                coverage: {
                    consolidated_asset_count: 3,
                    assets_with_economic_class: 3
                },
                concentration_by_currency: [{
                    currency: "BRL",
                    top_1_weight: "0.20"
                }],
                duplicate_exposures: []
            }
        });

        const visible = JSON.stringify(
            helpers.buildHealthReport(institution)
        );

        assert.doesNotMatch(
            visible,
            /concentração elevada|poucos ativos.*atenção/i
        );
    } finally {
        restore();
    }
});
