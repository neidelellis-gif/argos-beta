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
const IMPORT_STATUS_KEY = "argos.institution-import-status";
const PORTFOLIO_IMPORT_SESSION_KEY = "argos.portfolio-import-confirmed";

function normalizeInstitutionKey(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toLowerCase();
}

function readInstitutionImportStatus() {
    try {
        if (typeof window === "undefined" || !window.localStorage) return {};
        return JSON.parse(window.localStorage.getItem(IMPORT_STATUS_KEY) || "{}");
    } catch (_) {
        return {};
    }
}

function writeInstitutionImportStatus(status) {
    if (typeof window === "undefined" || !window.localStorage) return;
    window.localStorage.setItem(IMPORT_STATUS_KEY, JSON.stringify(status));
}

function setInstitutionImportError(institutionNames, message, reason = "import_failed") {
    const names = Array.from(new Set((institutionNames || []).map(normalizeInstitutionKey).filter(Boolean)));
    if (!names.length) return;
    const status = readInstitutionImportStatus();
    const now = new Date().toISOString();
    names.forEach((name) => {
        status[name] = { status: "error", reason, message, updated_at: now };
    });
    writeInstitutionImportStatus(status);
}

function clearInstitutionImportError(institutionNames) {
    const names = Array.from(new Set((institutionNames || []).map(normalizeInstitutionKey).filter(Boolean)));
    if (!names.length) return;
    const status = readInstitutionImportStatus();
    names.forEach((name) => {
        delete status[name];
    });
    writeInstitutionImportStatus(status);
}

function inferInstitutionFromFile(fileName, source = null) {
    if (identifySantanderExcelSource(fileName)) return "Santander";
    const normalized = normalizeInstitutionKey(`${fileName} ${source || ""}`);
    if (normalized.includes("santander")) return "Santander";
    if (normalized.includes("ubs")) return "UBS";
    return null;
}

function inferInstitutionsFromFiles(files) {
    return Array.from(new Set((files || [])
        .map((file) => inferInstitutionFromFile(file.name))
        .filter(Boolean)));
}

function activateNotebookTab(tabName, navigationItems, panels) {
    navigationItems.forEach((item) => {
        const isActive = item.dataset.tab === tabName;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-selected", String(isActive));
    });
    panels.forEach((panel) => {
        const isActive = panel.dataset.tabPanel === tabName;
        panel.classList.toggle("active", isActive);
        panel.hidden = !isActive;
    });
}

function setupNotebookNavigation(root = document) {
    const navigationItems = Array.from(root.querySelectorAll("[data-tab]"));
    const panels = Array.from(root.querySelectorAll("[data-tab-panel]"));

    navigationItems.forEach((item) => {
        item.addEventListener("click", () => {
            activateNotebookTab(item.dataset.tab, navigationItems, panels);
        });
    });
    activateNotebookTab("daily", navigationItems, panels);
}

function storeCanonicalPortfolioPositions(positions) {
    canonicalPortfolioPositions = (positions || []).map((position) => ({ ...position }));
}

function markPortfolioImportConfirmed() {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    window.sessionStorage.setItem(PORTFOLIO_IMPORT_SESSION_KEY, "true");
}

function clearPortfolioImportConfirmation() {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    window.sessionStorage.removeItem(PORTFOLIO_IMPORT_SESSION_KEY);
}

function hasPortfolioImportConfirmation() {
    if (typeof window === "undefined" || !window.sessionStorage) return false;
    return window.sessionStorage.getItem(PORTFOLIO_IMPORT_SESSION_KEY) === "true";
}

function shouldHydratePortfolioDashboard(data) {
    return hasPortfolioImportConfirmation()
        && data?.session?.status === "active"
        && Array.isArray(data.positions)
        && data.positions.length > 0;
}

function emptyPortfolioDashboard(data) {
    return {
        ...data,
        positions: [],
        institutions: [],
        consolidated: {
            institution_count: 0,
            position_count: 0,
            unique_asset_count: 0,
            repeated_asset_count: 0,
            totals_by_currency: {},
            warnings: []
        },
        session: {
            ...(data.session || {}),
            last_import_at: null,
            institution_count: 0,
            position_count: 0,
            analyzed_institutions: [],
            status: "waiting_import"
        }
    };
}

function getCanonicalPortfolioPositions() {
    return canonicalPortfolioPositions.map((position) => ({ ...position }));
}

function identifySantanderExcelSource(fileName) {
    return /^your-positions-.*\.xlsx$/i.test(fileName)
        ? "Exportação de posições Santander"
        : null;
}

function hasSantanderPositions(positions) {
    return (positions || []).some(
        (position) => normalizeInstitutionKey(position.institution) === "santander"
    );
}

