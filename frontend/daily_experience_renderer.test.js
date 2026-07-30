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
