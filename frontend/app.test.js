"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

const context = {
    console,
    document: {
        addEventListener() {}
    }
};

vm.createContext(context);
vm.runInContext(fs.readFileSync("frontend/daily_client.js", "utf8"), context);
vm.runInContext("this.DailyClientForTest = DailyFrontendClient", context);
vm.runInContext(fs.readFileSync("frontend/daily_request_builder.js", "utf8"), context);
vm.runInContext(fs.readFileSync("frontend/daily_experience_renderer.js", "utf8"), context);
vm.runInContext("this.DailyRendererForTest = DailyExperienceRenderer", context);
vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), context);

function readCsv(content) {
    return context.getCsvDataRows(context.parseCsv(content));
}

function createNotebookElement(dataset) {
    const classes = new Set();
    return {
        dataset,
        hidden: false,
        attributes: {},
        listener: null,
        classList: {
            toggle(name, enabled) {
                enabled ? classes.add(name) : classes.delete(name);
            },
            contains(name) {
                return classes.has(name);
            }
        },
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
        addEventListener(name, listener) {
            if (name === "click") this.listener = listener;
        }
    };
}

function createNotebookFixture() {
    const names = ["daily", "profile", "portfolios"];
    const items = names.map((tab) => createNotebookElement({ tab }));
    const panels = names.map(
        (tabPanel) => createNotebookElement({ tabPanel })
    );
    const root = {
        querySelectorAll(selector) {
            return selector === "[data-tab]" ? items : panels;
        }
    };
    return { root, items, panels };
}

test("notebook opens with only Daily selected", () => {
    const { root, items, panels } = createNotebookFixture();

    context.setupNotebookNavigation(root);

    assert.equal(items[0].attributes["aria-selected"], "true");
    assert.equal(panels[0].hidden, false);
    assert.equal(panels.filter((panel) => !panel.hidden).length, 1);
});

test("notebook switches tabs without replacing panel content", () => {
    const { root, items, panels } = createNotebookFixture();
    panels[2].contentState = "preserved";
    context.setupNotebookNavigation(root);

    items[2].listener();

    assert.equal(panels.filter((panel) => !panel.hidden).length, 1);
    assert.equal(panels[2].hidden, false);
    assert.equal(panels[2].contentState, "preserved");
    assert.equal(items[2].classList.contains("active"), true);
    assert.equal(items[0].attributes["aria-selected"], "false");
});

test("Daily and Portfolios keep their approved content boundaries", () => {
    const html = fs.readFileSync("frontend/index.html", "utf8");
    const daily = html.match(
        /data-tab-panel="daily"[\s\S]*?data-tab-panel="portfolios"/
    )[0];
    const portfolios = html.match(
        /data-tab-panel="portfolios"[\s\S]*?data-tab-panel="profile"/
    )[0];

    assert.match(daily, /class="daily-flow"/);
    assert.doesNotMatch(daily, /class="dashboard-section"/);
    assert.doesNotMatch(daily, /class="portfolio-import-section"/);
    assert.match(portfolios, /class="portfolio-workspace"/);
    assert.match(portfolios, /class="portfolio-import-drawer"/);
});

test("Strategic Profile presents private banking copy and hides technical terminology", () => {
    const html = fs.readFileSync("frontend/index.html", "utf8");
    const profile = html.match(/data-tab-panel="profile"[\s\S]*?data-tab-panel="news"/)[0];

    assert.match(html, /data-tab="profile">Perfil Estratégico<\/button>/);
    assert.match(profile, /Qual prioridade deve orientar este patrimônio neste ciclo\?/);
    assert.match(profile, /Diante de uma oscilação temporária de 15%/);
    assert.match(profile, /Confirmar Perfil Estratégico/);
    assert.doesNotMatch(profile, /Meu Perfil|Motor|Motor de Saúde|Perfil usado pelo Motor|Decision Profile/);
});

function createInvestorProfileFixture() {
    const inputs = new Map();
    const form = createElement("form");
    const summary = createElement("article");
    const status = createElement("span");
    let updateListener = null;
    form.hidden = false;
    summary.hidden = true;
    summary.replaceChildren = function (...elements) {
        this.children = elements;
        this.innerHTML = "";
    };
    form.querySelector = (selector) => {
        const match = selector.match(/input\[name="([^"]+)"\]\[value="([^"]+)"\]/);
        if (!match) return null;
        const key = `${match[1]}:${match[2]}`;
        if (!inputs.has(key)) inputs.set(key, { checked: false });
        return inputs.get(key);
    };
    summary.querySelector = (selector) => selector === "#updateInvestorProfile" ? {
        addEventListener(name, listener) {
            if (name === "click") updateListener = listener;
        }
    } : null;
    context.document.getElementById = (id) => ({
        investorProfileForm: form,
        investorProfileSummary: summary,
        investorProfileStatus: status
    })[id];
    return { form, summary, status, inputs, clickUpdate: () => updateListener() };
}

function assertProfileVisibility({ form, summary }, expected) {
    assert.equal(form.hidden, expected.formHidden);
    assert.equal(summary.hidden, expected.summaryHidden);
    assert.notEqual(form.hidden, summary.hidden);
}

test("Strategic Profile summary stays executive after save", () => {
    const form = createElement("form");
    const summary = createElement("article");
    const status = createElement("span");
    let summaryButtonListener = null;
    summary.querySelector = () => ({
        addEventListener(name, listener) {
            if (name === "click") summaryButtonListener = listener;
        }
    });
    context.document.getElementById = (id) => ({
        investorProfileForm: form,
        investorProfileSummary: summary,
        investorProfileStatus: status
    })[id];

    context.renderInvestorProfileSummary({
        answers: { primaryGoal: "balance", riskTolerance: "moderate", horizon: "long", liquidity: "moderate" },
        profile: { review_date: "2027-08-05" },
        saved_at: "2026-08-05T12:00:00.000Z"
    });

    assert.equal(form.hidden, true);
    assert.equal(summary.hidden, false);
    assert.equal(status.textContent, "Perfil vigente");
    assert.match(summary.innerHTML, /Última atualização/);
    assert.match(summary.innerHTML, /Próxima revisão anual/);
    assert.match(summary.innerHTML, /Atualizar Perfil/);
    assert.doesNotMatch(summary.innerHTML, /Motor|Decision Profile/);
    summaryButtonListener();
    assert.equal(form.hidden, false);
    assert.equal(summary.hidden, true);
});


