"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

function createElement(tagName, className = "", text = "") {
    return {
        tagName,
        className,
        textContent: text,
        children: [],
        dataset: {},
        style: {},
        append(...elements) {
            this.children.push(...elements);
        },
        appendChild(element) {
            this.children.push(element);
        },
        replaceChildren(...elements) {
            this.children = elements;
        },
        addEventListener() {}
    };
}

function collectText(element) {
    return [
        element.textContent || "",
        ...(element.children || []).map(collectText)
    ].join(" ");
}

function createContext(dashboard) {
    const elements = new Map();

    for (const id of [
        "portfolioExecutiveTotals",
        "portfolioExecutiveAllocation",
        "portfolioExecutiveAttention",
        "portfolioExecutiveInstitutions",
        "portfolioOwnerName"
    ]) {
        elements.set(id, createElement("div"));
    }

    const context = {
        console,
        URLSearchParams,
        window: {
            location: {
                href: ""
            },
            addEventListener() {}
        },
        document: {
            createElement,
            getElementById(id) {
                return elements.get(id);
            },
            addEventListener() {}
        },
        fetch: async () => ({
            ok: true,
            async json() {
                return dashboard;
            }
        }),
        ArgosAnalysisContext: {
            getActiveOwner() {
                return {
                    id: "JOLIKA",
                    name: "Jolika",
                    institutions: ["UBS", "Santander"]
                };
            }
        }
    };

    vm.createContext(context);
    vm.runInContext(
        fs.readFileSync("frontend/portfolio_executive.js", "utf8"),
        context
    );
    vm.runInContext(
        "this.PortfolioExecutiveForTest = PortfolioExecutive",
        context
    );

    return { context, elements };
}

test("keeps consolidated intelligence hidden before explicit authorization", async () => {
    const dashboard = {
        institutions: [
            {
                name: "UBS",
                position_count: 2,
                currencies: ["USD"],
                totals_by_currency: { USD: "150" }
            },
            {
                name: "Santander",
                position_count: 1,
                currencies: ["USD"],
                totals_by_currency: { USD: "50" }
            }
        ],
        consolidated: {
            intelligence: {
                priority: {
                    level: "Alta",
                    reasons: [
                        "concentration",
                        "cross_institution_duplicate"
                    ]
                },
                portfolio_reading:
                    "A carteira está concentrada em poucos ativos e isso merece mais atenção agora.",
                coverage: {
                    consolidated_asset_count: 2,
                    assets_with_economic_class: 2,
                    assets_with_identifier: 2
                },
                concentration_by_currency: [
                    {
                        currency: "USD",
                        top_1_weight: "0.75"
                    }
                ],
                duplicate_exposures: [
                    {
                        across_institutions: true
                    }
                ]
            }
        }
    };

    const { context, elements } = createContext(dashboard);

    await context.PortfolioExecutiveForTest.load();

    const text = collectText(
        elements.get("portfolioExecutiveAttention")
    );

    assert.match(text, /Análises disponíveis/);
    assert.match(text, /UBS e Santander estão disponíveis para análise individual/);
    assert.match(text, /Análises disponíveis/);

    assert.doesNotMatch(text, /Prioridade de análise/);
    assert.doesNotMatch(text, /Alta\. Fatores:/);
    assert.doesNotMatch(text, /concentração relevante/);
    assert.doesNotMatch(
        text,
        /ativo presente em mais de uma instituição/
    );
    assert.doesNotMatch(text, /Leitura da carteira/);
    assert.doesNotMatch(text, /Cobertura da classificação/);
    assert.doesNotMatch(text, /Maior concentração individual/);
    assert.doesNotMatch(text, /Duplicidades entre instituições/);
    assert.doesNotMatch(text, /ativos consolidados/);
});

test("keeps executive attention working without Jolika intelligence", async () => {
    const dashboard = {
        institutions: [
            {
                name: "UBS",
                position_count: 1,
                currencies: ["USD"],
                totals_by_currency: { USD: "100" }
            }
        ],
        consolidated: {}
    };

    const { context, elements } = createContext(dashboard);

    await context.PortfolioExecutiveForTest.load();

    const text = collectText(
        elements.get("portfolioExecutiveAttention")
    );

    assert.match(text, /Análises disponíveis/);
    assert.match(text, /Carteiras ainda não carregadas/);
    assert.doesNotMatch(text, /Cobertura da classificação/);
});
