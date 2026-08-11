"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

function node(tagName) {
    return {
        tagName,
        className: "",
        textContent: "",
        hidden: false,
        children: [],
        dataset: {},
        attributes: {},
        listeners: {},
        append(...children) { this.children.push(...children); },
        appendChild(child) { this.children.push(child); return child; },
        replaceChildren(...children) { this.children = children; },
        setAttribute(name, value) { this.attributes[name] = String(value); },
        addEventListener(name, listener) { this.listeners[name] = listener; },
        querySelector() { return null; }
    };
}

function setup() {
    const elements = new Map();
    ["greeting", "currentDate", "lastUpdateLabel", "lastUpdate", "factsCount", "marketReactionCount"]
        .forEach((id) => elements.set(id, node("span")));
    [
        ["daily-facts", "importantFacts"],
        ["daily-market-reaction", "marketReaction"]
    ].forEach(([sectionId, listId]) => {
        const section = node("section");
        section.hidden = true;
        elements.set(sectionId, section);
        elements.set(listId, node("div"));
    });
    ["daily-investment-impact", "daily-decision"].forEach((id) => {
        const section = node("section");
        section.hidden = true;
        elements.set(id, section);
    });
    elements.set("neiInvestmentImpact", node("div"));
    elements.set("jolikaInvestmentImpact", node("div"));
    elements.set("dailyAnalyzePortfolios", node("button"));
    elements.set("dailyNotNow", node("button"));
    ["daily-error", "daily-loading"].forEach((id) => {
        const value = node("p");
        value.hidden = true;
        elements.set(id, value);
    });

    const decisionCopy = node("p");
    elements.get("daily-decision").querySelector = (selector) => (
        selector === ".daily-decision-copy p" ? decisionCopy : null
    );

    global.document = {
        createElement: node,
        getElementById(id) { return elements.get(id); }
    };
    global.window = { location: { href: "/" } };
    delete require.cache[require.resolve("./daily_experience_renderer.js")];
    const { DailyExperienceRenderer } = require("./daily_experience_renderer.js");
    return { decisionCopy, elements, renderer: DailyExperienceRenderer };
}

function response(overrides = {}) {
    return {
        contract_version: "1.5",
        status: "SUCCESS",
        generated_at: "2026-07-30T12:00:00Z",
        header: {
            greeting: "Bom dia, Nei",
            display_date: "quinta-feira, 30 de julho de 2026"
        },
        facts: [{ title: "Fato", summary: "Resumo do fato", importance: "HIGH" }],
        priorities: [{ title: "Prioridade", reason: "Resumo da prioridade", level: "HIGH" }],
        analyses: [{ title: "Análise", reason: "Resumo da análise" }],
        impact_assessments: [],
        ...overrides
    };
}

function renderedText(value) {
    return JSON.stringify(value);
}

test("renders the current daily flow and preserves the public header", () => {
    const { decisionCopy, elements, renderer } = setup();
    renderer.render(response());

    assert.equal(elements.get("greeting").textContent, "Bom dia, Nei");
    assert.equal(elements.get("currentDate").textContent, "quinta-feira, 30 de julho de 2026");
    assert.equal(elements.get("lastUpdateLabel").textContent, "Atualizado");
    assert.match(elements.get("lastUpdate").textContent, /^hoje às \d{2}:\d{2}$/);
    assert.equal(elements.get("daily-facts").hidden, false);
    assert.equal(elements.get("daily-market-reaction").hidden, false);
    assert.equal(elements.get("daily-investment-impact").hidden, false);
    assert.equal(elements.get("daily-decision").hidden, false);
    assert.match(decisionCopy.textContent, /Aprofundar análise/);
});

test("combines, deduplicates and limits facts without reordering", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        facts: [
            { title: "Primeiro", summary: "F1" },
            { title: "Duplicado", summary: "F2" },
            { title: "Terceiro", summary: "F3" },
            { title: "Quarto", summary: "F4" }
        ],
        priorities: [{ title: "duplicado", reason: "Não deve repetir" }],
        analyses: [{ title: "Quinto", reason: "F5" }]
    }));

    const items = elements.get("importantFacts").children;
    assert.equal(items.length, 3);
    assert.equal(items[0].children[1].children[0].textContent, "Primeiro");
    assert.equal(items[1].children[1].children[0].textContent, "Duplicado");
    assert.equal(items[2].children[1].children[0].textContent, "Terceiro");
    assert.equal(items[0].children[0].attributes["aria-hidden"], "true");
});

test("hides empty fact and market sections while keeping the decision flow available", () => {
    const { elements, renderer } = setup();
    renderer.render(response({ facts: [], priorities: [], analyses: [], impact_assessments: [] }));

    assert.equal(elements.get("daily-facts").hidden, true);
    assert.equal(elements.get("daily-market-reaction").hidden, true);
    assert.equal(elements.get("importantFacts").children.length, 0);
    assert.equal(elements.get("marketReaction").children.length, 0);
    assert.equal(elements.get("daily-investment-impact").hidden, false);
    assert.equal(elements.get("daily-decision").hidden, false);
});