test("Strategic Profile first access shows only form and keeps summary without visual space", () => {
    const fixture = createInvestorProfileFixture();

    context.renderInvestorProfileSummary(null);

    assertProfileVisibility(fixture, { formHidden: false, summaryHidden: true });
    assert.equal(fixture.status.textContent, "Perfil não preenchido");
    assert.equal(fixture.summary.innerHTML, "");
});

test("Strategic Profile toggles through confirmed, editing, and reconfirmed without simultaneous visibility", () => {
    const fixture = createInvestorProfileFixture();
    const stored = {
        answers: { primaryGoal: "balance", riskTolerance: "moderate", horizon: "long", liquidity: "moderate" },
        profile: { review_date: "2027-08-05" },
        saved_at: "2026-08-05T12:00:00.000Z"
    };

    context.renderInvestorProfileSummary(stored);

    assertProfileVisibility(fixture, { formHidden: true, summaryHidden: false });
    assert.match(fixture.summary.innerHTML, /Perfil Estratégico/);
    assert.doesNotMatch(fixture.summary.innerHTML, /<input|fieldset|Confirmar Perfil Estratégico/);

    fixture.clickUpdate();

    assertProfileVisibility(fixture, { formHidden: false, summaryHidden: true });
    assert.equal(fixture.summary.innerHTML, "");
    assert.equal(fixture.inputs.get("primaryGoal:balance").checked, true);
    assert.equal(fixture.inputs.get("riskTolerance:moderate").checked, true);
    assert.equal(fixture.inputs.get("horizon:long").checked, true);
    assert.equal(fixture.inputs.get("liquidity:moderate").checked, true);

    context.renderInvestorProfileSummary(stored);

    assertProfileVisibility(fixture, { formHidden: true, summaryHidden: false });
});

test("Strategic Profile hidden form and summary do not occupy visual space", () => {
    const css = fs.readFileSync("frontend/style.css", "utf8");

    assert.match(css, /\.profile-form\[hidden\],\s*\.profile-summary\[hidden\]\s*{\s*display:\s*none;/);
});

test("initial canonical portfolio state is empty", () => {
    assert.deepEqual(
        JSON.parse(JSON.stringify(context.getCanonicalPortfolioPositions())),
        []
    );
});

const CANONICAL_POSITION = Object.freeze({
    institution: "UBS",
    owner: "JOLIKA",
    account: null,
    asset_class: "FIXED_INCOME",
    asset_subclass: null,
    asset_name: "Treasury Bond",
    identifier: "US912810TM09",
    identifier_type: "ISIN",
    quantity: "10.0000",
    unit_price: "98.1250",
    market_value: "981.25000000",
    currency: "USD",
    portfolio_weight: "0.125000",
    reference_date: "2026-07-29",
    source_file: "ubs.csv",
    ignored_field: "must not be sent"
});


test("does not hydrate portfolios from dashboard without tab import confirmation", () => {
    const dashboard = {
        positions: [CANONICAL_POSITION],
        institutions: [{ name: "UBS" }],
        consolidated: {
            institution_count: 1,
            position_count: 1,
            unique_asset_count: 1,
            repeated_asset_count: 0,
            totals_by_currency: { USD: "981.25000000" },
            warnings: []
        },
        session: {
            last_import_at: "2026-07-29T00:00:00+00:00",
            institution_count: 1,
            position_count: 1,
            analyzed_institutions: ["UBS"],
            status: "active"
        }
    };

    const empty = context.emptyPortfolioDashboard(dashboard);

    assert.equal(context.shouldHydratePortfolioDashboard(dashboard), false);
    assert.deepEqual(JSON.parse(JSON.stringify(empty.positions)), []);
    assert.deepEqual(JSON.parse(JSON.stringify(empty.institutions)), []);
    assert.equal(empty.consolidated.position_count, 0);
    assert.equal(empty.session.status, "waiting_import");
});

test("hydrates portfolios only after successful tab import confirmation", () => {
    const storage = new Map();
    context.window = {
        sessionStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, value); },
            removeItem(key) { storage.delete(key); }
        }
    };
    const dashboard = {
        positions: [CANONICAL_POSITION],
        session: { status: "active" }
    };

    context.markPortfolioImportConfirmed();

    assert.equal(context.shouldHydratePortfolioDashboard(dashboard), true);

    context.clearPortfolioImportConfirmation();
    assert.equal(context.shouldHydratePortfolioDashboard(dashboard), false);

    delete context.window;
});

test("DailyRequestBuilder builds an empty collection", () => {
    assert.deepEqual(context.DailyRequestBuilder.build([]), []);
});

test("DailyRequestBuilder preserves exactly the 15 canonical fields", () => {
    const [position] = context.DailyRequestBuilder.build([CANONICAL_POSITION]);

    assert.deepEqual(Object.keys(position), [
        "institution", "owner", "account", "asset_class", "asset_subclass",
        "asset_name", "identifier", "identifier_type", "quantity", "unit_price",
        "market_value", "currency", "portfolio_weight", "reference_date", "source_file"
    ]);
    assert.equal(position.quantity, "10.0000");
    assert.equal(position.unit_price, "98.1250");
    assert.equal(position.market_value, "981.25000000");
    assert.equal(position.portfolio_weight, "0.125000");
    assert.equal(position.reference_date, "2026-07-29");
    assert.equal(position.account, null);
    assert.equal(position.asset_subclass, null);
});

test("DailyRequestBuilder copies multiple positions without mutating its input", () => {
    const input = [
        { ...CANONICAL_POSITION },
        { ...CANONICAL_POSITION, institution: "Santander", reference_date: null }
    ];
    const before = JSON.stringify(input);
    const result = context.DailyRequestBuilder.build(input);

    assert.equal(result.length, 2);
    assert.equal(result[1].institution, "Santander");
    assert.equal(result[1].reference_date, null);
    assert.equal(JSON.stringify(input), before);
    assert.notEqual(result, input);
    assert.notEqual(result[0], input[0]);
});

const UBS_FIXTURE_PATH =
    "frontend/test/fixtures/UBS_Holdings_27_07_2026.csv";

