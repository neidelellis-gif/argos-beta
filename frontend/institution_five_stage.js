"use strict";

const InstitutionFiveStage = (() => {
    const METHOD = "ARGOS_PATRIMONIAL_5_STAGE_V1";

    function normalize(value) {
        return String(value || "").normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim().toLowerCase();
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    async function loadDailyIntelligence() {
        const response = await fetch("/api/daily-experience", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            cache: "no-store",
            body: JSON.stringify({ positions: [], fact_candidates: [], reference_date: null })
        });
        if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
        const payload = await response.json();
        if (payload?.status !== "SUCCESS") throw new Error("Inteligência patrimonial indisponível.");
        return payload?.experience?.portfolio_intelligence || {};
    }

    async function loadDashboard() {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        if (!response.ok) throw new Error(`Erro HTTP ${response.status}`);
        return response.json();
    }

    function selectedReport(intelligence) {
        const params = new URLSearchParams(window.location.search);
        if (params.get("consolidated") === "1") {
            return intelligence?.JOLIKA?.patrimonial_analysis || null;
        }
        const requested = normalize(params.get("institution"));
        const entry = Object.entries(intelligence).find(([name]) => (
            name !== "JOLIKA" && normalize(name) === requested
        ));
        return entry?.[1]?.patrimonial_analysis || null;
    }

    function evidenceText(item) {
        const evidence = Array.isArray(item?.evidence) ? item.evidence.filter(Boolean) : [];
        if (!evidence.length) return "";
        return `Evidência: ${evidence.join(" · ")}.`;
    }

    function renderStage(stage, index) {
        const article = element("article", `five-stage-card five-stage-${stage.status || "available"}`);
        const header = element("div", "five-stage-header");
        const number = element("span", "five-stage-number", String(index + 1).padStart(2, "0"));
        const heading = element("div");
        heading.append(
            element("p", "institution-kicker", `ETAPA ${index + 1}`),
            element("h2", "", stage.title || "Etapa")
        );
        const status = element(
            "span",
            "five-stage-status",
            stage.status === "limited" ? "Base limitada" : "Analisada"
        );
        header.append(number, heading, status);
        article.append(header, element("p", "five-stage-summary", stage.summary || ""));

        const items = element("div", "five-stage-items");
        (Array.isArray(stage.items) ? stage.items : []).forEach((item) => {
            const row = element("div", "five-stage-item");
            row.append(
                element("strong", "", item.title || "Leitura"),
                element("p", "", item.reading || "")
            );
            const evidence = evidenceText(item);
            if (evidence) row.append(element("small", "", evidence));
            items.append(row);
        });
        article.append(items);
        return article;
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

    function setMetric(id, label, value) {
        const metric = document.getElementById(id);
        if (!metric) return;
        metric.textContent = value;
        const article = metric.closest("article");
        const labelNode = article?.querySelector("span");
        if (labelNode) labelNode.textContent = label;
    }

    function applyConsolidatedPresentation(dashboard) {
        const title = document.getElementById("institutionName");
        const meta = document.getElementById("institutionMeta");
        const kicker = document.getElementById("analysisModeKicker");
        const status = document.getElementById("institutionStatus");
        const legacySummary = document.getElementById("executiveSummary")?.closest(".institution-summary");
        const legacyMetrics = document.getElementById("metricValue")?.closest(".institution-metrics");
        const decision = document.getElementById("consolidatedDecision");
        const footer = document.querySelector("main.institution-main > footer.institution-actions");
        const lock = document.querySelector(".institution-consolidation-lock");

        if (title) title.textContent = "JOLIKA consolidada";
        if (meta) meta.textContent = `Jolika · análise consolidada · ${new Intl.DateTimeFormat("pt-BR").format(new Date())}`;
        if (kicker) kicker.textContent = "LEITURA CONSOLIDADA";
        if (status) {
            status.textContent = "Concluída";
            status.classList.add("done");
        }
        if (legacySummary) legacySummary.hidden = true;
        if (legacyMetrics) legacyMetrics.hidden = false;
        if (decision) decision.hidden = true;
        if (footer) footer.hidden = true;
        if (lock) {
            const label = lock.querySelector("strong");
            if (label) label.textContent = "Leituras individuais concluídas";
        }

        const consolidated = dashboard?.consolidated || {};
        const totals = Object.entries(consolidated.totals_by_currency || {});
        const totalText = totals.length
            ? totals.map(([currency, value]) => formatCurrency(value, currency)).join(" · ")
            : "—";
        const currencies = totals.map(([currency]) => currency);

        setMetric("metricValue", "Patrimônio consolidado", totalText);
        setMetric(
            "metricPositions",
            "Posições consolidadas",
            String(consolidated.position_count ?? "—")
        );
        setMetric(
            "metricCurrencies",
            "Moedas encontradas",
            currencies.join(" · ") || "—"
        );
        setMetric(
            "metricSituation",
            "Condição da análise",
            dashboard?.session?.consolidation_authorized === true
                ? "Consolidação concluída"
                : "Consolidação não autorizada"
        );

        const completed = new Set(
            Array.isArray(dashboard?.session?.completed_institutions)
                ? dashboard.session.completed_institutions.map(normalize)
                : []
        );
        document.querySelectorAll("#institutionNav button").forEach((button) => {
            const name = normalize(button.textContent);
            button.classList.remove("active");
            button.classList.toggle("done", completed.has(name));
        });
    }

    function renderReport(report, dashboard) {
        const container = document.getElementById("fiveStageReport");
        const state = document.getElementById("fiveStageState");
        if (!container || !state) return;
        container.replaceChildren();

        if (!report || report.method !== METHOD || !Array.isArray(report.stages) || report.stages.length !== 5) {
            state.textContent = "O relatório de cinco etapas ainda não está disponível para esta análise.";
            state.hidden = false;
            return;
        }

        state.hidden = true;
        report.stages.forEach((stage, index) => container.append(renderStage(stage, index)));

        if (report.scope === "consolidated") {
            applyConsolidatedPresentation(dashboard);
        }
    }

    async function load() {
        const state = document.getElementById("fiveStageState");
        if (state) {
            state.hidden = false;
            state.textContent = "Preparando as cinco etapas da análise…";
        }
        try {
            const [intelligence, dashboard] = await Promise.all([
                loadDailyIntelligence(),
                loadDashboard()
            ]);
            renderReport(selectedReport(intelligence), dashboard);
        } catch (error) {
            console.error("Five-stage patrimonial analysis failed", error);
            if (state) state.textContent = "Não foi possível carregar o relatório patrimonial agora.";
        }
    }

    async function authorizeConsolidation() {
        const response = await fetch("/api/portfolios/consolidate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            cache: "no-store",
            body: "{}"
        });
        const payload = await response.json();
        if (!response.ok || payload?.ok !== true || payload?.consolidation_authorized !== true) {
            throw new Error(payload?.error || "Não foi possível autorizar a análise consolidada.");
        }
        return payload;
    }

    function bindConsolidatedDecision() {
        document.addEventListener("click", async (event) => {
            const button = event.target.closest?.("#openConsolidated");
            if (!button) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            button.disabled = true;
            try {
                await authorizeConsolidation();
                window.location.href = "/institution_analysis.html?owner=jolika&consolidated=1";
            } catch (error) {
                console.error("Jolika consolidation authorization failed", error);
                button.disabled = false;
                window.alert(error.message || "Não foi possível abrir a análise consolidada agora.");
            }
        }, true);
    }

    bindConsolidatedDecision();
    return Object.freeze({
        load,
        _test: Object.freeze({
            selectedReport,
            authorizeConsolidation,
            applyConsolidatedPresentation,
            formatCurrency
        })
    });
})();

if (typeof module !== "undefined" && module.exports) {
    module.exports = { InstitutionFiveStage };
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", InstitutionFiveStage.load);
}
