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