function readUbsFixture() {
    return readCsv(fs.readFileSync(UBS_FIXTURE_PATH, "utf8"));
}

function importUbsPositions(csvData) {
    const headerIndexes = new Map(
        csvData.headers.map((header, index) => [header, index])
    );

    return csvData.dataRows.map((row) => ({
        name: row[headerIndexes.get("DESCRIPTION")],
        ticker: context.parseTipRanksText(row[headerIndexes.get("SYMBOL")]),
        cusip: context.parseTipRanksText(row[headerIndexes.get("CUSIP")])
    }));
}

test("identifies the real UBS holdings export structure", () => {
    const csvData = readUbsFixture();

    assert.deepEqual(
        JSON.parse(JSON.stringify(csvData.headers)),
        [
            "ACCOUNT NUMBER",
            "DESCRIPTION",
            "SYMBOL",
            "CUSIP",
            "QUANTITY",
            "PRICE",
            "AS OF",
            "FACTOR",
            "CHANGE IN PRICE",
            "VALUE",
            "CHANGE IN VALUE",
            "PERCENT CHANGE",
            "YIELD",
            "UNREALIZED GAIN/LOSS $",
            "UNREALIZED GAIN/LOSS %",
            "PERCENT OF PORTFOLIO"
        ]
    );
    assert.equal(context.identifyFileSource(csvData), "Exportação de posições UBS");
});

test("identifies Santander Excel export filenames including macOS renames", () => {
    [
        "your-positions-4005106-17.xlsx",
        "your-positions-4005106-17 2.xlsx",
        "your-positions-4005106-17 (2).xlsx",
        "YOUR-POSITIONS-4005106-17.XLSX"
    ].forEach((fileName) => {
        assert.equal(
            context.identifySantanderExcelSource(fileName),
            "Exportação de posições Santander"
        );
    });
});

test("does not identify similar filenames as Santander Excel exports", () => {
    [
        "your-positions-4005106-38.xls",
        "copy-your-positions-4005106-38.xlsx"
    ].forEach((fileName) => {
        assert.equal(context.identifySantanderExcelSource(fileName), null);
    });
});

test("imports all 28 positions from the real UBS holdings export", () => {
    const csvData = readUbsFixture();
    const positions = importUbsPositions(csvData);

    assert.equal(csvData.dataRows.length, 28);
    assert.equal(positions.length, 28);
});

test("preserves both UBS cash positions", () => {
    const positions = importUbsPositions(readUbsFixture());
    const cashPositions = positions.filter(({ name }) => [
        "UBS Insured Sweep Program",
        "UBS CASH RESERVE"
    ].includes(name));

    assert.deepEqual(
        Array.from(cashPositions, ({ name }) => name),
        ["UBS Insured Sweep Program", "UBS CASH RESERVE"]
    );
    assert.ok(cashPositions.every(({ ticker }) => ticker === null));
});

test("imports every SYMBOL N/A position with a null ticker", () => {
    const csvData = readUbsFixture();
    const symbolIndex = csvData.headers.indexOf("SYMBOL");
    const unavailableSymbolRows = csvData.dataRows.filter(
        (row) => row[symbolIndex] === "N/A"
    );
    const positions = importUbsPositions(csvData);
    const unavailableTickerPositions = positions.filter(
        ({ ticker }) => ticker === null
    );

    assert.equal(unavailableSymbolRows.length, 15);
    assert.equal(unavailableTickerPositions.length, unavailableSymbolRows.length);
});

test("preserves positions identified only by CUSIP", () => {
    const positions = importUbsPositions(readUbsFixture());
    const cusipOnlyPositions = positions.filter(
        ({ ticker, cusip }) => ticker === null && cusip !== null
    );

    assert.equal(cusipOnlyPositions.length, 13);
    assert.ok(cusipOnlyPositions.some(
        ({ name, cusip }) => name.startsWith("BNP PARIBAS")
            && cusip === "09663N454"
    ));
    assert.ok(cusipOnlyPositions.some(
        ({ name, cusip }) => name === "WARRANTS OAS SA"
            && cusip === "P7331H100"
    ));
});

test("skips multiple introductory lines before the CSV header", () => {
    const result = readCsv([
        "HOLDINGS",
        "Generated on 27/07/2026",
        "Asset,Type,Value",
        "Bond A,Fixed Income,$100"
    ].join("\n"));

    assert.deepEqual(
        JSON.parse(JSON.stringify(result)),
        {
            headers: ["Asset", "Type", "Value"],
            dataRows: [["Bond A", "Fixed Income", "$100"]]
        }
    );
});

test("does not identify a partial UBS header set as UBS", () => {
    const csvData = readCsv([
        "DESCRIPTION,SYMBOL,CUSIP,QUANTITY,PRICE,VALUE",
        "Example,SYM,000000000,1,1,1"
    ].join("\n"));

    assert.equal(context.identifyFileSource(csvData), "CSV Genérico");
});

test("keeps rows matching the header and ignores a short footer", () => {
    const result = readCsv([
        "Asset,Type,Value",
        "Bond A,Fixed Income,$100",
        "Fund B,Fund,$200",
        "Cash,$0"
    ].join("\n"));

    assert.deepEqual(
        JSON.parse(JSON.stringify(result)),
        {
            headers: ["Asset", "Type", "Value"],
            dataRows: [
                ["Bond A", "Fixed Income", "$100"],
                ["Fund B", "Fund", "$200"]
            ]
        }
    );
});

test("ignores empty lines when counting valid data rows", () => {
    const result = readCsv("Asset,Type,Value\n\nBond A,Fixed Income,$100\n,,\nCash,$0\n");

    assert.equal(result.dataRows.length, 1);
});

test("rejects an inconsistent row in the middle of the table", () => {
    assert.throws(
        () => readCsv("Asset,Type,Value\nBond A,$100\nFund B,Fund,$200"),
        /Invalid CSV data row/
    );
});

test("rejects a trailing row with more columns than the header", () => {
    assert.throws(
        () => readCsv("Asset,Value\nBond A,$100\nTotal,$100,extra"),
        /Invalid CSV data row/
    );
});

