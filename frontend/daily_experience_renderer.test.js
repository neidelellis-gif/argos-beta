"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

function node(tagName) {
    return {
        tagName, className: "", textContent: "", hidden: false, children: [],
        appendChild(child) { this.children.push(child); },
        replaceChildren(...children) { this.children = children; }
    };
}

function setup() {
    const elements = new Map();
    ["greeting", "currentDate", "lastUpdateLabel", "lastUpdate"].forEach(
        (id) => elements.set(id, node("span"))
    );
    [
        ["daily-facts", "importantFacts"],
        ["daily-priorities", "dailyPriorities"],
        ["daily-analyses", "dailyAnalyses"],
        ["daily-decision-context", "dailyDecisionContexts"],
        ["daily-impacts", "dailyImpacts"],
        ["data-quality", "dataQualityDiagnostics"],
        ["market-agenda", "marketAgenda"]
    ].forEach(([panelId, listId]) => {
        const section = node("article");
        section.hidden = true;
        elements.set(panelId, section);
        elements.set(listId, node("div"));
    });
    const agendaPanel = node("article");
    agendaPanel.hidden = true;
    elements.set("marketAgendaPanel", agendaPanel);
    ["daily-error", "daily-loading"].forEach((id) => {
        const value = node("p");
        value.hidden = true;
        elements.set(id, value);
    });
    global.document = {
        createElement: node,
        getElementById(id) { return elements.get(id); }
    };
    delete require.cache[require.resolve("./daily_experience_renderer.js")];
    const { DailyExperienceRenderer } = require("./daily_experience_renderer.js");
    return { elements, renderer: DailyExperienceRenderer };
}

function response(overrides = {}) {
    return {
        contract_version: "1.0", status: "SUCCESS",
        generated_at: "2026-07-30T12:00:00Z",
        header: { greeting: "Bom dia, Nei", display_date: "quinta-feira, 30 de julho de 2026" },
        facts: [{ id: "technical", category: "Carteira", text: "Fato", importance: "HIGH" }],
        priorities: [{ fact_id: "technical", type: "DECIDE", level: "HIGH", title: "Prioridade", reason: "Resumo", related_analyses: ["a"] }],
        analyses: [{ fact_id: "technical", action: "Analisar", title: "Análise", reason: "Resumo", related_facts: ["f"] }],
        ...overrides
    };
}

test("renders a complete payload and preserves the public date", () => {
    const { elements, renderer } = setup();
    renderer.render(response());
    assert.equal(elements.get("greeting").textContent, "Bom dia, Nei");
    assert.equal(elements.get("currentDate").textContent, "quinta-feira, 30 de julho de 2026");
    assert.equal(elements.get("daily-facts").hidden, false);
    assert.equal(elements.get("daily-priorities").hidden, false);
    assert.equal(elements.get("daily-analyses").hidden, false);
    assert.equal(elements.get("market-agenda").hidden, true);
});

for (const [name, overrides, visible] of [
    ["only facts", { priorities: [], analyses: [] }, "daily-facts"],
    ["only priorities", { facts: [], analyses: [] }, "daily-priorities"],
    ["only analyses", { facts: [], priorities: [] }, "daily-analyses"]
]) {
    test(`shows ${name} and hides empty blocks`, () => {
        const { elements, renderer } = setup();
        renderer.render(response(overrides));
        for (const id of ["daily-facts", "daily-priorities", "daily-analyses"]) {
            assert.equal(elements.get(id).hidden, id !== visible);
        }
    });
}

test("shows only greeting and date when every block is empty", () => {
    const { elements, renderer } = setup();
    renderer.render(response({ facts: [], priorities: [], analyses: [] }));
    assert.equal(elements.get("greeting").textContent, "Bom dia, Nei");
    assert.equal(elements.get("daily-facts").hidden, true);
    assert.equal(elements.get("daily-priorities").hidden, true);
    assert.equal(elements.get("daily-analyses").hidden, true);
});

test("enforces the presentation limits without reordering", () => {
    const { elements, renderer } = setup();
    const facts = Array.from({ length: 7 }, (_, index) => ({ category: "C", text: `F${index}` }));
    const priorities = Array.from({ length: 4 }, (_, index) => ({ level: "LOW", title: `P${index}`, reason: "R" }));
    const analyses = Array.from({ length: 4 }, (_, index) => ({ action: "Decidir", title: `A${index}`, reason: "R" }));
    renderer.render(response({ facts, priorities, analyses }));
    assert.equal(elements.get("importantFacts").children.length, 5);
    assert.equal(elements.get("dailyPriorities").children.length, 2);
    assert.equal(elements.get("dailyAnalyses").children.length, 2);
    assert.equal(elements.get("importantFacts").children[0].children[1].textContent, "F0");
});