function countSantanderPositions(positions) {
    return (positions || []).filter(
        (position) => normalizeInstitutionKey(position.institution) === "santander"
    ).length;
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
        const selectedFiles = Array.from(fileInput.files || []);
        fileName.textContent = selectedFiles.length
            ? selectedFiles.map((file) => file.name).join(", ")
            : "Nenhum arquivo selecionado";
        if (importButton) {
            importButton.disabled = selectedFiles.length === 0;
        }
        fileSummary.replaceChildren();
        hideTipRanksPreview(previewSection, previewContent);

        if (!selectedFiles.length) {
            return;
        }

        const santanderFiles = selectedFiles.filter(
            (file) => identifySantanderExcelSource(file.name)
        );

        if (santanderFiles.length) {
            renderIdentifiedFileSource(
                fileSummary,
                "Exportação de posições Santander"
            );
            try {
                let positionCount = 0;
                for (const file of santanderFiles) {
                    const response = await fetch("/api/santander/inspect", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            file: {
                                name: file.name,
                                content: await readFileAsBase64(file)
                            }
                        })
                    });
                    const result = await response.json();
                    if (!response.ok || !result.ok || !result.position_count) {
                        throw new Error(result.error || "Arquivo Santander inválido.");
                    }
                    positionCount += result.position_count;
                }
                renderSantanderPositionCount(fileSummary, positionCount);
            } catch (error) {
                setInstitutionImportError(["Santander"], "A carteira ainda não foi importada corretamente.", "import_failed");
                renderSantanderExcelError(fileSummary);
            }
            return;
        }

        const selectedFile = selectedFiles[0];

        if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
            setInstitutionImportError(
                [inferInstitutionFromFile(selectedFile.name)].filter(Boolean),
                "Arquivo não reconhecido para importação da carteira.",
                "unrecognized_file"
            );
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

            const institutionName = inferInstitutionFromFile(selectedFile.name, source);
            if (!source) {
                setInstitutionImportError(
                    [institutionName].filter(Boolean),
                    "Arquivo não reconhecido para importação da carteira.",
                    "unrecognized_file"
                );
            }
            renderPortfolioFileSummary(
                fileSummary,
                dataRows.length,
                headers,
                source
            );
        } catch (error) {
            setInstitutionImportError(
                [inferInstitutionFromFile(selectedFile.name)].filter(Boolean),
                "A carteira ainda não foi importada corretamente.",
                "import_failed"
            );
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
            let result = null;
            try {
                const response = await fetch("/api/portfolios/import", {
                    method: "POST",
                    body: formData
                });
                result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Falha na importação.");
                }
                progressBar.value = 100;
                progressText.textContent = "Importação concluída.";
                const importedPositions = result.positions || [];
                const importedInstitutionNames = Array.isArray(result.dashboard?.institutions)
                    ? result.dashboard.institutions.map((institution) => institution.name)
                    : inferInstitutionsFromFiles(files);
                const includesSantanderFile = files.some((file) => identifySantanderExcelSource(file.name));
                if (includesSantanderFile && !hasSantanderPositions(importedPositions)) {
                    throw new Error("Não foi possível ler o Excel do Santander");
                }
                clearInstitutionImportError(
                    importedInstitutionNames.filter(
                        (institution) => normalizeInstitutionKey(institution) !== "santander"
                            || hasSantanderPositions(importedPositions)
                    )
                );
                markPortfolioImportConfirmed();
                storeCanonicalPortfolioPositions(importedPositions);
                renderDashboard(result.dashboard);
                const santanderCount = countSantanderPositions(importedPositions);
                if (santanderCount) {
                    progressText.textContent = `Importação concluída. ${formatCount(santanderCount, "posição Santander carregada")}.`;
                }
            } catch (error) {
                setInstitutionImportError(
                    inferInstitutionsFromFiles(files),
                    error.message || "A carteira ainda não foi importada corretamente.",
                    "import_failed"
                );
                storeCanonicalPortfolioPositions(result?.positions || []);
                if (result?.dashboard) {
                    renderDashboard(result.dashboard);
                }
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
                clearPortfolioImportConfirmation();
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

function setDailyLoading(loading) {
    dailyExperienceLoading = loading;
    if (loading) {
        DailyExperienceRenderer.showLoading();
    }
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
            // The backend is the sole authority for the official portfolios.
            positions: [],
            fact_candidates: [],
            reference_date: null
        });
        DailyExperienceRenderer.render(response);
    } catch (error) {
        console.error("Daily experience failed", error);
        DailyExperienceRenderer.showError();
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
        const dashboard = shouldHydratePortfolioDashboard(result)
            ? result
            : emptyPortfolioDashboard(result);
        storeCanonicalPortfolioPositions(dashboard.positions);
        renderDashboard(dashboard);
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
    setupNotebookNavigation();
    setupPortfolioFilePicker();
    document.getElementById("toggleValues").addEventListener(
        "click",
        toggleDashboardValues
    );
    loadDailyExperience();
    loadDashboard();
});
