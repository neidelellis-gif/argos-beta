"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { InstitutionAnalysis } = require("./institution_analysis.js");
const helpers = InstitutionAnalysis._test;

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

test("uses executive wording only after the import has positions and values", () => {
    const institution = {
        name: "Santander",
        position_count: 3,
        currencies: ["BRL"],
        totals_by_currency: { BRL: 1000 },
        warnings: []
    };

    assert.equal(helpers.isImportIncomplete(institution), false);
    assert.equal(
        helpers.buildSummary(institution),
        "Santander tem 3 posições carregadas, com exposição em BRL. A base está suficiente para uma leitura executiva inicial, ainda sem substituir a validação individual dos ativos."
    );
    assert.equal(helpers.riskItems(institution).length, 0);
    assert.match(helpers.favorableItems(institution)[0].title, /Mais de uma posição/);
});

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
        assert.match(helpers.buildSummary(institution), /2 posições carregadas/);
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