test("maps priority levels and action types", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        priorities: [
            { type: "ANALYZE", level: "MEDIUM", title: "M", reason: "R" },
            { type: "DECIDE", level: "MODERATE", title: "C", reason: "R" }
        ],
        analyses: [
            { type: "ANALYZE", title: "A", reason: "R" },
            { type: "DECIDE", title: "D", reason: "R" }
        ]
    }));
    const priorities = elements.get("dailyPriorities").children;
    assert.equal(priorities[0].children[0].children[0].textContent, "Analisar");
    assert.equal(priorities[0].children[0].children[1].textContent, "Moderada");
    assert.equal(priorities[1].children[0].children[0].textContent, "Decidir");
    assert.equal(priorities[1].children[0].children[1].textContent, "Moderada");
    assert.equal(elements.get("dailyAnalyses").children[0].children[0].children[0].textContent, "Analisar");
    assert.equal(elements.get("dailyAnalyses").children[1].children[0].children[0].textContent, "Decidir");
});

test("maps HIGH and LOW to safe visual labels", () => {
    const { elements, renderer } = setup();
    renderer.render(response({ priorities: [
        { level: "HIGH", title: "H", reason: "R" },
        { level: "LOW", title: "L", reason: "R" }
    ] }));
    assert.equal(elements.get("dailyPriorities").children[0].children[0].children[1].textContent, "Alta");
    assert.equal(elements.get("dailyPriorities").children[1].children[0].children[1].textContent, "Baixa");
});

test("does not expose technical relationships, ids, JSON, or execute HTML", () => {
    const { elements, renderer } = setup();
    renderer.render(response({ facts: [{ category: "C", text: "<img src=x onerror=alert(1)>" }] }));
    const serialized = JSON.stringify([...elements.values()]);
    assert.doesNotMatch(serialized, /technical|related_facts|related_analyses|\[object Object\]/);
    assert.equal(elements.get("importantFacts").children[0].children[1].textContent,
        "<img src=x onerror=alert(1)>");
});

test("does not mutate any part of the payload", () => {
    const { renderer } = setup();
    const payload = response({ market_agenda: [{ title: "Evento" }] });
    const before = JSON.stringify(payload);
    renderer.render(payload);
    assert.equal(JSON.stringify(payload), before);
});

test("keeps agenda hidden whether absent, empty, or unsupported by contract 1.0", () => {
    for (const agenda of [undefined, [], [{ title: "Evento" }]]) {
        const { elements, renderer } = setup();
        renderer.render(response(agenda === undefined ? {} : { market_agenda: agenda }));
        assert.equal(elements.get("market-agenda").hidden, true);
    }
});

test("renders contract 1.1 agenda safely with translations and original timezone", () => {
    const { elements, renderer } = setup();
    const event = {
        id: "agenda-secret", event_type: "CENTRAL_BANK", importance: "HIGH",
        title: "<Decisão>", summary: "Política monetária", event_date: "2026-07-30",
        event_time: "14:00", timezone: "America/New_York", all_day: false,
        affected_assets: ["USD", "NVDA"], source_name: "Federal Reserve",
        source_reference: "never-render"
    };
    renderer.render(response({ contract_version: "1.1", market_agenda: [event] }));
    const rendered = JSON.stringify(elements.get("marketAgenda"));
    assert.equal(elements.get("marketAgendaPanel").hidden, false);
    assert.equal(elements.get("marketAgenda").children.length, 1);
    assert.match(rendered, /Bancos centrais/);
    assert.match(rendered, /Alta/);
    assert.match(rendered, /14:00 — America\/New_York/);
    assert.match(rendered, /Fonte: Federal Reserve/);
    assert.doesNotMatch(rendered, /agenda-secret|never-render/);
});

test("renders all-day events, limits ten, and hides after an empty response", () => {
    const { elements, renderer } = setup();
    const events = Array.from({ length: 12 }, (_, index) => ({
        id: `id-${index}`, event_type: "EARNINGS", importance: "MEDIUM",
        title: `Evento ${index}`, summary: "Resumo", event_date: "2026-07-30",
        event_time: null, timezone: null, all_day: true, affected_assets: [], source_name: "RI"
    }));
    renderer.render(response({ contract_version: "1.1", market_agenda: events }));
    assert.equal(elements.get("marketAgenda").children.length, 10);
    assert.match(JSON.stringify(elements.get("marketAgenda")), /Dia inteiro/);
    renderer.render(response({ contract_version: "1.1", market_agenda: [] }));
    assert.equal(elements.get("marketAgendaPanel").hidden, true);
    assert.equal(elements.get("marketAgenda").children.length, 0);
});

test("rejects invalid responses and controls loading and error states", () => {
    const { elements, renderer } = setup();
    renderer.showLoading();
    assert.equal(elements.get("daily-loading").hidden, false);
    assert.throws(() => renderer.render({}), /Invalid daily experience/);
    renderer.showError();
    assert.equal(elements.get("daily-loading").hidden, true);
    assert.equal(elements.get("daily-error").hidden, false);
    assert.equal(elements.get("daily-error").textContent,
        "Não foi possível preparar a experiência diária.");
});

