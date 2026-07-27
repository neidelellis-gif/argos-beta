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
