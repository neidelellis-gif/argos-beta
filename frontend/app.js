"use strict";

const STATUS_LABELS = {
    waiting: "Aguardando",
    completed: "Concluído",
    unavailable: "Indisponível",
    pendente: "Pendente",
    em_construcao: "Em construção",
    pronto: "Pronto"
};

const FILE_SOURCE_IDENTIFIERS = [
    {
        source: "Exportação de posições UBS",
        matches({ headers }) {
            const normalizedHeaders = new Set(headers.map(normalizeCsvHeader));
            const ubsHeaders = [
                "description",
                "symbol",
                "cusip",
                "quantity",
                "price",
                "value"
            ];
            const hasPortfolioPercentage = [
                "percent of portfolio",
                "% of portfolio"
            ].some((header) => normalizedHeaders.has(header));

            return ubsHeaders.every((header) => normalizedHeaders.has(header))
                && hasPortfolioPercentage;
        }
    },
    {
        source: "Exportação de carteira TipRanks",
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
    ["Instituição", "institution"],
    ["Código", "ticker"],
    ["Nome", "name"],
    ["Quantidade", "shares"],
    ["Preço", "price"],
    ["Valor da posição", "holdingValue"],
    ["Nota", "smartScore"],
    ["Consenso dos analistas", "analystConsensus"],
    ["Preço-alvo dos analistas", "analystPriceTarget"],
    ["Variação até o preço-alvo", "analystPriceTargetPercent"]
];

let importedPortfolioPositions = [];
let canonicalPortfolioPositions = [];
let dashboardValuesVisible = false;
let dailyExperienceLoading = false;

function storeCanonicalPortfolioPositions(positions) {
    canonicalPortfolioPositions = positions.map((position) => ({ ...position }));
}

function getCanonicalPortfolioPositions() {
    return canonicalPortfolioPositions.map((position) => ({ ...position }));
}

function identifySantanderExcelSource(fileName) {
    return /^your-positions-\d+-\d+\.xlsx$/i.test(fileName)
        ? "Exportação de posições Santander"
        : null;
}

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

function setupPortfolioFilePicker() {
    const fileInput = document.getElementById("portfolioFile");
    const fileName = document.getElementById("portfolioFileName");
    const fileSummary = document.getElementById("portfolioFileSummary");
    const previewSection = document.getElementById("tipRanksPreview");
    const previewContent = document.getElementById("tipRanksPreviewContent");
    const importButton = document.getElementById("importPortfolios");
    const progress = document.getElementById("importProgress");
    const progressBar = document.getElementById("importProgressBar");
    const progressText = document.getElementById("importProgressText");
    const clearButton = document.getElementById("clearPortfolios");

    fileInput.addEventListener("change", async () => {
        const selectedFile = fileInput.files[0];
        const selectedFiles = Array.from(fileInput.files || []);
        fileName.textContent = selectedFiles.length
            ? selectedFiles.map((file) => file.name).join(", ")
            : "Nenhum arquivo selecionado";
        if (importButton) {
            importButton.disabled = selectedFiles.length === 0;
        }
        fileSummary.replaceChildren();
        hideTipRanksPreview(previewSection, previewContent);

        if (!selectedFile) {
            return;
        }

        const santanderSource = identifySantanderExcelSource(selectedFile.name);

        if (santanderSource) {
            renderIdentifiedFileSource(fileSummary, santanderSource);
            try {
                const response = await fetch("/api/santander/inspect", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        file: {
                            name: selectedFile.name,
                            content: await readFileAsBase64(selectedFile)
                        }
                    })
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Arquivo Santander inválido.");
                }
                renderSantanderPositionCount(
                    fileSummary,
                    result.position_count
                );
            } catch (error) {
                renderSantanderExcelError(fileSummary);
            }
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

            if (source === "Exportação de carteira TipRanks") {
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

    if (importButton) {
        importButton.addEventListener("click", async () => {
            const files = Array.from(fileInput.files || []);
            const formData = new FormData();
            files.forEach((file) => formData.append("files", file, file.name));
            importButton.disabled = true;
            progress.hidden = false;
            progressBar.value = 25;
            progressText.textContent = "Enviando arquivos...";
            try {
                const response = await fetch("/api/portfolios/import", {
                    method: "POST",
                    body: formData
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Falha na importação.");
                }
                progressBar.value = 100;
                progressText.textContent = "Importação concluída.";
                storeCanonicalPortfolioPositions(result.positions);
                renderDashboard(result.dashboard);
            } catch (error) {
                progressBar.value = 0;
                progressText.textContent = error.message;
            } finally {
                importButton.disabled = files.length === 0;
            }
        });
    }


    if (clearButton) {
        clearButton.addEventListener("click", async () => {
            clearButton.disabled = true;
            progress.hidden = false;
            progressBar.value = 25;
            progressText.textContent = "Limpando carteiras...";
            try {
                const response = await fetch("/api/portfolios", {
                    method: "DELETE"
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error("Não foi possível limpar as carteiras.");
                }
                fileInput.value = "";
                fileName.textContent = "Nenhum arquivo selecionado";
                fileSummary.replaceChildren();
                hideTipRanksPreview(previewSection, previewContent);
                importButton.disabled = true;
                progressBar.value = 100;
                progressText.textContent = "Todas as carteiras foram removidas.";
                storeCanonicalPortfolioPositions(result.positions);
                renderDashboard(result.dashboard);
            } catch (error) {
                console.error(error);
                progressBar.value = 0;
                progressText.textContent = "Não foi possível limpar as carteiras.";
            } finally {
                clearButton.disabled = false;
            }
        });
    }
}

function readFileAsBase64(file) {
    return file.arrayBuffer().then((buffer) => {
        let binary = "";
        new Uint8Array(buffer).forEach((byte) => {
            binary += String.fromCharCode(byte);
        });
        return btoa(binary);
    });
}

function renderSantanderPositionCount(container, positionCount) {
    const count = document.createElement("p");
    count.textContent = `Quantidade de posições encontradas: ${positionCount}`;
    container.append(count);
}

function renderSantanderExcelError(container) {
    const error = document.createElement("p");
    error.className = "file-picker-error";
    error.textContent = "Não foi possível ler o Excel do Santander.";
    container.appendChild(error);
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
    const structuralHeaderIndex = nonEmptyRows.findIndex(
        (row, index) => row.length > 1
            && nonEmptyRows[index + 1]?.length === row.length
    );
    const firstMultiColumnIndex = nonEmptyRows.findIndex(
        (row) => row.length > 1
    );
    const headerIndex = structuralHeaderIndex >= 0
        ? structuralHeaderIndex
        : Math.max(firstMultiColumnIndex, 0);
    const headers = nonEmptyRows[headerIndex] || [];
    const dataRows = nonEmptyRows.slice(headerIndex + 1);

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
    summary.textContent = `${formatCount(rowCount, "linha")} · ${formatCount(
        headers.length,
        "coluna"
    )}`;

    const columns = document.createElement("p");
    columns.textContent = `Cabeçalhos: ${headers.join(", ")}`;

    container.append(summary, columns);
    renderIdentifiedFileSource(container, source);
}

function renderIdentifiedFileSource(container, source) {
    const identifiedSource = document.createElement("p");
    identifiedSource.textContent = source
        ? `Origem identificada: ${source}`
        : "Origem desconhecida.";
    container.append(identifiedSource);
}

function renderPortfolioFileError(container) {
    const error = document.createElement("p");
    error.className = "file-picker-error";
    error.textContent = "Não foi possível ler um CSV válido.";
    container.appendChild(error);
}

function formatUpdatedAt(value) {
    if (!value) {
        return "Nenhuma importação realizada";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Nenhuma importação realizada";
    }

    return new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    }).format(date);
}

function formatCount(value, singular, plural = `${singular}s`) {
    return `${value} ${Number(value) === 1 ? singular : plural}`;
}

function translateWarning(warning) {
    return warning
        .replace(
            /(\d+) duplicated asset\(s\)/gi,
            (_message, count) => formatCount(count, "ativo duplicado", "ativos duplicados")
        )
        .replace(
            /(\d+) position\(s\) without symbol/gi,
            (_message, count) => `${formatCount(count, "posição", "posições")} sem ticker identificado`
        );
}

function formatDashboardDate(value) {
    const date = new Date(`${value}T12:00:00`);
    return new Intl.DateTimeFormat("pt-BR", {
        day: "numeric",
        month: "long",
        year: "numeric"
    }).format(date);
}

function formatCurrency(value, currency) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return "Valor não informado";
    }
    const locale = currency === "BRL" ? "pt-BR" : "en-US";
    const symbols = { USD: "US$", EUR: "€", BRL: "R$" };
    const formattedNumber = new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(Math.abs(number));
    const sign = number < 0 ? "-" : "";
    return `${sign}${symbols[currency] || currency} ${formattedNumber}`;
}

function formatQuantity(value) {
    return new Intl.NumberFormat("pt-BR", {
        maximumFractionDigits: 8
    }).format(Number(value));
}

function formatPercentage(value) {
    return `${new Intl.NumberFormat("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(Number(value))}%`;
}

function createMetric(label, value, sensitive = false) {
    const paragraph = document.createElement("p");
    const title = document.createElement("strong");
    const content = document.createElement("span");
    title.textContent = `${label}: `;
    content.textContent = String(value);
    if (sensitive) {
        content.className = "financial-value";
        content.dataset.value = String(value);
        if (!dashboardValuesVisible) {
            content.textContent = "••••";
        }
    }
    paragraph.append(title, content);
    return paragraph;
}

function appendTotals(container, totals) {
    const entries = Object.entries(totals || {});
    if (entries.length === 0) {
        container.append(createMetric("Totais por moeda", "Nenhum total informado"));
        return;
    }
    entries.forEach(([currency, total]) => {
        container.append(createMetric(
            `Total ${currency}`,
            formatCurrency(total, currency),
            true
        ));
    });
}

function appendWarnings(container, warnings) {
    container.append(createMetric(
        "Avisos",
        warnings.length ? warnings.map(translateWarning).join(" · ") : "Nenhum"
    ));
}

function createTextElement(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text || "";
    return element;
}

function createEmptyState(message) {
    return createTextElement("p", "daily-empty", message);
}

function createDailyItem({ title, eyebrow, summary, metadata }) {
    const article = document.createElement("article");
    article.className = "daily-item";
    const header = document.createElement("div");
    header.className = "daily-item-header";
    header.append(createTextElement("span", "daily-item-eyebrow", eyebrow));
    article.append(
        header,
        createTextElement("h3", "", title),
        createTextElement("p", "daily-item-summary", summary)
    );
    if (metadata) {
        article.append(createTextElement("p", "daily-item-meta", metadata));
    }
    return article;
}

function renderHeader(header, generatedAt) {
    document.getElementById("greeting").textContent = header.greeting;
    document.getElementById("currentDate").textContent = header.display_date;
    document.getElementById("lastUpdateLabel").textContent = "Experiência gerada em";
    document.getElementById("lastUpdate").textContent = generatedAt;
}

function renderMessage(message) {
    document.getElementById("dailyMessageTitle").textContent = message.title;
    document.getElementById("dailyWindow").textContent = message.text;
}

function renderFacts(facts) {
    const container = document.getElementById("importantFacts");
    container.replaceChildren();
    facts.forEach((fact) => container.append(
        createDailyItem({
            title: fact.text,
            eyebrow: fact.category,
            summary: fact.importance
        })
    ));
}

function renderPriorities(priorities) {
    const container = document.getElementById("dailyPriorities");
    container.replaceChildren();
    priorities.forEach((item) => container.append(
        createDailyItem({
            title: item.title,
            eyebrow: item.label,
            summary: item.reason
        })
    ));
}

function renderAnalyses(analyses) {
    const container = document.getElementById("dailyAnalyses");
    container.replaceChildren();
    analyses.forEach((item) => container.append(
        createDailyItem({
            title: item.title,
            eyebrow: item.action,
            summary: item.reason
        })
    ));
}

function renderBlocks(blocks) {
    const panels = [
        document.getElementById("importantFacts").closest("article"),
        document.getElementById("dailyPriorities").closest("article"),
        document.getElementById("dailyAnalyses").closest("article")
    ];
    blocks.forEach((block, index) => {
        panels[index].hidden = !block.visible;
        panels[index].querySelector("h2").textContent = block.title;
    });
}

function renderSummary(summary) {
    const container = document.getElementById("dailySummary");
    container.replaceChildren(
        createMetric("Fatos", summary.fact_count),
        createMetric("Prioridades", summary.priority_count),
        createMetric("Análises", summary.analysis_count),
        createMetric("Blocos visíveis", summary.visible_block_count)
    );
    document.getElementById("summaryStatus").textContent =
        `${summary.visible_block_count} blocos visíveis`;
}

function renderDailyExperience(response) {
    renderHeader(response.header, response.generated_at);
    renderMessage(response.message);
    renderFacts(response.facts);
    renderPriorities(response.priorities);
    renderAnalyses(response.analyses);
    renderBlocks(response.blocks);
    renderSummary(response.summary);
    document.getElementById("factsCount").textContent = response.summary.fact_count;
    document.getElementById("prioritiesCount").textContent = response.summary.priority_count;
    document.getElementById("analysesCount").textContent = response.summary.analysis_count;
}

function setDailyLoading(loading) {
    dailyExperienceLoading = loading;
    const container = document.getElementById("dailySummary");
    if (loading) {
        container.replaceChildren(createTextElement(
            "p", "loading-message", "Carregando experiência diária..."
        ));
    }
}

function renderDailyError(message) {
    document.getElementById("dailySummary").replaceChildren(
        createTextElement("p", "error-message", message)
    );
}

async function loadDailyExperience(client = new DailyFrontendClient()) {
    if (dailyExperienceLoading) {
        return;
    }
    setDailyLoading(true);
    try {
        if (typeof DailyRequestBuilder === "undefined") {
            await import("./daily_request_builder.js");
        }
        const response = await client.loadExperience({
            positions: DailyRequestBuilder.build(canonicalPortfolioPositions),
            fact_candidates: [],
            reference_date: null
        });
        renderDailyExperience(response);
    } catch (error) {
        renderDailyError(error.message);
    } finally {
        setDailyLoading(false);
    }
}

function renderDashboard(data) {
    const institutions = document.getElementById("institutions");
    const consolidated = document.getElementById("consolidated");
    const executiveCards = document.getElementById("executiveCards");
    const moduleCards = document.getElementById("moduleCards");
    institutions.replaceChildren();
    consolidated.replaceChildren();
    executiveCards.replaceChildren();
    moduleCards.replaceChildren();

    document.getElementById("dashboardVersion").textContent =
        `Versão ${data.header.version}`;
    document.getElementById("situationLabel").textContent =
        data.labels.daily_situation;
    document.getElementById("situationTitle").textContent =
        data.labels.daily_situation_title;
    document.getElementById("modulesLabel").textContent = data.labels.modules;
    document.getElementById("modulesTitle").textContent =
        data.labels.modules_title;

    if (data.institutions.length === 0) {
        institutions.append(createMetric(
            "Instituições",
            "Nenhuma posição disponível"
        ));
    }
    data.institutions.forEach((institution) => {
        const card = document.createElement("article");
        card.className = "institution-card";
        const title = document.createElement("h3");
        title.textContent = institution.name;
        card.append(
            title,
            createMetric("Posições", institution.position_count),
            createMetric(
                "Moedas",
                institution.currencies.join(", ") || "Nenhuma"
            )
        );
        appendTotals(card, institution.totals_by_currency);
        appendWarnings(card, institution.warnings);
        institutions.append(card);
    });

    consolidated.append(
        createMetric("Instituições", data.consolidated.institution_count),
        createMetric("Posições", data.consolidated.position_count),
        createMetric("Ativos únicos", data.consolidated.unique_asset_count),
        createMetric("Ativos repetidos", data.consolidated.repeated_asset_count)
    );
    appendTotals(consolidated, data.consolidated.totals_by_currency);
    appendWarnings(consolidated, data.consolidated.warnings);

    data.daily_situation.forEach((item, index) => {
        executiveCards.appendChild(createExecutiveCard(item, index));
    });
    document.getElementById("executiveCount").textContent =
        formatCount(data.daily_situation.length, "item", "itens");

    data.modules.forEach((module) => {
        moduleCards.appendChild(createModuleCard(module));
    });
}

function toggleDashboardValues() {
    dashboardValuesVisible = !dashboardValuesVisible;
    document.querySelectorAll(".financial-value").forEach((element) => {
        element.textContent = dashboardValuesVisible
            ? element.dataset.value
            : "••••";
    });
    document.getElementById("toggleValues").textContent =
        dashboardValuesVisible ? "Ocultar valores" : "Mostrar valores";
}

async function loadDashboard() {
    try {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`Erro HTTP ${response.status}`);
        }
        const result = await response.json();
        storeCanonicalPortfolioPositions(result.positions);
        renderDashboard(result);
    } catch (error) {
        console.error(error);
        document.getElementById("institutions").replaceChildren(
            createTextElement(
                "p", "error-message", "Não foi possível carregar o dashboard."
            )
        );
    }
}

function createExecutiveCard(item, index) {
    const article = document.createElement("article");
    article.className = "executive-card";

    const number = document.createElement("span");
    number.className = "card-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const title = document.createElement("h3");
    title.textContent = item.message;

    const footer = document.createElement("div");
    footer.className = "card-footer";

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status;

    footer.append(status);
    article.append(number, title, footer);

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
    description.textContent = item.message;

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

document.addEventListener("DOMContentLoaded", () => {
    setupPortfolioFilePicker();
    document.getElementById("toggleValues").addEventListener(
        "click",
        toggleDashboardValues
    );
    loadDailyExperience();
    loadDashboard();
});
