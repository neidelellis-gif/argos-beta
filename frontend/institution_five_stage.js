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
        const compositionStage = stageByKey(report, "composition");
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

        const concentrationItem = (Array.isArray(compositionStage?.items) ? compositionStage.items : [])
            .find((item) => /maiores posições/i.test(String(item?.title || "")));
        const concentrationText = String(concentrationItem?.reading || "");
        const largestMatch = concentrationText.match(/Maior posição\s+([0-9.,]+%)/i);
        const largestPosition = largestMatch ? largestMatch[1] : null;

        return { strengths, attention, market, forwarding, largestPosition };
    }

    function executiveHeadline(model) {
        const attentionCount = model.attention.length;
        const concentration = model.largestPosition
            ? `A maior posição representa ${model.largestPosition}`
            : "A carteira não mostra concentração dominante confirmada";

        if (!attentionCount) {
            return `${concentration}. Nenhum problema relevante exige providência neste momento.`;
        }
        const positions = attentionCount === 1 ? "1 posição apresenta" : `${attentionCount} posições apresentam`;
        return `${concentration}. ${positions} comportamento recente que merece acompanhamento mais próximo.`;
    }

    function parseAttention(value) {
        const text = String(value || "").trim();
        const separator = text.includes(" — ") ? " — " : ": ";
        const parts = text.split(separator);
        if (parts.length < 2) return { asset: "Atenção", detail: text };
        return {
            asset: parts.shift().trim(),
            detail: parts.join(separator).trim()
        };
    }

    function executiveCard(kicker, title, className = "") {
        const article = element("article", `executive-card ${className}`.trim());
        article.append(
            element("p", "executive-card-kicker", kicker),
            element("h3", "", title)
        );
        return article;
    }

    function renderStrengthCard(values) {
        const card = executiveCard("ESTRUTURA", "O que está bem", "executive-card-positive");
        if (!values.length) {
            card.append(element("p", "executive-card-empty", "Sem destaque positivo adicional."));
            return card;
        }
        const list = element("div", "executive-strength-list");
        values.forEach((value) => {
            const row = element("div", "executive-strength-row");
            row.append(
                element("span", "executive-strength-mark", "✓"),
                element("p", "", value)
            );
            list.append(row);
        });
        card.append(list);
        return card;
    }

    function renderAttentionCard(values) {
        const card = executiveCard("PRIORIDADE", "O que merece atenção", "executive-card-attention");
        if (!values.length) {
            card.append(element("p", "executive-card-empty", "Nenhum problema relevante foi confirmado."));
            return card;
        }
        const list = element("div", "executive-attention-list");
        values.forEach((value) => {
            const item = parseAttention(value);
            const row = element("div", "executive-attention-row");
            row.append(
                element("strong", "executive-asset", item.asset),
                element("p", "", item.detail)
            );
            list.append(row);
        });
        card.append(list);
        return card;
    }

    function renderMarketCard(items) {
        if (!items.length) return null;
        const card = executiveCard("CONTEXTO", "O que está acontecendo", "executive-card-market");
        const list = element("div", "executive-market-list");
        items.forEach((item) => {
            const row = element("div", "executive-market-row");
            row.append(
                element("strong", "", item.title),
                element("p", "", item.reading)
            );
            list.append(row);
        });
        card.append(list);
        return card;
    }

    function renderForwardingCard(text) {
        const card = executiveCard("PRÓXIMO PASSO", "Encaminhamento", "executive-card-forwarding");
        card.append(element("p", "executive-forwarding-text", text));
        return card;
    }

    function renderExecutiveReport(report, container) {
        const model = executiveModel(report);
        const summary = document.getElementById("executiveSummary");
        if (summary) summary.textContent = executiveHeadline(model);

        setMetric(
            "metricCurrencies",
            "Maior posição",
            model.largestPosition || "—"
        );
        setMetric(
            "metricSituation",
            "Pontos de atenção",
            model.attention.length ? `${model.attention.length} ativo${model.attention.length > 1 ? "s" : ""}` : "Nenhum"
        );

        container.append(
            renderStrengthCard(model.strengths),
            renderAttentionCard(model.attention)
        );

        const marketCard = renderMarketCard(model.market);
        if (marketCard) container.append(marketCard);
        container.append(renderForwardingCard(model.forwarding));
        return model;
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

    function consolidatedMetricValues(dashboard, model) {
        const consolidated = dashboard?.consolidated || {};
        const totals = Object.entries(consolidated.totals_by_currency || {});
        const totalText = totals.length
            ? totals.map(([currency, value]) => formatCurrency(value, currency)).join(" · ")
            : "—";
        const attentionCount = Array.isArray(model?.attention) ? model.attention.length : 0;

        return {
            totalText,
            positions: String(consolidated.position_count ?? "—"),
            largestPosition: model?.largestPosition || "—",
            attention: attentionCount
                ? `${attentionCount} ativo${attentionCount > 1 ? "s" : ""}`
                : "Nenhum"
        };
    }

    function applyConsolidatedPresentation(dashboard, model) {
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
        if (legacySummary) legacySummary.hidden = false;
        if (legacyMetrics) legacyMetrics.hidden = false;
        if (decision) decision.hidden = true;
        if (footer) footer.hidden = true;
        if (lock) {
            const label = lock.querySelector("strong");
            if (label) label.textContent = "Leituras individuais concluídas";
        }

        const metrics = consolidatedMetricValues(dashboard, model);
        setMetric("metricValue", "Patrimônio consolidado", metrics.totalText);
        setMetric("metricPositions", "Posições consolidadas", metrics.positions);
        setMetric("metricCurrencies", "Maior posição", metrics.largestPosition);
        setMetric("metricSituation", "Pontos de atenção", metrics.attention);

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
        const model = renderExecutiveReport(report, container);

        if (typeof window !== "undefined" && typeof window.CustomEvent === "function") {
            window.dispatchEvent(new CustomEvent("argos:patrimonial-report", {
                detail: { report }
            }));
        }

        if (report.scope === "consolidated") {
            applyConsolidatedPresentation(dashboard, model);
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
        if (typeof document === "undefined") return;
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
            executiveHeadline,
            parseAttention,
            consolidatedMetricValues,
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