test("renders contract 1.2 impacts safely, translates labels, limits five, and hides after empty", () => {
    const { elements, renderer } = setup();
    const impactPanel = node("article"); impactPanel.hidden = true;
    elements.set("daily-impacts", impactPanel); elements.set("dailyImpacts", node("div"));
    const impact = {
        id: "impact-secret", source_id: "fact-secret", source_type: "FACT",
        impact_level: "HIGH", impact_direction: "MIXED", confidence: "MEDIUM",
        title: "<img src=x>", summary: "Impacto potencial.", affected_assets: ["GLD"],
        impact_factors: [{ factor_type: "CURRENCY", factor_value: "USD", description: "Moeda USD presente." }],
        affected_positions: [{ position_id: "secret" }]
    };
    const payload = response({ contract_version: "1.2", impact_assessments: Array(7).fill(impact), market_agenda: [] });
    const before = JSON.stringify(payload);
    renderer.render(payload);
    assert.equal(elements.get("daily-impacts").hidden, false);
    assert.equal(elements.get("dailyImpacts").children.length, 5);
    const rendered = JSON.stringify(elements.get("dailyImpacts"));
    assert.match(rendered, /Direção: Misto · Confiança: Moderada/);
    assert.match(rendered, /Ativos relacionados: GLD/);
    assert.match(rendered, /Moeda USD presente/);
    assert.doesNotMatch(rendered, /fact-secret|position_id|\[object Object\]/);
    assert.equal(JSON.stringify(payload), before);
    renderer.render(response({ contract_version: "1.2", impact_assessments: [], market_agenda: [] }));
    assert.equal(elements.get("daily-impacts").hidden, true);
});

test("renders contract 1.3 decision contexts safely, translated, limited and immutable", () => {
    const { elements, renderer } = setup();
    const context = {
        id: "context-secret", context_type: "RESTRICTION_CONTEXT", relevance_level: "HIGH",
        title: "<Contexto>", summary: "Relação descritiva.", related_assets: ["USD"],
        context_factors: [{ factor_type: "RESTRICTION", factor_value: "secret", description: "Restrição declarada." }],
        limitations: ["A exposição quantitativa não foi calculada."], related_facts: ["private"]
    };
    const payload = response({ contract_version: "1.3", decision_contexts: Array(7).fill(context) });
    const before = JSON.stringify(payload);
    renderer.render(payload);
    assert.equal(elements.get("daily-decision-context").hidden, false);
    assert.equal(elements.get("dailyDecisionContexts").children.length, 5);
    const rendered = JSON.stringify(elements.get("dailyDecisionContexts"));
    assert.match(rendered, /Restrições/);
    assert.match(rendered, /Alta/);
    assert.match(rendered, /Ativos relacionados: USD/);
    assert.match(rendered, /Restrição declarada/);
    assert.match(rendered, /Limitações/);
    assert.doesNotMatch(rendered, /context-secret|private|factor_value|\[object Object\]/);
    assert.equal(JSON.stringify(payload), before);
    renderer.render(response({ contract_version: "1.3", decision_contexts: [] }));
    assert.equal(elements.get("daily-decision-context").hidden, true);
});

test("keeps data quality hidden for healthy 1.4 and every previous version", () => {
    for (const contract_version of ["1.0", "1.1", "1.2", "1.3"]) {
        const { elements, renderer } = setup();
        renderer.render(response({ contract_version, data_quality: {
            status: "ERROR", diagnostics: [{ title: "Não renderizar" }]
        } }));
        assert.equal(elements.get("data-quality").hidden, true);
    }
    const { elements, renderer } = setup();
    renderer.render(response({ contract_version: "1.4", data_quality: {
        status: "HEALTHY", summary: { errors: 0, warnings: 0, infos: 0 }, diagnostics: []
    } }));
    assert.equal(elements.get("data-quality").hidden, true);
});

test("renders 1.4 diagnostics safely without interpreting HTML or mutating payload", () => {
    const { elements, renderer } = setup();
    const diagnostic = {
        id: "private-id", severity: "WARNING", category: "PORTFOLIO",
        title: "<img src=x onerror=alert(1)>", description: "Revise a importação.",
        affected_items: ["GLD"], can_continue: true
    };
    const payload = response({ contract_version: "1.4", data_quality: {
        status: "WARNING", summary: { errors: 0, warnings: 1, infos: 0 }, diagnostics: [diagnostic]
    } });
    const before = JSON.stringify(payload);
    renderer.render(payload);
    const rendered = JSON.stringify(elements.get("dataQualityDiagnostics"));
    assert.equal(elements.get("data-quality").hidden, false);
    assert.match(rendered, /Atenção/);
    assert.match(rendered, /<img src=x onerror=alert\(1\)>/);
    assert.match(rendered, /Itens afetados: GLD/);
    assert.doesNotMatch(rendered, /private-id|PORTFOLIO|can_continue/);
    assert.equal(JSON.stringify(payload), before);
});