test("renders market entries uniquely and limits them to three", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        priorities: [{ title: "Mercado B", reason: "B repetido" }],
        impact_assessments: [
            { title: "Mercado A", summary: "A" },
            { title: "Mercado B", summary: "B" },
            { title: "Mercado C", summary: "C" },
            { title: "Mercado D", summary: "D" }
        ]
    }));

    const items = elements.get("marketReaction").children;
    assert.equal(items.length, 3);
    assert.equal(items[0].children[1].children[0].textContent, "Mercado A");
    assert.equal(items[1].children[1].children[0].textContent, "Mercado B");
    assert.equal(items[2].children[1].children[0].textContent, "Mercado C");
});

test("renders known owner impacts with the current status labels and limits", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        impact_assessments: [
            { affected_assets: ["BTC", "ETH", "SOL", "AAVE"], impact_direction: "POSITIVE", summary: "Cenário favorável" },
            { affected_assets: ["GLD"], impact_direction: "NEGATIVE", summary: "Ponto de atenção" }
        ]
    }));

    const nei = elements.get("neiInvestmentImpact").children;
    const jolika = elements.get("jolikaInvestmentImpact").children;
    assert.equal(nei.length, 3);
    assert.equal(nei[0].children[0].children[0].textContent, "BTC");
    assert.equal(nei[0].children[0].children[1].textContent, "Favorável");
    assert.equal(jolika.length, 1);
    assert.equal(jolika[0].children[0].children[0].textContent, "GLD");
    assert.equal(jolika[0].children[0].children[1].textContent, "Atenção");
});

test("cleans editorial metadata and renders external-looking text as text", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        facts: [{
            title: "<img src=x onerror=alert(1)>",
            summary: "analysis-123 Federal Reserve e Treasuries. Direção não é recomendação."
        }],
        priorities: [],
        analyses: []
    }));

    const item = elements.get("importantFacts").children[0];
    assert.equal(item.children[1].children[0].textContent, "<img src=x onerror=alert(1)>");
    assert.match(item.children[1].children[1].textContent, /uma análise interna/);
    assert.match(item.children[1].children[1].textContent, /Banco Central dos Estados Unidos/);
    assert.match(item.children[1].children[1].textContent, /títulos do governo americano/);
    assert.doesNotMatch(item.children[1].children[1].textContent, /analysis-123|Direção não é recomendação/);
});

test("does not mutate any part of the response", () => {
    const { renderer } = setup();
    const payload = response({
        impact_assessments: [{
            affected_assets: ["BTC", "GLD"],
            impact_direction: "MIXED",
            summary: "Impacto"
        }]
    });
    const before = JSON.stringify(payload);
    renderer.render(payload);
    assert.equal(JSON.stringify(payload), before);
});

test("replaces previous list content on subsequent renders", () => {
    const { elements, renderer } = setup();
    renderer.render(response());
    renderer.render(response({ facts: [], priorities: [], analyses: [], impact_assessments: [] }));

    assert.equal(elements.get("importantFacts").children.length, 0);
    assert.equal(elements.get("marketReaction").children.length, 0);
    assert.equal(elements.get("daily-facts").hidden, true);
    assert.equal(elements.get("daily-market-reaction").hidden, true);
});

test("binds decision actions once and keeps their current behavior", () => {
    const { elements, renderer } = setup();
    renderer.render(response());
    const analyze = elements.get("dailyAnalyzePortfolios");
    const notNow = elements.get("dailyNotNow");
    const analyzeListener = analyze.listeners.click;
    const notNowListener = notNow.listeners.click;

    assert.equal(analyze.textContent, "Aprofundar análise");
    analyze.listeners.click();
    assert.equal(global.window.location.href, "/analysis_start.html");
    notNow.listeners.click();
    assert.equal(notNow.textContent, "Continuar depois");

    renderer.render(response());
    assert.equal(analyze.listeners.click, analyzeListener);
    assert.equal(notNow.listeners.click, notNowListener);
});

test("rejects invalid responses and controls loading and error states", () => {
    const { elements, renderer } = setup();
    renderer.showLoading();
    assert.equal(elements.get("daily-loading").hidden, false);
    assert.equal(elements.get("daily-error").hidden, true);

    for (const invalid of [null, {}, response({ status: "ERROR" }), response({ facts: null })]) {
        assert.throws(() => renderer.render(invalid), /Invalid daily experience/);
    }

    renderer.showError();
    assert.equal(elements.get("daily-loading").hidden, true);
    assert.equal(elements.get("daily-error").hidden, false);
    assert.equal(elements.get("daily-error").textContent,
        "Não foi possível preparar a experiência diária.");
});

test("does not expose technical relationship fields in the rendered DOM", () => {
    const { elements, renderer } = setup();
    renderer.render(response({
        facts: [{ title: "Fato público", summary: "Resumo", id: "private-fact" }],
        priorities: [{ title: "Prioridade pública", reason: "Razão", related_analyses: ["private-analysis"] }],
        analyses: [{ title: "Análise pública", reason: "Razão", related_facts: ["private-fact"] }]
    }));

    const rendered = renderedText([
        elements.get("importantFacts"),
        elements.get("marketReaction")
    ]);
    assert.doesNotMatch(rendered, /private-fact|private-analysis|related_facts|related_analyses/);
});
