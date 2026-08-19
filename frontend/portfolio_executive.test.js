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

test("renders Jolika intelligence in executive attention", async () => {
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
                coverage: {
                    consolidated_asset_count: 2,
                    assets_with_economic_class: 2
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

    assert.match(text, /Prioridade de análise/);
    assert.match(text, /Alta\. Fatores:/);
    assert.match(text, /concentração relevante/);
    assert.match(text, /ativo presente em mais de uma instituição/);
    assert.match(text, /Cobertura da classificação/);
    assert.match(text, /100\.0% dos ativos consolidados/);
    assert.match(text, /Maior concentração individual/);
    assert.match(text, /USD: 75\.0% no maior ativo/);
    assert.match(text, /Duplicidades entre instituições/);
    assert.match(text, /1 ativo aparece em mais de uma instituição/);
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

    assert.match(text, /Análises individuais primeiro/);
    assert.match(text, /Carteiras ainda não carregadas/);
    assert.doesNotMatch(text, /Cobertura da classificação/);
});
