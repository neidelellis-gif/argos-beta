"use strict";

const InstitutionAnalysis = (() => {
    const COMPLETED_KEY = "argos.completed-institutions";
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

    function buildSummary(institution) {
        const positions = Number(institution.position_count || 0);
        const currencies = Array.isArray(institution.currencies) ? institution.currencies : [];
        const warnings = Array.isArray(institution.warnings) ? institution.warnings : [];
        if (!positions) {
            return `A carteira de ${institution.name} foi identificada, mas ainda não possui posições suficientes para um diagnóstico completo.`;
        }
        if (warnings.length) {
            return `A carteira de ${institution.name} possui ${positions} posições. O diagnóstico inicial indica pontos que merecem verificação antes de qualquer consolidação.`;
        }
        const currencyText = currencies.length ? `, com exposição em ${currencies.join(" e ")}` : "";
        return `A carteira de ${institution.name} possui ${positions} posições${currencyText}. Nesta leitura inicial, não há alerta operacional crítico, mas a composição deve ser analisada antes da consolidação.`;
    }

    function attentionItems(institution) {
        const items = [];
        const warnings = Array.isArray(institution.warnings) ? institution.warnings : [];
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
        const institution = selectedInstitution();
        if (!institution) return;
        const done = isCompleted(institution.name);

        $("ownerLabel").textContent = `Patrimônio de ${owner.name}`;
        $("institutionName").textContent = institution.name;
        $("institutionMeta").textContent = `${owner.name} · análise individual · ${new Intl.DateTimeFormat("pt-BR").format(new Date())}`;
        $("executiveSummary").textContent = buildSummary(institution);
        $("metricValue").textContent = institutionValue(institution);
        $("metricPositions").textContent = String(institution.position_count || 0);
        $("metricCurrencies").textContent = (institution.currencies || []).join(" · ") || "—";
        $("metricSituation").textContent = (institution.warnings || []).length ? "Atenção" : "Regular";
        $("attentionCount").textContent = `${attentionItems(institution).length} pontos`;

        const status = $("institutionStatus");
        status.textContent = done ? "Concluída" : "Em análise";
        status.classList.toggle("done", done);
        $("completeInstitution").textContent = done ? "Ir para a próxima instituição →" : "Concluir análise desta instituição →";

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

    return Object.freeze({ load });
})();

document.addEventListener("DOMContentLoaded", InstitutionAnalysis.load);
