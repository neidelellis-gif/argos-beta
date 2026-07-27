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
vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), context);

function readCsv(content) {
    return context.getCsvDataRows(context.parseCsv(content));
}

test("identifies the real UBS holdings export structure", () => {
    const csvData = readCsv(fs.readFileSync(
        "frontend/test/fixtures/UBS_Holdings_27_07_2026.csv",
        "utf8"
    ));

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
    assert.equal(context.identifyFileSource(csvData), "UBS Holdings Export");
});

test("keeps compatibility with the alternate UBS portfolio header", () => {
    const csvData = readCsv([
        "DESCRIPTION,SYMBOL,CUSIP,QUANTITY,PRICE,VALUE,% OF PORTFOLIO",
        "Example,SYM,000000000,1,1,1,1%"
    ].join("\n"));

    assert.equal(context.identifyFileSource(csvData), "UBS Holdings Export");
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
        "TipRanks Portfolio Export"
    );
});

test("identifies the TipRanks format with Stock and Market Value", () => {
    const csvData = readCsv([
        "Stock,Price,Price Change,Market Value,Portfolio Weight,Total Gain/Loss,Smart Score,Analyst Consensus,Price Target",
        "ICE,$175.00,1.25%,\"$1,750.00\",10%,12.50%,9,Strong Buy,$180"
    ].join("\n"));

    assert.equal(
        context.identifyFileSource(csvData),
        "TipRanks Portfolio Export"
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
        "TipRanks Portfolio Export"
    );

    assert.equal(
        children.at(-1).textContent,
        "Origem identificada: TipRanks Portfolio Export"
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
        "UBS Holdings Export"
    );

    assert.equal(
        children.at(-1).textContent,
        "Origem identificada: UBS Holdings Export"
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
        append(...elements) {
            this.children.push(...elements);
        },
        appendChild(element) {
            this.children.push(element);
        },
        replaceChildren(...elements) {
            this.children = elements;
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
            "Institution", "Ticker", "Name", "Shares", "Price",
            "Holding Value", "Smart Score", "Analyst Consensus",
            "Analyst Price Target", "Analyst Price Target %"
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