test("identifies a TipRanks portfolio export from its real headers", () => {
    const csvData = readCsv([
        "Ticker,Name,No. of Shares,Price,% Change,Analyst Consensus,Analyst Price Target %,Analyst Price Target,Smart Score,Holding Value,Holding Gain Change,Holding Gain Change %",
        "ICE,Intercontinental Exchange,10,$175.00,1.25%,Strong Buy,2.86%,$180,9,\"$1,750.00\",$194.44,12.50%"
    ].join("\n"));

    assert.equal(
        context.identifyFileSource(csvData),
        "Exportação de carteira TipRanks"
    );
});

test("identifies the TipRanks format with Stock and Market Value", () => {
    const csvData = readCsv([
        "Stock,Price,Price Change,Market Value,Portfolio Weight,Total Gain/Loss,Smart Score,Analyst Consensus,Price Target",
        "ICE,$175.00,1.25%,\"$1,750.00\",10%,12.50%,9,Strong Buy,$180"
    ].join("\n"));

    assert.equal(
        context.identifyFileSource(csvData),
        "Exportação de carteira TipRanks"
    );
});

test("converts a TipRanks CSV row to an internal ARGOS position", () => {
    const csvData = readCsv([
        "Ticker,Name,No. of Shares,Price,% Change,Analyst Consensus,Analyst Price Target %,Analyst Price Target,Smart Score,Holding Value,Holding Gain Change,Holding Gain Change %",
        "ICE,Intercontinental Exchange,10,$175.00,1.25%,Strong Buy,2.86%,$180,9,\"$1,750.00\",$194.44,12.50%"
    ].join("\n"));

    assert.deepEqual(
        JSON.parse(JSON.stringify(context.transformTipRanksPortfolio(csvData))),
        [{
            institution: "TipRanks",
            ticker: "ICE",
            name: "Intercontinental Exchange",
            shares: 10,
            price: 175,
            holdingValue: 1750,
            smartScore: 9,
            analystConsensus: "Strong Buy",
            analystPriceTarget: 180,
            analystPriceTargetPercent: 2.86
        }]
    );
});

test("converts unavailable TipRanks text fields to null", () => {
    const csvData = readCsv([
        "Ticker,Name,No. of Shares,Analyst Consensus,Smart Score",
        "ICE,N/A,10,-,9",
        "N/A,Acme,5,,8",
        "-,Other,3,Buy,7"
    ].join("\n"));

    const positions = JSON.parse(JSON.stringify(
        context.transformTipRanksPortfolio(csvData)
    ));

    assert.equal(positions[0].name, null);
    assert.equal(positions[0].analystConsensus, null);
    assert.equal(positions[1].ticker, null);
    assert.equal(positions[1].analystConsensus, null);
    assert.equal(positions[2].ticker, null);
});

test("identifies a structurally valid multi-column CSV as generic", () => {
    const csvData = readCsv("Asset,Type,Value\nBond A,Fixed Income,$100");

    assert.equal(context.identifyFileSource(csvData), "CSV Genérico");
});

test("reports an unknown source when no identifier matches", () => {
    const csvData = readCsv("Notes\nImported manually");

    assert.equal(context.identifyFileSource(csvData), null);
});

test("renders the identified source below the file information", () => {
    const children = [];
    const document = context.document;
    document.createElement = () => ({ className: "", textContent: "" });
    const container = {
        append(...elements) {
            children.push(...elements);
        }
    };

    context.renderPortfolioFileSummary(
        container,
        1,
        ["Ticker", "Shares", "Smart Score"],
        "Exportação de carteira TipRanks"
    );

    assert.equal(
        children.at(-1).textContent,
        "Origem identificada: Exportação de carteira TipRanks"
    );
});

test("renders the Santander Excel source identification", () => {
    const children = [];
    const document = context.document;
    document.createElement = () => ({ className: "", textContent: "" });
    const container = {
        append(...elements) {
            children.push(...elements);
        }
    };

    context.renderIdentifiedFileSource(container, "Exportação de posições Santander");

    assert.equal(
        children[0].textContent,
        "Origem identificada: Exportação de posições Santander"
    );
});

test("renders the Santander position count", () => {
    const children = [];
    context.document.createElement = () => ({
        className: "",
        textContent: ""
    });
    const container = {
        append(...elements) {
            children.push(...elements);
        }
    };

    context.renderSantanderPositionCount(container, 17);

    assert.deepEqual(
        children.map((child) => child.textContent),
        ["Quantidade de posições encontradas: 17"]
    );
});

test("shows Santander source and count after selecting its Excel", async () => {
    const elements = new Map();
    const fileInput = {
        files: [{
            name: "your-positions-4005106-38.xlsx",
            async arrayBuffer() {
                return Uint8Array.from([1, 2, 3]).buffer;
            }
        }],
        addEventListener(_event, listener) {
            this.changeListener = listener;
        }
    };
    elements.set("portfolioFile", fileInput);
    elements.set("portfolioFileName", { textContent: "" });
    elements.set("portfolioFileSummary", createElement("div"));
    elements.set("tipRanksPreview", { hidden: false });
    elements.set("tipRanksPreviewContent", createElement("div"));
    context.document.getElementById = (id) => elements.get(id);
    context.document.createElement = createElement;
    context.btoa = (value) => Buffer.from(value, "binary").toString("base64");
    context.fetch = async () => ({
        ok: true,
        async json() {
            return {
                ok: true,
                source: "Exportação de posições Santander",
                position_count: 23
            };
        }
    });

    context.setupPortfolioFilePicker();
    await fileInput.changeListener();

    assert.deepEqual(
        elements.get("portfolioFileSummary").children.map(
            (child) => child.textContent
        ),
        [
            "Origem identificada: Exportação de posições Santander",
            "Quantidade de posições encontradas: 23"
        ]
    );
});


