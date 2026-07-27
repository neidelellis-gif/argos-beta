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
            const hasAssetIdentifier = ["ticker", "symbol"].some(
                (header) => normalizedHeaders.has(header)
            );
            const hasPortfolioData = ["shares", "quantity", "market value"].some(
                (header) => normalizedHeaders.has(header)
            );
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

    fileInput.addEventListener("change", async () => {
        const selectedFile = fileInput.files[0];
        fileName.textContent = selectedFile
            ? selectedFile.name
            : "Nenhum arquivo selecionado";
        fileSummary.replaceChildren();

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
