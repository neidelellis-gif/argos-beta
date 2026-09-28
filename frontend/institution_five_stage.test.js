"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { InstitutionFiveStage } = require("./institution_five_stage.js");
const helpers = InstitutionFiveStage._test;

function report() {
    return {
        method: "ARGOS_PATRIMONIAL_5_STAGE_V1",
        scope: "institution",
        stages: [
            { key: "diagnosis", items: [] },
            { key: "composition", items: [] },
            { key: "master_assumptions", items: [] },
            {
                key: "market_context",
                status: "available",
                items: [
                    { title: "Juros e economia", reading: "Dado macro relevante." },
                    { title: "Mercado", reading: "Fato ligado à carteira." },
                    { title: "Terceiro fato", reading: "Não deve aparecer no resumo." }
                ]
            },
            {
                key: "final_diagnosis",
                items: [
                    { title: "O que está bem", reading: "Ponto A. • Ponto B. • Ponto C. • Ponto D." },
                    { title: "O que merece atenção", reading: "Ativo A: queda. • Ativo B: oscilação. • Ativo C: risco. • Ativo D: outro." },
                    { title: "Encaminhamento", reading: "Sugerimos conversar com seu gerente de banco ou Banker." }
                ]
            }
        ]
    };
}

test("executive model limits the primary view to three strengths, three attention points and two market facts", () => {
    const model = helpers.executiveModel(report());
    assert.equal(model.strengths.length, 3);
    assert.equal(model.attention.length, 3);
    assert.equal(model.market.length, 2);
    assert.match(model.forwarding, /Banker/);
});

test("executive model does not expose methodology labels", () => {
    const visible = JSON.stringify(helpers.executiveModel(report()));
    assert.doesNotMatch(visible, /5 etapas|metodologia|premissas mestres/i);
});