test("inspects every selected Santander Excel candidate", async () => {
    const elements = new Map();
    const files = [
        {
            name: "your-positions-4005106-17.xlsx",
            async arrayBuffer() { return Uint8Array.from([1]).buffer; }
        },
        {
            name: "your-positions-4005106-17 (2).xlsx",
            async arrayBuffer() { return Uint8Array.from([2]).buffer; }
        }
    ];
    const fileInput = {
        files,
        addEventListener(_event, listener) { this.changeListener = listener; }
    };
    elements.set("portfolioFile", fileInput);
    elements.set("portfolioFileName", { textContent: "" });
    elements.set("portfolioFileSummary", createElement("div"));
    elements.set("tipRanksPreview", { hidden: false });
    elements.set("tipRanksPreviewContent", createElement("div"));
    context.document.getElementById = (id) => elements.get(id);
    context.document.createElement = createElement;
    context.btoa = (value) => Buffer.from(value, "binary").toString("base64");
    const inspectedNames = [];
    context.fetch = async (_url, options) => {
        inspectedNames.push(JSON.parse(options.body).file.name);
        return {
            ok: true,
            async json() { return { ok: true, position_count: 2 }; }
        };
    };

    context.setupPortfolioFilePicker();
    await fileInput.changeListener();

    assert.deepEqual(inspectedNames, files.map((file) => file.name));
    assert.deepEqual(
        elements.get("portfolioFileSummary").children.map((child) => child.textContent),
        [
            "Origem identificada: Exportação de posições Santander",
            "Quantidade de posições encontradas: 4"
        ]
    );
});

test("does not treat an invalid Santander xlsx as CSV", async () => {
    const elements = new Map();
    const fileInput = {
        files: [{
            name: "your-positions-4005106-17.xlsx",
            async arrayBuffer() { return Uint8Array.from([9]).buffer; }
        }],
        addEventListener(_event, listener) { this.changeListener = listener; }
    };
    elements.set("portfolioFile", fileInput);
    elements.set("portfolioFileName", { textContent: "" });
    elements.set("portfolioFileSummary", createElement("div"));
    elements.set("tipRanksPreview", { hidden: false });
    elements.set("tipRanksPreviewContent", createElement("div"));
    context.document.getElementById = (id) => elements.get(id);
    context.document.createElement = createElement;
    context.btoa = (value) => Buffer.from(value, "binary").toString("base64");
    context.fetch = async () => ({
        ok: false,
        async json() { return { ok: false, error: "inválido" }; }
    });

    context.setupPortfolioFilePicker();
    await fileInput.changeListener();

    assert.deepEqual(
        elements.get("portfolioFileSummary").children.map((child) => child.textContent),
        [
            "Origem identificada: Exportação de posições Santander",
            "Não foi possível ler o Excel do Santander."
        ]
    );
});

test("renders the UBS holdings source below the file information", () => {
    const children = [];
    const document = context.document;
    document.createElement = () => ({ className: "", textContent: "" });
    const container = {
        append(...elements) {
            children.push(...elements);
        }
    };

    context.renderPortfolioFileSummary(
        container,
        1,
        ["DESCRIPTION", "SYMBOL", "CUSIP"],
        "Exportação de posições UBS"
    );

    assert.equal(
        children.at(-1).textContent,
        "Origem identificada: Exportação de posições UBS"
    );
});

test("renders the unknown source message when detection fails", () => {
    const children = [];
    const document = context.document;
    document.createElement = () => ({ className: "", textContent: "" });
    const container = {
        append(...elements) {
            children.push(...elements);
        }
    };

    context.renderPortfolioFileSummary(container, 1, ["Notes"], null);

    assert.equal(children.at(-1).textContent, "Origem desconhecida.");
});

function createElement(tagName) {
    return {
        tagName,
        children: [],
        className: "",
        textContent: "",
        attributes: {},
        append(...elements) {
            this.children.push(...elements);
        },
        appendChild(element) {
            this.children.push(element);
        },
        replaceChildren(...elements) {
            this.children = elements;
        },
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
        querySelector() {
            return null;
        }
    };
}

test("renders exactly the internal TipRanks fields for at most 10 positions", () => {
    context.document.createElement = createElement;
    const section = { hidden: true };
    const container = createElement("div");
    const positions = Array.from({ length: 12 }, (_, index) => ({
        institution: "TipRanks",
        ticker: `T${index}`,
        name: `Asset ${index}`,
        shares: index,
        price: index + 1,
        holdingValue: index + 2,
        smartScore: index + 3,
        analystConsensus: "Buy",
        analystPriceTarget: index + 4,
        analystPriceTargetPercent: index + 5
    }));
    const originalPositions = JSON.stringify(positions);

    context.renderTipRanksPreview(section, container, positions);

    const [wrapper, total] = container.children;
    const [table] = wrapper.children;
    const [head, body] = table.children;
    assert.deepEqual(
        head.children[0].children.map((cell) => cell.textContent),
        [
            "Instituição", "Código", "Nome", "Quantidade", "Preço",
            "Valor da posição", "Nota", "Consenso dos analistas",
            "Preço-alvo dos analistas", "Variação até o preço-alvo"
        ]
    );
    assert.equal(body.children.length, 10);
    assert.deepEqual(
        body.children[0].children.map((cell) => cell.textContent),
        ["TipRanks", "T0", "Asset 0", "0", "1", "2", "3", "Buy", "4", "5"]
    );
    assert.equal(total.textContent, "Total de posições convertidas: 12");
    assert.equal(section.hidden, false);
    assert.equal(JSON.stringify(positions), originalPositions);
});

test("hides and clears the TipRanks preview", () => {
    const section = { hidden: false };
    const container = createElement("div");
    container.children = [createElement("table")];

    context.hideTipRanksPreview(section, container);

    assert.equal(section.hidden, true);
    assert.deepEqual(container.children, []);
});

test("renders null TipRanks values as an em dash", () => {
    context.document.createElement = createElement;
    const section = { hidden: true };
    const container = createElement("div");
    const position = {
        institution: "TipRanks",
        ticker: "ICE",
        name: null
    };

    context.renderTipRanksPreview(section, container, [position]);

    const body = container.children[0].children[0].children[1];
    assert.equal(body.children[0].children[2].textContent, "—");
    assert.equal(body.children[0].children[3].textContent, "");
});

