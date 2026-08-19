"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

function createElement() {
    return {
        hidden: false,
        disabled: false,
        textContent: "",
        value: "",
        dataset: {},
        files: [],
        children: [],
        listeners: {},
        classList: {
            toggle() {}
        },
        addEventListener(name, listener) {
            this.listeners[name] = listener;
        },
        appendChild(child) {
            this.children.push(child);
        },
        replaceChildren(...children) {
            this.children = children;
        },
        scrollIntoView() {}
    };
}

function createContext() {
    const elements = new Map();

    [
        "previousPortfolioStatus",
        "previousPortfolioSummary",
        "usePreviousPortfolio",
        "methodPanel",
        "previousPanel",
        "pastePanel",
        "uploadPanel",
        "ownerStage",
        "institutionStage",
        "ownerOptions",
        "institutionList",
        "portfolioPaste",
        "usePastedPortfolio",
        "analysisFiles",
        "analysisFileStatus",
        "useUploadedPortfolio",
        "startIndividualAnalysis",
        "portfolioReadingStage",
        "portfolioReadingText",
        "deepenPortfolioAnalysis",
        "finishBriefReading"
    ].forEach((id) => {
        elements.set(id, createElement());
    });

    const context = {
        console,
        URLSearchParams,
        document: {
            addEventListener() {},
            getElementById(id) {
                return elements.get(id);
            },
            querySelectorAll() {
                return [];
            },
            createElement
        },
        window: {
            alert() {},
            location: { href: "" }
        },
        ArgosAnalysisContext: {
            getOwners() {
                return [{
                    id: "JOLIKA",
                    name: "Jolika",
                    institutions: ["UBS", "Santander"]
                }];
            },
            setActiveOwner() {}
        },
        fetch: async (url, options) => {
            if (url === "/api/dashboard") {
                return {
                    ok: true,
                    async json() {
                        return {
                            institutions: []
                        };
                    }
                };
            }

            assert.equal(url, "/api/portfolios/paste");
            assert.equal(options.method, "POST");

            return {
                ok: true,
                async json() {
                    return {
                        ok: true,
                        dashboard: {
                            institutions: [{
                                name: "UBS",
                                position_count: 2
                            }],
                            consolidated: {
                                intelligence: {
                                    portfolio_reading:
                                        "A carteira está concentrada em poucos ativos e isso merece mais atenção agora."
                                }
                            }
                        }
                    };
                }
            };
        }
    };

    vm.createContext(context);
    vm.runInContext(
        fs.readFileSync("frontend/analysis_start.js", "utf8"),
        context
    );
    vm.runInContext(
        "this.AnalysisStartForTest = AnalysisStart",
        context
    );

    return { context, elements };
}

test("pasted portfolio shows brief reading before deeper analysis", async () => {
    const { context, elements } = createContext();

    context.AnalysisStartForTest.setup();

    const paste = elements.get("portfolioPaste");
    paste.value =
        "instituição\tativo\tvalor\tmoeda\nUBS\tApple\t80000\tUSD";

    paste.listeners.input();
    assert.equal(
        elements.get("usePastedPortfolio").disabled,
        false
    );

    await elements.get("usePastedPortfolio").listeners.click();

    assert.equal(
        elements.get("portfolioReadingText").textContent,
        "A carteira está concentrada em poucos ativos e isso merece mais atenção agora."
    );
    assert.equal(
        elements.get("portfolioReadingStage").hidden,
        false
    );
    assert.equal(
        elements.get("ownerStage").hidden,
        true
    );
    assert.equal(
        elements.get("institutionStage").hidden,
        true
    );

    elements.get("deepenPortfolioAnalysis").listeners.click();

    assert.equal(
        elements.get("portfolioReadingStage").hidden,
        true
    );
    assert.equal(
        elements.get("ownerStage").hidden,
        false
    );
});


test("uploaded portfolio shows brief reading before deeper analysis", async () => {
    const { context, elements } = createContext();

    context.FormData = class {
        constructor() {
            this.items = [];
        }
        append(name, file, fileName) {
            this.items.push({ name, file, fileName });
        }
    };

    context.fetch = async (url, options) => {
        if (url === "/api/dashboard") {
            return {
                ok: true,
                async json() {
                    return {
                        institutions: []
                    };
                }
            };
        }

        assert.equal(url, "/api/portfolios/import");
        assert.equal(options.method, "POST");
        assert.ok(options.body instanceof context.FormData);

        return {
            ok: true,
            async json() {
                return {
                    ok: true,
                    dashboard: {
                        institutions: [{
                            name: "UBS",
                            position_count: 2
                        }],
                        consolidated: {
                            intelligence: {
                                portfolio_reading:
                                    "A carteira está concentrada em poucos ativos e isso merece mais atenção agora."
                            }
                        }
                    }
                };
            }
        };
    };

    context.AnalysisStartForTest.setup();

    const files = elements.get("analysisFiles");
    files.files = [
        {
            name: "ubs.csv"
        }
    ];

    files.listeners.change();

    assert.equal(
        elements.get("useUploadedPortfolio").disabled,
        false
    );

    await elements.get("useUploadedPortfolio").listeners.click();

    assert.equal(
        elements.get("portfolioReadingText").textContent,
        "A carteira está concentrada em poucos ativos e isso merece mais atenção agora."
    );
    assert.equal(
        elements.get("portfolioReadingStage").hidden,
        false
    );
    assert.equal(
        elements.get("ownerStage").hidden,
        true
    );
    assert.equal(
        elements.get("institutionStage").hidden,
        true
    );

    elements.get("deepenPortfolioAnalysis").listeners.click();

    assert.equal(
        elements.get("portfolioReadingStage").hidden,
        true
    );
    assert.equal(
        elements.get("ownerStage").hidden,
        false
    );
});
