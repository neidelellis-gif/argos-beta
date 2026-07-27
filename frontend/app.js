"use strict";

const STATUS_LABELS = {
    pendente: "Pendente",
    em_construcao: "Em construção",
    pronto: "Pronto"
};

const FILE_SOURCE_IDENTIFIERS = [
    {
        source: "TipRanks Portfolio Export",
        matches({ headers }) {
            const normalizedHeaders = new Set(headers.map(normalizeCsvHeader));
            const hasAssetIdentifier = ["ticker", "symbol", "stock"].some(
                (header) => normalizedHeaders.has(header)
            );
            const hasPortfolioData = [
                "shares",
                "quantity",
                "market value",
                "no of shares",
                "holding value"
            ].some((header) => normalizedHeaders.has(header));
            const hasTipRanksData = [
                "analyst consensus",
                "price target",
                "smart score",
                "tipranks smart score"
            ].some((header) => normalizedHeaders.has(header));

            return hasAssetIdentifier && hasPortfolioData && hasTipRanksData;
        }
    },
    {
        source: "CSV Genérico",
        matches({ headers }) {
            return headers.length > 1;
        }
    }
];

const TIPRANKS_PREVIEW_COLUMNS = [
    ["Institution", "institution"],
    ["Ticker", "ticker"],
    ["Name", "name"],
    ["Shares", "shares"],
    ["Price", "price"],
    ["Holding Value", "holdingValue"],
    ["Smart Score", "smartScore"],
    ["Analyst Consensus", "analystConsensus"],
    ["Analyst Price Target", "analystPriceTarget"],
    ["Analyst Price Target %", "analystPriceTargetPercent"]
];

let importedPortfolioPositions = [];

function normalizeCsvHeader(header) {
    return header
        .replace(/^\uFEFF/, "")
        .trim()
        .toLowerCase()
        .replace(/[._-]+/g, " ")
        .replace(/\s+/g, " ");
}

function identifyFileSource(csvData) {
    const identifier = FILE_SOURCE_IDENTIFIERS.find(
        (candidate) => candidate.matches(csvData)
    );

    return identifier ? identifier.source : null;
}

function parseTipRanksNumber(value) {
    const normalizedValue = value.trim();

    if (!normalizedValue || normalizedValue === "-") {
        return null;
    }

    const isNegative = normalizedValue.startsWith("(")
        && normalizedValue.endsWith(")");
    const number = Number(normalizedValue.replace(/[$,%()\s]/g, ""));

    if (!Number.isFinite(number)) {
        return null;
    }

    return isNegative ? -number : number;
}

function parseTipRanksText(value) {
    const normalizedValue = value.trim();

    return !normalizedValue || normalizedValue.toUpperCase() === "N/A"
        || normalizedValue === "-"
        ? null
        : normalizedValue;
}

function transformTipRanksPortfolio({ headers, dataRows }) {
    const headerIndexes = new Map(
        headers.map((header, index) => [normalizeCsvHeader(header), index])
    );
    const valueFor = (row, ...names) => {
        const name = names.find((candidate) => headerIndexes.has(candidate));
        return name === undefined ? "" : row[headerIndexes.get(name)].trim();
    };

    return dataRows
        .filter((row) => valueFor(row, "ticker", "symbol", "stock"))
        .map((row) => ({
            institution: "TipRanks",
            ticker: parseTipRanksText(
                valueFor(row, "ticker", "symbol", "stock")
            ),
            name: parseTipRanksText(
                valueFor(row, "name", "company", "company name")
            ),
            shares: parseTipRanksNumber(
                valueFor(row, "shares", "quantity", "no of shares")
            ),
            price: parseTipRanksNumber(valueFor(row, "price")),
            holdingValue: parseTipRanksNumber(
                valueFor(row, "holding value", "market value")
            ),
            smartScore: parseTipRanksNumber(
                valueFor(row, "smart score", "tipranks smart score")
            ),
            analystConsensus: parseTipRanksText(
                valueFor(row, "analyst consensus")
            ),
            analystPriceTarget: parseTipRanksNumber(
                valueFor(row, "analyst price target", "price target")
            ),
            analystPriceTargetPercent: parseTipRanksNumber(
                valueFor(row, "analyst price target %", "price target %")
            )
        }));
}

function setGreeting() {
    const greeting = document.getElementById("greeting");
    const currentDate = document.getElementById("currentDate");
    const now = new Date();
    const hour = now.getHours();

    if (hour < 12) {
        greeting.textContent = "Bom dia, Nei.";
    } else if (hour < 18) {
        greeting.textContent = "Boa tarde, Nei.";
    } else {
        greeting.textContent = "Boa noite, Nei.";
    }

    currentDate.textContent = new Intl.DateTimeFormat("pt-BR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
    }).format(now);
}