test("renders the imported session dashboard after a successful import", async () => {
    const elements = new Map();
    const file = { name: "holdings.csv" };
    const input = {
        files: [file],
        addEventListener(_event, listener) {
            this.changeListener = listener;
        }
    };
    const button = {
        disabled: true,
        addEventListener(_event, listener) {
            this.clickListener = listener;
        }
    };
    elements.set("portfolioFile", input);
    elements.set("portfolioFileName", { textContent: "" });
    elements.set("portfolioFileSummary", createElement("div"));
    elements.set("tipRanksPreview", { hidden: true });
    elements.set("tipRanksPreviewContent", createElement("div"));
    elements.set("importPortfolios", button);
    elements.set("importProgress", { hidden: true });
    elements.set("importProgressBar", { value: 0 });
    elements.set("importProgressText", { textContent: "" });
    context.document.getElementById = (id) => elements.get(id);
    context.FormData = class {
        append() {}
    };
    const importedDashboard = {
        session: {
            last_import_at: "2026-07-28T14:35:00Z",
            institution_count: 1
        },
        daily_situation: [{
            status: "completed",
            message: "1 instituição analisada"
        }],
        modules: [{
            id: "portfolios",
            title: "Carteiras",
            status: "completed",
            message: "1 instituição analisada"
        }]
    };
    const canonicalPositions = [{
        institution: "UBS",
        owner: "JOLIKA",
        market_value: "152.4300"
    }];
    let renderedDashboard = null;
    context.renderDashboard = (dashboard) => {
        renderedDashboard = dashboard;
    };
    context.fetch = async () => ({
        ok: true,
        async json() {
            return {
                ok: true,
                dashboard: importedDashboard,
                positions: canonicalPositions
            };
        }
    });

    context.setupPortfolioFilePicker();
    await button.clickListener();

    assert.equal(renderedDashboard, importedDashboard);
    assert.deepEqual(
        JSON.parse(JSON.stringify(context.getCanonicalPortfolioPositions())),
        canonicalPositions
    );
    assert.equal(elements.get("importProgressBar").value, 100);
    assert.equal(
        elements.get("importProgressText").textContent,
        "Importação concluída."
    );
});

test("renders an empty dashboard after a failed portfolio import", async () => {
    const elements = new Map();
    const file = { name: "your-positions-4005106-38.xlsx" };
    const input = {
        files: [file],
        addEventListener(_event, listener) {
            this.changeListener = listener;
        }
    };
    const button = {
        disabled: true,
        addEventListener(_event, listener) {
            this.clickListener = listener;
        }
    };
    elements.set("portfolioFile", input);
    elements.set("portfolioFileName", { textContent: "" });
    elements.set("portfolioFileSummary", createElement("div"));
    elements.set("tipRanksPreview", { hidden: true });
    elements.set("tipRanksPreviewContent", createElement("div"));
    elements.set("importPortfolios", button);
    elements.set("importProgress", { hidden: true });
    elements.set("importProgressBar", { value: 0 });
    elements.set("importProgressText", { textContent: "" });
    context.document.getElementById = (id) => elements.get(id);
    context.FormData = class {
        append() {}
    };
    const emptyDashboard = {
        institutions: [],
        consolidated: { position_count: 0 },
        daily_situation: [{ status: "waiting", message: "Nenhuma carteira carregada" }]
    };
    let renderedDashboard = null;
    context.renderDashboard = (dashboard) => {
        renderedDashboard = dashboard;
    };
    context.storeCanonicalPortfolioPositions([{ institution: "Santander" }]);
    context.fetch = async () => ({
        ok: false,
        async json() {
            return {
                ok: false,
                error: "Instituição não reconhecida: your-positions-4005106-38.xlsx.",
                dashboard: emptyDashboard,
                positions: []
            };
        }
    });

    context.setupPortfolioFilePicker();
    await button.clickListener();

    assert.equal(renderedDashboard, emptyDashboard);
    assert.deepEqual(
        JSON.parse(JSON.stringify(context.getCanonicalPortfolioPositions())),
        []
    );
    assert.equal(elements.get("importProgressBar").value, 0);
    assert.match(
        elements.get("importProgressText").textContent,
        /Instituição não reconhecida/
    );
});

test("stores official positions as immutable frontend copies", () => {
    const payload = [{
        institution: "UBS",
        owner: "JOLIKA",
        market_value: "152.4300"
    }, {
        institution: "Santander",
        owner: "NEI",
        market_value: "20.00"
    }];
    context.storeCanonicalPortfolioPositions(payload);
    payload[0].market_value = "changed";
    const firstRead = context.getCanonicalPortfolioPositions();
    firstRead[0].institution = "changed";
    const stored = JSON.parse(JSON.stringify(
        context.getCanonicalPortfolioPositions()
    ));

    assert.deepEqual(stored, [{
        institution: "UBS",
        owner: "JOLIKA",
        market_value: "152.4300"
    }, {
        institution: "Santander",
        owner: "NEI",
        market_value: "20.00"
    }]);
});

test("keeps canonical positions separate from the TipRanks preview", () => {
    context.storeCanonicalPortfolioPositions([{
        institution: "UBS", owner: "JOLIKA", market_value: "1.00"
    }]);
    context.transformTipRanksPortfolio({
        headers: ["Ticker", "Shares", "Smart Score"],
        dataRows: [["TIP", "1", "8"]]
    });

    assert.equal(
        context.getCanonicalPortfolioPositions()[0].institution,
        "UBS"
    );
});

test("starts canonical portfolio state empty", () => {
    context.storeCanonicalPortfolioPositions([]);
    assert.deepEqual(
        JSON.parse(JSON.stringify(context.getCanonicalPortfolioPositions())),
        []
    );
});

test("keeps portfolios empty while loading an unconfirmed existing dashboard", async () => {
    const dashboard = {
        positions: [{
            institution: "Santander",
            owner: "JOLIKA",
            market_value: "99.9900"
        }],
        institutions: [{ name: "Santander" }],
        consolidated: { position_count: 1 },
        session: { status: "active" }
    };
    let rendered = null;
    context.fetch = async (url, options) => {
        assert.equal(url, "/api/dashboard");
        assert.equal(options.cache, "no-store");
        return { ok: true, async json() { return dashboard; } };
    };
    context.renderDashboard = (payload) => { rendered = payload; };

    await context.loadDashboard();

    assert.notEqual(rendered, dashboard);
    assert.deepEqual(
        JSON.parse(JSON.stringify(context.getCanonicalPortfolioPositions())),
        []
    );
    assert.equal(rendered.consolidated.position_count, 0);
});

test("formats the last import date and time returned by the dashboard", () => {
    const originalTimezone = process.env.TZ;
    process.env.TZ = "UTC";

    try {
        const formatted = context.formatUpdatedAt("2026-07-28T14:35:00Z");

        assert.match(formatted, /28\/07\/2026/);
        assert.match(formatted, /14:35/);
    } finally {
        if (originalTimezone === undefined) {
            delete process.env.TZ;
        } else {
            process.env.TZ = originalTimezone;
        }
    }
});

