"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { InstitutionAnalysis } = require("./institution_analysis.js");
const helpers = InstitutionAnalysis._test;

function withInvestorProfile(callback, profile = {}) {
    const originalWindow = global.window;
    const stored = JSON.stringify({
        profile: {
            profile_name: "Perfil teste",
            risk_level: "MODERATE",
            investment_horizon: "LONG_TERM",
            liquidity_needs: "MODERATE",
            capital_preservation_level: "MODERATE",
            ...profile
        }
    });
    global.window = {
        localStorage: {
            getItem(key) { return key === "argos.investor-profile" ? stored : null; },
            setItem() {}
        }
    };
    try { callback(); } finally { global.window = originalWindow; }
}

test("blocks conclusions when institution import is incomplete", () => {
    const institution = {
        name: "UBS",
        position_count: 0,
        currencies: [],
        totals_by_currency: {},
        warnings: ["Carteira ainda não carregada para esta instituição."]
    };

    assert.equal(helpers.isImportIncomplete(institution), true);
    assert.match(helpers.buildSummary(institution), /Dados insuficientes/);
    assert.match(helpers.attentionItems(institution)[0].title, /Dados insuficientes/);
    assert.match(helpers.riskItems(institution)[0].title, /Dados insuficientes/);
    assert.match(helpers.favorableItems(institution)[0].title, /Dados insuficientes/);
});

test("uses portfolio health wording only after the import has positions and values", () => withInvestorProfile(() => {
    const institution = {
        name: "Santander",
        position_count: 3,
        currencies: ["BRL"],
        totals_by_currency: { BRL: 1000 },
        warnings: []
    };

    assert.equal(helpers.isImportIncomplete(institution), false);
    assert.match(helpers.buildSummary(institution), /Santander está saudável/);
    assert.match(helpers.buildSummary(institution), /não há sinal suficiente para exigir ação imediata/);
    assert.equal(helpers.attentionItems(institution).length, 3);
    assert.equal(helpers.riskItems(institution)[0].title, "Nenhum risco dominante identificado");
    assert.equal(helpers.favorableItems(institution)[0].title, "Nenhuma tese exige atenção imediata");
    assert.doesNotMatch(helpers.buildSummary(institution), /comprar|vender/i);
}));

test("failed import status blocks diagnosis for an institution with old dashboard data", () => {
    const originalWindow = global.window;
    const storage = new Map([
        ["argos.institution-import-status", JSON.stringify({
            santander: { status: "error", reason: "import_failed", message: "Falha" }
        })]
    ]);
    global.window = {
        localStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, value); }
        }
    };

    try {
        const institution = helpers.applyImportStatus({
            name: "Santander",
            position_count: 1,
            currencies: ["BRL"],
            totals_by_currency: { BRL: 10000 },
            warnings: []
        });

        assert.equal(helpers.isImportIncomplete(institution), true);
        assert.match(helpers.buildSummary(institution), /Dados insuficientes/);
        assert.match(helpers.buildSummary(institution), /ainda não foi importada corretamente/);
        assert.doesNotMatch(helpers.buildSummary(institution), /1 posições carregadas|R\$ 10\.000|Regular/);
        assert.equal(helpers.riskItems(institution)[0].title, "Dados insuficientes");
        assert.equal(helpers.favorableItems(institution)[0].title, "Dados insuficientes");
    } finally {
        global.window = originalWindow;
    }
});

test("successful import status clears error and allows diagnosis wording", () => {
    const originalWindow = global.window;
    const storage = new Map([
        ["argos.institution-import-status", JSON.stringify({})]
    ]);
    global.window = {
        localStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, value); }
        }
    };

    try {
        const institution = helpers.applyImportStatus({
            name: "Santander",
            position_count: 2,
            currencies: ["BRL"],
            totals_by_currency: { BRL: 20000 },
            warnings: []
        });

        assert.equal(helpers.isImportIncomplete(institution), false);
        withInvestorProfile(() => {
            assert.match(helpers.buildSummary(institution), /2 investimentos foram identificados/);
        });
    } finally {
        global.window = originalWindow;
    }
});

test("completion button remains disabled while import error exists", () => {
    const oldInstitution = {
        name: "Santander",
        position_count: 1,
        currencies: ["BRL"],
        totals_by_currency: { BRL: 10000 },
        warnings: [],
        import_status: { status: "error", reason: "unrecognized_file" }
    };

    assert.equal(helpers.isImportIncomplete(oldInstitution), true);
});


test("answers action question without buy or sell recommendation", () => withInvestorProfile(() => {
    const institution = {
        name: "UBS",
        position_count: 1,
        currencies: ["USD"],
        totals_by_currency: { USD: 10000 },
        warnings: []
    };

    const action = helpers.attentionItems(institution).find((item) => item.title === "Preciso agir agora?");

    assert.ok(action);
    assert.match(action.description, /Não há recomendação automática de compra ou venda/);
    assert.match(helpers.riskItems(institution)[0].description, /concentrada em uma única posição/);
}));

test("blocks health conclusions until investor profile exists", () => {
    const institution = {
        name: "UBS",
        position_count: 3,
        currencies: ["USD"],
        totals_by_currency: { USD: 10000 },
        warnings: []
    };

    assert.match(helpers.buildSummary(institution), /Perfil pendente/);
    assert.equal(helpers.riskItems(institution)[0].title, "Risco não classificado");
});