function setupPortfolioFilePicker() {
    const fileInput = document.getElementById("portfolioFile");
    const fileName = document.getElementById("portfolioFileName");
    const fileSummary = document.getElementById("portfolioFileSummary");
    const previewSection = document.getElementById("tipRanksPreview");
    const previewContent = document.getElementById("tipRanksPreviewContent");

    fileInput.addEventListener("change", async () => {
        const selectedFile = fileInput.files[0];
        fileName.textContent = selectedFile
            ? selectedFile.name
            : "Nenhum arquivo selecionado";
        fileSummary.replaceChildren();
        hideTipRanksPreview(previewSection, previewContent);

        if (!selectedFile) {
            return;
        }

        if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
            renderPortfolioFileError(fileSummary);
            return;
        }

        try {
            const { headers, dataRows } = getCsvDataRows(
                parseCsv(await selectedFile.text())
            );

            const source = identifyFileSource({ headers, dataRows });

            if (source === "TipRanks Portfolio Export") {
                importedPortfolioPositions = transformTipRanksPortfolio({
                    headers,
                    dataRows
                });
                renderTipRanksPreview(
                    previewSection,
                    previewContent,
                    importedPortfolioPositions
                );
            }

            renderPortfolioFileSummary(
                fileSummary,
                dataRows.length,
                headers,
                source
            );
        } catch (error) {
            renderPortfolioFileError(fileSummary);
        }
    });
}

function hideTipRanksPreview(section, container) {
    section.hidden = true;
    container.replaceChildren();
}

function renderTipRanksPreview(section, container, positions) {
    const tableWrapper = document.createElement("div");
    tableWrapper.className = "tipranks-preview-table-wrapper";

    const table = document.createElement("table");
    table.className = "tipranks-preview-table";

    const header = document.createElement("thead");
    const headerRow = document.createElement("tr");
    TIPRANKS_PREVIEW_COLUMNS.forEach(([label]) => {
        const cell = document.createElement("th");
        cell.scope = "col";
        cell.textContent = label;
        headerRow.appendChild(cell);
    });
    header.appendChild(headerRow);

    const body = document.createElement("tbody");
    positions.slice(0, 10).forEach((position) => {
        const row = document.createElement("tr");
        TIPRANKS_PREVIEW_COLUMNS.forEach(([, property]) => {
            const cell = document.createElement("td");
            const value = position[property];
            cell.textContent = value === null
                ? "—"
                : value === undefined
                    ? ""
                : String(value);
            row.appendChild(cell);
        });
        body.appendChild(row);
    });

    table.append(header, body);
    tableWrapper.appendChild(table);

    const total = document.createElement("p");
    total.className = "tipranks-preview-total";
    total.textContent = `Total de posições convertidas: ${positions.length}`;

    container.replaceChildren(tableWrapper, total);
    section.hidden = false;
}

function parseCsv(content) {
    if (!content.trim()) {
        throw new Error("Empty CSV");
    }

    const rows = [];
    let row = [];
    let field = "";
    let insideQuotes = false;

    for (let index = 0; index < content.length; index += 1) {
        const character = content[index];

        if (insideQuotes) {
            if (character === '"' && content[index + 1] === '"') {
                field += '"';
                index += 1;
            } else if (character === '"') {
                insideQuotes = false;
            } else {
                field += character;
            }
        } else if (character === '"' && field === "") {
            insideQuotes = true;
        } else if (character === ",") {
            row.push(field);
            field = "";
        } else if (character === "\n") {
            row.push(field.endsWith("\r") ? field.slice(0, -1) : field);
            rows.push(row);
            row = [];
            field = "";
        } else if (character === '"') {
            throw new Error("Unexpected quote");
        } else {
            field += character;
        }
    }

    if (insideQuotes) {
        throw new Error("Unclosed quoted field");
    }

    row.push(field.endsWith("\r") ? field.slice(0, -1) : field);
    if (row.some((value) => value !== "") || rows.length === 0) {
        rows.push(row);
    }

    return rows;
}

function getCsvDataRows(rows) {
    const nonEmptyRows = rows.filter(
        (row) => row.some((value) => value.trim() !== "")
    );
    const headers = nonEmptyRows[0] || [];
    const dataRows = nonEmptyRows.slice(1);

    if (headers.length === 0 || headers.some((header) => !header.trim())) {
        throw new Error("Invalid CSV header");
    }

    while (
        dataRows.length > 0
        && dataRows[dataRows.length - 1].length < headers.length
    ) {
        dataRows.pop();
    }

    if (dataRows.some((row) => row.length !== headers.length)) {
        throw new Error("Invalid CSV data row");
    }

    return { headers, dataRows };
}