test("uses a natural empty state when no import has been completed", () => {
    assert.equal(context.formatUpdatedAt(null), "Nenhuma importação realizada");
    assert.equal(context.formatUpdatedAt("invalid"), "Nenhuma importação realizada");
});

test("pluralizes interface counters in Portuguese", () => {
    assert.equal(context.formatCount(0, "item", "itens"), "0 itens");
    assert.equal(context.formatCount(1, "item", "itens"), "1 item");
    assert.equal(context.formatCount(2, "item", "itens"), "2 itens");
});

test("translates and pluralizes portfolio warnings", () => {
    assert.equal(
        context.translateWarning("Santander: 1 duplicated asset(s)"),
        "Santander: 1 ativo duplicado"
    );
    assert.equal(
        context.translateWarning("UBS: 15 position(s) without symbol"),
        "UBS: 15 posições sem ticker identificado"
    );
    assert.equal(
        context.translateWarning("1 position(s) without symbol"),
        "1 posição sem ticker identificado"
    );
});

test("formats currencies according to the approved official standard", () => {
    assert.equal(context.formatCurrency("2976187.35", "USD"), "US$ 2,976,187.35");
    assert.equal(context.formatCurrency("86036.66", "EUR"), "€ 86,036.66");
    assert.equal(context.formatCurrency("2976187.35", "BRL"), "R$ 2.976.187,35");
    assert.equal(context.formatCurrency("invalid", "BRL"), "Valor não informado");
});

test("formats quantities and percentages in Brazilian Portuguese", () => {
    assert.equal(context.formatQuantity("2976.18735"), "2.976,18735");
    assert.equal(context.formatPercentage("12.5"), "12,50%");
});

function dailyResponse(overrides = {}) {
    return {
        contract_version: "1.0",
        status: "SUCCESS",
        generated_at: "2026-07-30T12:00:00+00:00",
        experience_status: "READY",
        header: {
            greeting: "Bom dia, Nei.",
            display_date: "quinta-feira, 30 de julho de 2026",
            period: "MORNING"
        },
        message: { title: "Resumo do dia", text: "Decisão com clareza." },
        facts: [{ id: "f1", category: "Mercados", text: "Fato <b>seguro</b>", importance: "HIGH" }],
        priorities: [{ fact_id: "f1", level: "HIGH", label: "Alta", title: "Prioridade", reason: "Razão" }],
        analyses: [{ fact_id: "f1", action: "Analisar", title: "Análise", reason: "Motivo" }],
        blocks: [
            { type: "FACTS", visible: true, title: "Fatos importantes", items: [] },
            { type: "PRIORITIES", visible: true, title: "Prioridades do dia", items: [] },
            { type: "ANALYSES", visible: true, title: "Análises", items: [] }
        ],
        summary: {
            fact_count: 1,
            priority_count: 1,
            analysis_count: 1,
            visible_block_count: 3,
            requires_attention: true,
            requires_decision: false
        },
        error: null,
        ...overrides
    };
}

function dailyDom() {
    const elements = new Map();
    [
        "greeting", "currentDate", "lastUpdateLabel", "lastUpdate"
    ].forEach((id) => elements.set(id, createElement("span")));
    [
        ["daily-facts", "importantFacts"],
        ["daily-priorities", "dailyPriorities"],
        ["daily-analyses", "dailyAnalyses"],
        ["daily-market-reaction", "marketReaction"]
    ].forEach(([panelId, listId]) => {
        const panel = createElement("article");
        panel.hidden = true;
        const container = createElement("div");
        elements.set(panelId, panel);
        elements.set(listId, container);
    });
    ["market-agenda", "daily-error", "daily-loading", "daily-investment-impact", "daily-decision"].forEach((id) => {
        const element = createElement("div");
        element.hidden = true;
        elements.set(id, element);
    });
    const agendaPanel = createElement("article");
    agendaPanel.hidden = true;
    elements.set("marketAgendaPanel", agendaPanel);
    elements.set("marketAgenda", createElement("div"));
    ["factsCount", "marketReactionCount", "neiInvestmentImpact", "jolikaInvestmentImpact"].forEach((id) => {
        elements.set(id, createElement("div"));
    });
    context.document.createElement = createElement;
    context.document.getElementById = (id) => elements.get(id);
    return elements;
}

test("DailyFrontendClient posts the official request and returns JSON on HTTP 200", async () => {
    const expected = dailyResponse();
    const request = { positions: [], fact_candidates: [], reference_date: null };
    let call;
    const client = new context.DailyClientForTest(async (url, options) => {
        call = { url, options };
        return { status: 200, async json() { return expected; } };
    });

    assert.equal(await client.loadExperience(request), expected);
    assert.equal(call.url, "/api/daily-experience");
    assert.equal(call.options.method, "POST");
    assert.deepEqual(
        JSON.parse(JSON.stringify(call.options.headers)),
        { "Content-Type": "application/json" }
    );
    assert.deepEqual(JSON.parse(call.options.body), request);
});

test("DailyFrontendClient calls fetch without changing its receiver", async () => {
    const expected = dailyResponse();
    const fetchImplementation = async function () {
        assert.equal(this, undefined);
        return { status: 200, async json() { return expected; } };
    };
    const client = new context.DailyClientForTest(fetchImplementation);

    assert.equal(await client.loadExperience({}), expected);
});

test("DailyFrontendClient accepts complete 1.3 and requires decision contexts", async () => {
    const complete = dailyResponse({
        contract_version: "1.3", market_agenda: [], impact_assessments: [],
        decision_contexts: []
    });
    const accepted = new context.DailyClientForTest(async () => ({
        status: 200, async json() { return complete; }
    }));
    assert.equal(await accepted.loadExperience({}), complete);

    const incomplete = dailyResponse({
        contract_version: "1.3", market_agenda: [], impact_assessments: []
    });
    const rejected = new context.DailyClientForTest(async () => ({
        status: 200, async json() { return incomplete; }
    }));
    await assert.rejects(rejected.loadExperience({}), /Erro interno\./);
});

