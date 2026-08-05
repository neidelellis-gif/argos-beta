"use strict";

const InstitutionAnalysis = (() => {
    const COMPLETED_KEY = "argos.completed-institutions";
    const IMPORT_STATUS_KEY = "argos.institution-import-status";
    let dashboard = null;
    let owner = null;
    let institutions = [];
    let currentIndex = 0;

    function $(id) {
        return document.getElementById(id);
    }

    function normalize(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim()
            .toLowerCase();
    }

    function params() {
        return new URLSearchParams(window.location.search);
    }

    function importStatusMap() {
        try {
            return JSON.parse(window.localStorage.getItem(IMPORT_STATUS_KEY) || "{}");
        } catch (_) {
            return {};
        }
    }

    function importStatusFor(institution) {
        const status = importStatusMap()[normalize(institution?.name)];
        return status && status.status !== "success" ? status : null;
    }

    function applyImportStatus(institution) {
        const status = importStatusFor(institution);
        return status ? { ...institution, import_status: status } : institution;
    }

    function completedMap() {
        try {
            return JSON.parse(window.localStorage.getItem(COMPLETED_KEY) || "{}");
        } catch (_) {
            return {};
        }
    }

    function isCompleted(name) {
        const map = completedMap();
        return Boolean(map[owner.id]?.includes(normalize(name)));
    }

    function markCompleted(name) {
        const map = completedMap();
        const list = new Set(Array.isArray(map[owner.id]) ? map[owner.id] : []);
        list.add(normalize(name));
        map[owner.id] = Array.from(list);
        window.localStorage.setItem(COMPLETED_KEY, JSON.stringify(map));
    }

    function formatCurrency(value, currency) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "—";
        const locale = currency === "BRL" ? "pt-BR" : "en-US";
        const symbol = { BRL: "R$", USD: "US$", EUR: "€" }[currency] || currency;
        return `${symbol} ${new Intl.NumberFormat(locale, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(number)}`;
    }

    function institutionValue(institution) {
        const totals = Object.entries(institution?.totals_by_currency || {});
        if (!totals.length) return "Valor não informado";
        return totals.map(([currency, value]) => formatCurrency(value, currency)).join(" · ");
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function listItem(title, description) {
        const row = element("div", "institution-list-item");
        const marker = element("span", "institution-list-marker");
        const body = element("div");
        body.append(element("strong", "", title));
        if (description) body.append(element("p", "", description));
        row.append(marker, body);
        return row;
    }

    function renderList(containerId, items, fallback) {
        const container = $(containerId);
        container.replaceChildren();
        if (!items.length) {
            container.append(element("p", "institution-empty", fallback));
            return;
        }
        items.forEach((item) => container.append(listItem(item.title, item.description)));
    }

    function selectedInstitution() {
        return institutions[currentIndex] || null;
    }

    function warningTexts(institution) {
        return Array.isArray(institution.warnings) ? institution.warnings.map(String) : [];
    }

    function isImportIncomplete(institution) {
        const positions = Number(institution?.position_count || 0);
        const totals = Object.entries(institution?.totals_by_currency || {});
        const warnings = warningTexts(institution || {}).map(normalize);
        return Boolean(institution?.import_status)
            || positions <= 0
            || !totals.length
            || warnings.some((warning) => (
                warning.includes("ainda nao carregada")
                || warning.includes("incomplet")
                || warning.includes("insuficient")
            ));
    }

    function buildSummary(institution) {
        const positions = Number(institution.position_count || 0);
        const currencies = Array.isArray(institution.currencies) ? institution.currencies : [];
        const warnings = warningTexts(institution);
        if (isImportIncomplete(institution)) {
            return `Dados insuficientes. A carteira de ${institution.name} ainda não foi importada corretamente. Complete uma nova importação válida antes de avaliar riscos, oportunidades ou consolidação.`;
        }
        if (warnings.length) {
            return `${institution.name} tem ${positions} posições carregadas. Antes de decidir, revise os pontos de atenção da importação e confirme se a base representa a carteira atual.`;
        }
        const currencyText = currencies.length ? `, com exposição em ${currencies.join(" e ")}` : "";
        return `${institution.name} tem ${positions} posições carregadas${currencyText}. A base está suficiente para uma leitura executiva inicial, ainda sem substituir a validação individual dos ativos.`;
    }

    function attentionItems(institution) {
        const items = [];
        const warnings = warningTexts(institution);
        if (isImportIncomplete(institution)) {
            return [{
                title: "Dados insuficientes",
                description: "A carteira ainda não foi importada corretamente. O ARGOS não vai usar dados anteriores como base atual nem concluir a análise desta instituição."
            }];
        }
        warnings.slice(0, 4).forEach((warning) => {
            items.push({ title: "Ponto informado pela instituição", description: String(warning) });
        });
        if (Number(institution.position_count || 0) > 25) {
            items.push({
                title: "Quantidade elevada de posições",
                description: "A carteira possui muitos ativos. Vale verificar se todos continuam cumprindo uma função clara."
            });
        }
        const currencies = Array.isArray(institution.currencies) ? institution.currencies : [];
        if (currencies.length > 1) {
            items.push({
                title: "Exposição em mais de uma moeda",
                description: `A carteira está distribuída entre ${currencies.join(" e ")}. O efeito cambial precisa ser considerado.`
            });
        }
        if (!items.length) {
            items.push({
                title: "Nenhum alerta operacional imediato",
                description: "A análise detalhada dos ativos ainda é necessária antes de concluir o diagnóstico desta instituição."
            });
        }
        return items.slice(0, 5);
    }

    function riskItems(institution) {
        if (isImportIncomplete(institution)) {
            return [{
                title: "Dados insuficientes",
                description: "A carteira ainda não foi importada corretamente; por isso o ARGOS não emite conclusão sobre concentração, liquidez ou risco."
            }];
        }
        const risks = [];
        const positions = Number(institution.position_count || 0);
        if (positions === 1) {
            risks.push({ title: "Concentração elevada", description: "A posição está concentrada em apenas um ativo." });
        } else if (positions > 30) {
            risks.push({ title: "Carteira muito fragmentada", description: "Muitas posições podem dificultar o acompanhamento e diluir as melhores teses." });
        }
        const totals = Object.entries(institution.totals_by_currency || {});
        if (!totals.length) {
            risks.push({ title: "Valor patrimonial incompleto", description: "O arquivo não apresentou valores suficientes para medir pesos e concentrações." });
        }
        return risks;
    }

    function favorableItems(institution) {
        if (isImportIncomplete(institution)) {
            return [{
                title: "Dados insuficientes",
                description: "A carteira ainda não foi importada corretamente; por isso o ARGOS não confirma pontos favoráveis com base antiga."
            }];
        }
        const items = [];
        if (Number(institution.position_count || 0) > 1) {
            items.push({ title: "Mais de uma posição identificada", description: "Existe base para avaliar distribuição e concentração dentro da instituição." });
        }
        if (Array.isArray(institution.currencies) && institution.currencies.length) {
            items.push({ title: "Moeda identificada", description: `A carteira está registrada em ${institution.currencies.join(" e ")}.` });
        }
        if (!(institution.warnings || []).length) {
            items.push({ title: "Sem avisos de importação", description: "A leitura da carteira não apresentou inconsistências operacionais aparentes." });
        }
        return items;
    }

    function renderAllocation(institution) {
        const container = $("allocationList");
        container.replaceChildren();
        if (isImportIncomplete(institution)) {
            container.append(element("p", "institution-empty", "A distribuição será exibida somente após uma importação válida desta instituição."));
            return;
        }
        const totals = Object.entries(institution.totals_by_currency || {});
        const grandTotal = totals.reduce((sum, [, value]) => sum + Math.abs(Number(value || 0)), 0);
        if (!grandTotal) {
            container.append(element("p", "institution-empty", "A distribuição será exibida quando os valores da carteira estiverem disponíveis."));
            return;
        }
        totals.forEach(([currency, value]) => {
            const percentage = Math.abs(Number(value || 0)) / grandTotal * 100;
            const row = element("div", "institution-allocation-row");
            const label = element("span", "", currency);
            const track = element("div", "institution-allocation-track");
            const fill = element("div", "institution-allocation-fill");
            fill.style.width = `${Math.max(2, percentage)}%`;
            track.append(fill);
            const percent = element("span", "", `${percentage.toFixed(1)}%`);
            row.append(label, track, percent);
            container.append(row);
        });
    }

    function renderAssets(institution) {
        const container = $("assetList");
        container.replaceChildren();
        if (isImportIncomplete(institution)) {
            container.append(element("p", "institution-empty", "Os ativos aparecerão aqui após uma importação válida desta instituição."));
            return;
        }
        const positions = Number(institution.position_count || 0);
        const suggested = [];
        if (positions) suggested.push("Concentração", "Liquidez", "Custos", "Desempenho");
        if ((institution.currencies || []).length > 1) suggested.push("Câmbio");
        if (!suggested.length) {
            container.append(element("p", "institution-empty", "Os ativos aparecerão aqui após a leitura detalhada das posições."));
            return;
        }
        suggested.forEach((label) => {
            const button = element("button", "institution-asset", label);
            button.type = "button";
            button.addEventListener("click", () => {
                window.alert(`${label}: o detalhamento desta dimensão será conectado ao motor de análise nas próximas etapas da Sprint 3.`);
            });
            container.append(button);
        });
    }

    function renderNavigation() {
        const nav = $("institutionNav");
        nav.replaceChildren();
        institutions.forEach((institution, index) => {
            const button = element("button", "", institution.name);
            button.type = "button";
            button.classList.toggle("active", index === currentIndex);
            button.classList.toggle("done", isCompleted(institution.name) && index !== currentIndex);
            button.addEventListener("click", () => {
                currentIndex = index;
                render();
            });
            nav.append(button);
        });
        const completed = institutions.filter((institution) => isCompleted(institution.name)).length;
        $("progressLabel").textContent = `${completed} de ${institutions.length} análises concluídas`;
        $("progressBar").style.width = institutions.length ? `${completed / institutions.length * 100}%` : "0%";
    }

    function render() {
        const institution = applyImportStatus(selectedInstitution());
        if (!institution) return;
        const done = isCompleted(institution.name);

        $("ownerLabel").textContent = `Patrimônio de ${owner.name}`;
        $("institutionName").textContent = institution.name;
        $("institutionMeta").textContent = `${owner.name} · análise individual · ${new Intl.DateTimeFormat("pt-BR").format(new Date())}`;
        $("executiveSummary").textContent = buildSummary(institution);
        const incomplete = isImportIncomplete(institution);
        $("metricValue").textContent = incomplete ? "Não disponível" : institutionValue(institution);
        $("metricPositions").textContent = incomplete ? "—" : String(institution.position_count || 0);
        $("metricCurrencies").textContent = incomplete ? "—" : (institution.currencies || []).join(" · ") || "—";
        $("metricSituation").textContent = incomplete ? "Dados insuficientes" : (institution.warnings || []).length ? "Atenção" : "Regular";
        $("attentionCount").textContent = `${attentionItems(institution).length} pontos`;

        const status = $("institutionStatus");
        status.textContent = done ? "Concluída" : "Em análise";
        status.classList.toggle("done", done);
        $("completeInstitution").textContent = incomplete ? "Complete a importação para concluir" : done ? "Ir para a próxima instituição →" : "Concluir análise desta instituição →";
        $("completeInstitution").disabled = incomplete;

        renderList("attentionList", attentionItems(institution), "Nenhum ponto de atenção foi identificado.");
        renderList("riskList", riskItems(institution), "Nenhum risco específico foi identificado com os dados disponíveis.");
        renderList("favorableList", favorableItems(institution), "Nenhum ponto favorável específico foi confirmado ainda.");
        renderAllocation(institution);
        renderAssets(institution);
        renderNavigation();
        $("previousInstitution").disabled = currentIndex === 0;
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function goToIndex(index) {
        if (index < 0 || index >= institutions.length) return;
        currentIndex = index;
        const institution = institutions[currentIndex];
        const query = new URLSearchParams({ owner: owner.id, institution: institution.name });
        window.history.replaceState({}, "", `/institution_analysis.html?${query.toString()}`);
        render();
    }

    function bindActions() {
        $("previousInstitution").addEventListener("click", () => goToIndex(currentIndex - 1));
        $("completeInstitution").addEventListener("click", () => {
            const institution = selectedInstitution();
            if (isImportIncomplete(institution)) return;
            if (!isCompleted(institution.name)) markCompleted(institution.name);
            if (currentIndex < institutions.length - 1) {
                goToIndex(currentIndex + 1);
                return;
            }
            render();
            window.alert(`Todas as instituições de ${owner.name} foram analisadas. A consolidação será oferecida na Sprint 4.`);
        });
    }

    async function load() {
        const ownerId = params().get("owner");
        const requestedInstitution = params().get("institution");
        const owners = ArgosAnalysisContext.getOwners();
        owner = owners.find((item) => item.id === ownerId) || ArgosAnalysisContext.getActiveOwner();
        ArgosAnalysisContext.setActiveOwner(owner.id);

        try {
            const response = await fetch("/api/dashboard", { cache: "no-store" });
            if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
            dashboard = await response.json();
        } catch (error) {
            console.error("Institution dashboard load failed", error);
            dashboard = { institutions: [] };
        }

        const allowed = new Set(owner.institutions.map(normalize));
        institutions = Array.isArray(dashboard.institutions)
            ? dashboard.institutions.filter((item) => allowed.has(normalize(item.name)))
            : [];

        if (!institutions.length) {
            institutions = owner.institutions.map((name) => ({
                name,
                position_count: 0,
                currencies: [],
                totals_by_currency: {},
                warnings: ["Carteira ainda não carregada para esta instituição."]
            }));
        }

        const requestedIndex = institutions.findIndex((item) => normalize(item.name) === normalize(requestedInstitution));
        currentIndex = requestedIndex >= 0 ? requestedIndex : 0;
        bindActions();
        render();
    }

    return Object.freeze({
        load,
        _test: Object.freeze({
            buildSummary,
            attentionItems,
            riskItems,
            favorableItems,
            isImportIncomplete,
            applyImportStatus,
            importStatusFor
        })
    });
})();

if (typeof module !== "undefined") {
    module.exports = { InstitutionAnalysis };
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", InstitutionAnalysis.load);
}
