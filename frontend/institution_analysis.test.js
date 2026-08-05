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
    assert.match(helpers.buildSummary(institution), /Ainda não há dados suficientes/);
    assert.match(helpers.attentionItems(institution)[0].title, /Importação incompleta/);
    assert.match(helpers.riskItems(institution)[0].title, /Sem conclusão de risco/);
    assert.match(helpers.favorableItems(institution)[0].title, /Nenhum ponto favorável confirmado/);
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