function renderPortfolioFileSummary(container, rowCount, headers, source) {
    const summary = document.createElement("p");
    summary.textContent = `${rowCount} linhas · ${headers.length} colunas`;

    const columns = document.createElement("p");
    columns.textContent = `Cabeçalhos: ${headers.join(", ")}`;

    const identifiedSource = document.createElement("p");
    identifiedSource.textContent = source
        ? `Origem identificada: ${source}`
        : "Origem desconhecida.";

    container.append(summary, columns, identifiedSource);
}

function renderPortfolioFileError(container) {
    const error = document.createElement("p");
    error.className = "file-picker-error";
    error.textContent = "Não foi possível ler um CSV válido.";
    container.appendChild(error);
}

function formatUpdatedAt(value) {
    if (!value) {
        return "Não disponível";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Não disponível";
    }

    return new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    }).format(date);
}

function createExecutiveCard(item, index) {
    const article = document.createElement("article");
    article.className = "executive-card";

    const number = document.createElement("span");
    number.className = "card-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const area = document.createElement("p");
    area.className = "card-area";
    area.textContent = item.area;

    const title = document.createElement("h3");
    title.textContent = item.title;

    const summary = document.createElement("p");
    summary.className = "card-summary";
    summary.textContent = item.summary;

    const footer = document.createElement("div");
    footer.className = "card-footer";

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status;

    const action = document.createElement("span");
    action.className = "analysis-link";
    action.textContent = "Análise completa em preparação";

    footer.append(status, action);
    article.append(number, area, title, summary, footer);

    return article;
}

function createModuleCard(item) {
    const article = document.createElement("article");
    article.className = "module-card";
    article.id = item.id;

    const header = document.createElement("div");
    header.className = "module-header";

    const title = document.createElement("h3");
    title.textContent = item.title;

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status;

    const description = document.createElement("p");
    description.textContent = item.description;

    header.append(title, status);
    article.append(header, description);

    return article;
}

function createOverviewCard(item) {
    const article = document.createElement("article");
    article.className = "overview-card";

    const title = document.createElement("h3");
    title.textContent = item.title || "";

    const summary = document.createElement("p");
    summary.className = "overview-description";
    summary.textContent = item.summary || "";

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status || "";

    article.append(title, summary, status);

    return article;
}

function renderCockpit(data) {
    const globalOverview = document.getElementById("globalOverview");
    const executiveCards = document.getElementById("executiveCards");
    const moduleCards = document.getElementById("moduleCards");
    const executiveCount = document.getElementById("executiveCount");
    const lastUpdate = document.getElementById("lastUpdate");

    globalOverview.innerHTML = "";
    executiveCards.innerHTML = "";
    moduleCards.innerHTML = "";

    const overviewItems = Array.isArray(data.global_overview)
        ? data.global_overview
        : data.global_overview
            ? [data.global_overview]
            : [];

    const executiveItems = Array.isArray(data.executive)
        ? data.executive
        : [];

    const moduleItems = Array.isArray(data.sections)
        ? data.sections
        : [];

    overviewItems.forEach((item) => {
        globalOverview.appendChild(createOverviewCard(item));
    });

    executiveItems.forEach((item, index) => {
        executiveCards.appendChild(createExecutiveCard(item, index));
    });

    moduleItems.forEach((item) => {
        moduleCards.appendChild(createModuleCard(item));
    });

    executiveCount.textContent = `${executiveItems.length} conclusões`;
    lastUpdate.textContent = formatUpdatedAt(data.updated_at);
}

function renderError(message) {
    const executiveCards = document.getElementById("executiveCards");
    const moduleCards = document.getElementById("moduleCards");
    const lastUpdate = document.getElementById("lastUpdate");

    executiveCards.innerHTML = `<p class="error-message">${message}</p>`;
    moduleCards.innerHTML = "";
    lastUpdate.textContent = "Falha no carregamento";
}

async function loadCockpit() {
    try {
        const response = await fetch("/api/cockpit", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(`Erro HTTP ${response.status}`);
        }

        const payload = await response.json();

        if (!payload.ok || !payload.cockpit) {
            throw new Error(payload.error || "Resposta inválida do servidor.");
        }

        renderCockpit(payload.cockpit);
    } catch (error) {
        console.error(error);
        renderError("Não foi possível carregar o Cockpit Executivo.");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    setGreeting();
    setupPortfolioFilePicker();
    loadCockpit();
});
