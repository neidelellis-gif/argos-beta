"use strict";

const InstitutionFiveStage = (() => {
    const METHOD = "ARGOS_PATRIMONIAL_5_STAGE_V1";
    let explicitConsolidationRequest = false;
    const nativeFetch = typeof window !== "undefined" ? window.fetch.bind(window) : null;

    function isConsolidatedMode() {
        return typeof window !== "undefined"
            && new URLSearchParams(window.location.search).get("consolidated") === "1";
    }

    function revealConsolidatedView() {
        if (typeof document === "undefined") return;
        document.documentElement.classList.remove("consolidated-loading");
    }

    function installConsolidationGuard() {
        if (!nativeFetch || typeof window === "undefined") return;
        window.fetch = async (input, init = {}) => {
            const url = typeof input === "string" ? input : input?.url || "";
            const method = String(init?.method || "GET").toUpperCase();
            if (
                url === "/api/portfolios/consolidate"
                && method === "POST"
                && !explicitConsolidationRequest
            ) {
                return new Response(JSON.stringify({
                    ok: true,
                    consolidation_authorized: false
                }), {
                    status: 200,
                    headers: { "Content-Type": "application/json" }
                });
            }
            return nativeFetch(input, init);
        };
    }

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

    function prepareConsolidatedLoading() {
        if (!isConsolidatedMode() || typeof document === "undefined") return;
        const title = document.getElementById("institutionName");
        const meta = document.getElementById("institutionMeta");
        const kicker = document.getElementById("analysisModeKicker");
        const status = document.getElementById("institutionStatus");
        const legacySummary = document.getElementById("executiveSummary")?.closest(".institution-summary");
        const legacyMetrics = document.getElementById("metricValue")?.closest(".institution-metrics");
        const details = document.querySelector(".institution-supporting-details");
        const decision = document.getElementById("consolidatedDecision");
        const footer = document.querySelector("main.institution-main > footer.institution-actions");

        if (kicker) kicker.textContent = "LEITURA CONSOLIDADA";
        if (title) title.textContent = "JOLIKA consolidada";
        if (meta) meta.textContent = "Carregando análise consolidada…";
        if (status) {
            status.textContent = "Carregando";
            status.classList.remove("done");
        }
        if (legacySummary) legacySummary.hidden = true;
        if (legacyMetrics) legacyMetrics.hidden = true;
        if (details) details.hidden = true;
        if (decision) decision.hidden = true;
        if (footer) footer.hidden = true;
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
        if (evidence.length === 1 && /^Fontes consultadas:/i.test(evidence[0])) {
            return evidence[0];
        }
        return `Base usada: ${evidence.join(" · ")}.`;
    }

    function splitReading(value, limit = 3) {
        return String(value || "")
            .split(" • ")
            .map((item) => item.trim())
            .filter(Boolean)
            .slice(0, limit);
    }

    function stageByKey(report, key) {
        return (Array.isArray(report?.stages) ? report.stages : [])
            .find((stage) => stage?.key === key) || null;
    }

    function itemByTitle(stage, title) {
        return (Array.isArray(stage?.items) ? stage.items : [])
            .find((item) => normalize(item?.title) === normalize(title)) || null;
    }

    function executiveModel(report) {
        const finalStage = stageByKey(report, "final_diagnosis");
        const marketStage = stageByKey(report, "market_context");
        const strengths = splitReading(itemByTitle(finalStage, "O que está bem")?.reading, 3);
        const attention = splitReading(itemByTitle(finalStage, "O que merece atenção")?.reading, 3);
        const forwarding = itemByTitle(finalStage, "Encaminhamento")?.reading || "Nada relevante exige providência neste momento.";
        const market = marketStage?.status === "available"
            ? (Array.isArray(marketStage.items) ? marketStage.items : [])
                .slice(0, 2)
                .map((item) => ({
                    title: item.title || "Mercado",
                    reading: item.reading || ""
                }))
                .filter((item) => item.reading)
            : [];
        return { strengths, attention, market, forwarding };
    }

    function compactCard(title, values, className = "") {
        const article = element("article", `executive-card ${className}`.trim());
        article.append(element("h3", "", title));
        if (!values.length) {
            article.append(element("p", "executive-card-empty", "Sem destaque adicional."));
            return article;
        }
        const list = element("ul", "executive-card-list");
        values.forEach((value) => list.append(element("li", "", value)));
        article.append(list);
        return article;
    }

    function renderExecutiveReport(report, container) {
        const model = executiveModel(report);
        container.append(
            compactCard("O que está bem", model.strengths, "executive-card-positive"),
            compactCard("O que merece atenção", model.attention, "executive-card-attention")
        );

        if (model.market.length) {
            container.append(compactCard(
                "O que está acontecendo",
                model.market.map((item) => `${item.title}: ${item.reading}`),
                "executive-card-market"
            ));
        }

        const forwarding = element("article", "executive-card executive-card-wide executive-card-forwarding");
        forwarding.append(
            element("h3", "", "Encaminhamento"),
            element("p", "", model.forwarding)
        );
        container.append(forwarding);
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
            state.textContent = "A leitura executiva ainda não está disponível para esta análise.";
            state.hidden = false;
            return;
        }

        state.hidden = true;
        renderExecutiveReport(report, container);

        if (typeof window !== "undefined" && typeof window.CustomEvent === "function") {
            window.dispatchEvent(new CustomEvent("argos:patrimonial-report", {
                detail: { report }
            }));
        }

        if (report.scope === "consolidated") {
            applyConsolidatedPresentation(dashboard);
        }
    }

    async function load() {
        prepareConsolidatedLoading();
        const consolidatedMode = isConsolidatedMode();
        const state = document.getElementById("fiveStageState");
        if (state) {
            state.hidden = false;
            state.textContent = consolidatedMode
                ? "Carregando análise consolidada…"
                : "Preparando a leitura da carteira…";
        }
        try {
            const [intelligence, dashboard] = await Promise.all([
                loadDailyIntelligence(),
                loadDashboard()
            ]);
            renderReport(selectedReport(intelligence), dashboard);
            if (consolidatedMode) revealConsolidatedView();
        } catch (error) {
            console.error("Five-stage patrimonial analysis failed", error);
            if (state) state.textContent = "Não foi possível carregar a leitura da carteira agora.";
            if (consolidatedMode) revealConsolidatedView();
        }
    }

    async function authorizeConsolidation() {
        explicitConsolidationRequest = true;
        try {
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
        } finally {
            explicitConsolidationRequest = false;
        }
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

    installConsolidationGuard();
    bindConsolidatedDecision();
    return Object.freeze({
        load,
        _test: Object.freeze({
            selectedReport,
            authorizeConsolidation,
            applyConsolidatedPresentation,
            formatCurrency,
            splitReading,
            executiveModel,
            isConsolidatedMode,
            prepareConsolidatedLoading,
            revealConsolidatedView
        })
    });
})();

if (typeof module !== "undefined" && module.exports) {
    module.exports = { InstitutionFiveStage };
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", InstitutionFiveStage.load);
}