test("DailyFrontendClient accepts 1.4 only with structured data quality", async () => {
    const complete = {
        contract_version: "1.4", status: "SUCCESS", generated_at: "2026-07-30T12:00:00+00:00",
        experience_status: "READY", header: {}, message: {}, facts: [], priorities: [],
        analyses: [], blocks: [], market_agenda: [], impact_assessments: [],
        decision_contexts: [], summary: {}, error: null,
        data_quality: { status: "HEALTHY", summary: { errors: 0, warnings: 0, infos: 0 }, diagnostics: [] }
    };
    const client = new context.DailyClientForTest(async () => ({ status: 200, json: async () => complete }));
    assert.equal((await client.loadExperience({})).contract_version, "1.4");
    const invalid = { ...complete }; delete invalid.data_quality;
    const invalidClient = new context.DailyClientForTest(async () => ({ status: 200, json: async () => invalid }));
    await assert.rejects(() => invalidClient.loadExperience({}), /Erro interno/);
});

test("DailyFrontendClient accepts 1.5 only with orchestrated experience status", async () => {
    const complete = dailyResponse({
        contract_version: "1.5", market_agenda: [], impact_assessments: [],
        decision_contexts: [], data_quality: { status: "HEALTHY", diagnostics: [] },
        experience: { status: "READY" }
    });
    const client = new context.DailyClientForTest(async () => ({
        status: 200, async json() { return complete; }
    }));
    assert.equal((await client.loadExperience({})).experience.status, "READY");
    const invalid = { ...complete, experience: { status: "UNKNOWN" } };
    const invalidClient = new context.DailyClientForTest(async () => ({
        status: 200, async json() { return invalid; }
    }));
    await assert.rejects(invalidClient.loadExperience({}), /Erro interno/);
});

for (const overrides of [
    { contract_version: "2.0" },
    { experience_status: "UNKNOWN" },
    { blocks: [{ type: "UNKNOWN", visible: true, title: "X", items: [] }] }
]) {
    test(`DailyFrontendClient rejects incompatible contract ${JSON.stringify(overrides)}`, async () => {
        const client = new context.DailyClientForTest(async () => ({
            status: 200,
            async json() { return dailyResponse(overrides); }
        }));
        await assert.rejects(client.loadExperience({}), /Erro interno\./);
    });
}

test("DailyFrontendClient rejects a response missing a required field", async () => {
    const payload = dailyResponse();
    delete payload.summary;
    const client = new context.DailyClientForTest(async () => ({
        status: 200,
        async json() { return payload; }
    }));
    await assert.rejects(client.loadExperience({}), /Erro interno\./);
});

for (const status of [400, 500]) {
    test(`DailyFrontendClient uses the API message on HTTP ${status}`, async () => {
        const client = new context.DailyClientForTest(async () => ({
            status,
            async json() { return { error: { message: `Falha ${status}.` } }; }
        }));
        await assert.rejects(client.loadExperience({}), new RegExp(`Falha ${status}`));
    });
}

test("DailyFrontendClient uses a safe fallback for HTTP errors without a message", async () => {
    const client = new context.DailyClientForTest(async () => ({
        status: 500,
        async json() { return {}; }
    }));
    await assert.rejects(client.loadExperience({}), /Erro interno\./);
});

test("DailyFrontendClient reports a friendly network error", async () => {
    const client = new context.DailyClientForTest(async () => {
        throw new Error("private stack");
    });
    await assert.rejects(
        client.loadExperience({}),
        /Não foi possível carregar a experiência diária\./
    );
});

test("renders header and facts in the executive cockpit", () => {
    const elements = dailyDom();
    context.DailyRendererForTest.render(dailyResponse());

    assert.equal(elements.get("greeting").textContent, "Bom dia, Nei.");
    assert.equal(elements.get("importantFacts").children[0].children[1].children[0].textContent, "Fato <b>seguro</b>");
    assert.equal("innerHTML" in elements.get("importantFacts").children[0].children[1].children[0], false);
});

test("renders the same DOM for the same DailyApiResponse", () => {
    const snapshot = () => {
        const elements = dailyDom();
        context.DailyRendererForTest.render(dailyResponse());
        return JSON.stringify([...elements].map(([id, element]) => [id, element]));
    };
    assert.equal(snapshot(), snapshot());
});

test("loadDailyExperience exposes loading, prevents concurrent loads and renders success", async () => {
    const elements = dailyDom();
    let resolve;
    let calls = 0;
    const client = {
        loadExperience() {
            calls += 1;
            return new Promise((done) => { resolve = done; });
        }
    };
    const first = context.loadDailyExperience(client);
    const second = context.loadDailyExperience(client);
    assert.equal(calls, 1);
    assert.equal(elements.get("daily-loading").hidden, false);
    resolve(dailyResponse());
    await Promise.all([first, second]);
    assert.equal(elements.get("greeting").textContent, "Bom dia, Nei.");
});

test("loadDailyExperience leaves official portfolio selection to the backend", async () => {
    dailyDom();
    context.storeCanonicalPortfolioPositions([CANONICAL_POSITION]);
    let request;

    await context.loadDailyExperience({
        async loadExperience(payload) {
            request = payload;
            return dailyResponse();
        }
    });

    assert.deepEqual(JSON.parse(JSON.stringify(request)), JSON.parse(JSON.stringify({
        positions: [],
        fact_candidates: [],
        reference_date: null
    })));
});

test("loadDailyExperience renders only the safe failure message", async () => {
    const elements = dailyDom();
    await context.loadDailyExperience({
        async loadExperience() {
            throw new Error("Não foi possível carregar a experiência diária.");
        }
    });
    assert.equal(elements.get("daily-error").textContent,
        "Não foi possível preparar a experiência diária.");
    assert.equal(elements.get("daily-loading").hidden, true);
});

test("records and clears institution import errors in persistent storage", () => {
    const originalWindow = context.window;
    const storage = new Map();
    context.window = {
        localStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, value); }
        }
    };

    try {
        context.setInstitutionImportError(["Santander"], "Falha", "import_failed");
        let status = JSON.parse(storage.get("argos.institution-import-status"));
        assert.equal(status.santander.status, "error");
        assert.equal(status.santander.reason, "import_failed");

        context.clearInstitutionImportError(["Santander"]);
        status = JSON.parse(storage.get("argos.institution-import-status"));
        assert.equal(status.santander, undefined);
    } finally {
        context.window = originalWindow;
    }
});
