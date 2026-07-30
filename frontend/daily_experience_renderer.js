"use strict";

const DailyExperienceRenderer = (() => {
    const LIMITS = Object.freeze({ facts: 5, priorities: 2, analyses: 2, contexts: 5, impacts: 5, agenda: 10, diagnostics: 10 });
    const QUALITY_LABELS = Object.freeze({ ERROR: "Erro", WARNING: "Atenção", INFO: "Informação" });
    const EVENT_LABELS = Object.freeze({
        EARNINGS: "Resultados", DIVIDEND: "Dividendos", CENTRAL_BANK: "Bancos centrais",
        MACROECONOMIC: "Economia", REGULATORY: "Regulação", CORPORATE: "Evento corporativo",
        MARKET_HOLIDAY: "Feriado de mercado", OTHER: "Outro"
    });
    const LEVEL_LABELS = Object.freeze({
        HIGH: "Alta",
        MEDIUM: "Moderada",
        MODERATE: "Moderada",
        LOW: "Baixa"
    });
    const ACTION_LABELS = Object.freeze({
        ANALYZE: "Analisar",
        DECIDE: "Decidir",
        Analisar: "Analisar",
        Decidir: "Decidir"
    });
    const DIRECTION_LABELS = Object.freeze({
        POSITIVE: "Positivo", NEGATIVE: "Negativo", MIXED: "Misto", UNCERTAIN: "Incerto"
    });
    const CONTEXT_LABELS = Object.freeze({
        RISK_ALIGNMENT: "Perfil de risco", HORIZON_ALIGNMENT: "Horizonte",
        OBJECTIVE_ALIGNMENT: "Objetivos", LIQUIDITY_CONTEXT: "Liquidez",
        PRESERVATION_CONTEXT: "Preservação de capital", VOLATILITY_CONTEXT: "Volatilidade",
        CONCENTRATION_CONTEXT: "Concentração", RESTRICTION_CONTEXT: "Restrições",
        CURRENCY_CONTEXT: "Moeda-base", MARKET_PREFERENCE: "Mercado preferencial",
        DECISION_FREQUENCY: "Frequência decisória", CONTEXT_CONFLICT: "Conflito de contexto"
    });

    function element(tagName, className, text) {
        const node = document.createElement(tagName);
        node.className = className;
        node.textContent = typeof text === "string" ? text : "";
        return node;
    }

    function text(value) {
        return typeof value === "string" ? value : "";
    }

    function item({ eyebrow, badge, title, summary, metadata }) {
        const article = element("article", "daily-item", "");
        const header = element("div", "daily-item-header", "");
        header.appendChild(element("span", "daily-item-eyebrow", eyebrow));
        if (badge) {
            header.appendChild(element("span", badge.className, badge.text));
        }
        article.appendChild(header);
        article.appendChild(element("h3", "", title));
        if (summary) {
            article.appendChild(element("p", "daily-item-summary", summary));
        }
        if (metadata) {
            article.appendChild(element("p", "daily-item-meta", metadata));
        }
        return article;
    }

    function panel(id) {
        return document.getElementById(id);
    }

    function renderCollection(panelId, listId, values, limit, createItem) {
        const section = panel(panelId);
        const container = panel(listId);
        if (!section || !container) {
            return;
        }
        container.replaceChildren();
        values.slice(0, limit).forEach((value) => container.appendChild(createItem(value)));
        section.hidden = container.children.length === 0;
    }

    function assets(itemValue) {
        const values = itemValue.affected_assets;
        return Array.isArray(values)
            ? values.filter((value) => typeof value === "string").join(" · ")
            : "";
    }

    function hideState() {
        panel("daily-loading").hidden = true;
        panel("daily-error").hidden = true;
    }

    function render(response) {
        if (!response || response.status !== "SUCCESS" || !["1.0", "1.1", "1.2", "1.3", "1.4"].includes(response.contract_version)
                || !response.header || !Array.isArray(response.facts)
                || !Array.isArray(response.priorities) || !Array.isArray(response.analyses)) {
            throw new TypeError("Invalid daily experience response");
        }

        hideState();
        panel("greeting").textContent = text(response.header.greeting);
        panel("currentDate").textContent = text(response.header.display_date);
        panel("lastUpdateLabel").textContent = "Experiência gerada em";
        panel("lastUpdate").textContent = text(response.generated_at);

        const quality = response.contract_version === "1.4" && response.data_quality
            && ["WARNING", "ERROR"].includes(response.data_quality.status)
            && Array.isArray(response.data_quality.diagnostics) ? response.data_quality.diagnostics : [];
        renderCollection("data-quality", "dataQualityDiagnostics", quality, LIMITS.diagnostics, (diagnostic) => {
            const affected = Array.isArray(diagnostic.affected_items)
                ? diagnostic.affected_items.filter((value) => typeof value === "string").join(" · ") : "";
            return item({
                eyebrow: QUALITY_LABELS[diagnostic.severity] || "Informação",
                title: text(diagnostic.title), description: text(diagnostic.description),
                summary: text(diagnostic.description),
                metadata: affected ? `Itens afetados: ${affected}` : ""
            });
        });

        renderCollection("daily-facts", "importantFacts", response.facts, LIMITS.facts, (fact) => (
            item({
                eyebrow: text(fact.category),
                title: text(fact.title || fact.text),
                summary: text(fact.summary),
                metadata: assets(fact)
            })
        ));
        renderCollection(
            "daily-priorities", "dailyPriorities", response.priorities,
            LIMITS.priorities, (priority) => {
                const level = LEVEL_LABELS[priority.level] || text(priority.label);
                return item({
                    eyebrow: ACTION_LABELS[priority.type] || text(priority.type),
                    badge: level ? {
                        className: `priority priority-${level === "Alta" ? "high" : level === "Baixa" ? "low" : "moderate"}`,
                        text: level
                    } : null,
                    title: text(priority.title),
                    summary: text(priority.summary || priority.reason),
                    metadata: assets(priority)
                });
            }
        );

        renderCollection(
            "daily-analyses", "dailyAnalyses", response.analyses,
            LIMITS.analyses, (analysis) => item({
                eyebrow: ACTION_LABELS[analysis.type] || ACTION_LABELS[analysis.action] || text(analysis.action),
                title: text(analysis.title),
                summary: text(analysis.summary || analysis.reason),
                metadata: assets(analysis)
            })
        );

        const contexts = Array.isArray(response.decision_contexts) ? response.decision_contexts : [];
        renderCollection("daily-decision-context", "dailyDecisionContexts", contexts, LIMITS.contexts, (context) => {
            const level = LEVEL_LABELS[context.relevance_level] || "";
            const related = Array.isArray(context.related_assets)
                ? context.related_assets.filter((value) => typeof value === "string").join(" · ") : "";
            const factors = Array.isArray(context.context_factors) ? context.context_factors
                .filter((factor) => factor && typeof factor.description === "string")
                .map((factor) => factor.description).join(" · ") : "";
            const limitations = Array.isArray(context.limitations)
                ? context.limitations.filter((value) => typeof value === "string").join(" · ") : "";
            const metadata = [related ? `Ativos relacionados: ${related}` : "", factors,
                limitations ? `Limitações: ${limitations}` : ""].filter(Boolean).join(" · ");
            return item({
                eyebrow: CONTEXT_LABELS[context.context_type] || "Contexto",
                badge: level ? { className: `priority priority-${level === "Alta" ? "high" : level === "Baixa" ? "low" : "moderate"}`, text: level } : null,
                title: text(context.title), summary: text(context.summary), metadata
            });
        });

        const impacts = Array.isArray(response.impact_assessments) ? response.impact_assessments : [];
        renderCollection("daily-impacts", "dailyImpacts", impacts, LIMITS.impacts, (impact) => {
            const level = LEVEL_LABELS[impact.impact_level] || "";
            const direction = DIRECTION_LABELS[impact.impact_direction] || "Incerto";
            const confidence = LEVEL_LABELS[impact.confidence] || "";
            const factors = Array.isArray(impact.impact_factors) ? impact.impact_factors
                .filter((factor) => factor && typeof factor.description === "string")
                .map((factor) => factor.description).join(" · ") : "";
            const metadata = [assets(impact) ? `Ativos relacionados: ${assets(impact)}` : "", factors]
                .filter(Boolean).join(" · ");
            return item({
                eyebrow: `Direção: ${direction} · Confiança: ${confidence}`,
                badge: level ? { className: `priority priority-${level === "Alta" ? "high" : level === "Baixa" ? "low" : "moderate"}`, text: level } : null,
                title: text(impact.title), summary: text(impact.summary), metadata
            });
        });

        const agenda = ["1.1", "1.2", "1.3", "1.4"].includes(response.contract_version) && Array.isArray(response.market_agenda)
            ? response.market_agenda : [];
        renderCollection("marketAgendaPanel", "marketAgenda", agenda, LIMITS.agenda, (event) => {
            const timing = event.all_day ? "Dia inteiro" : [text(event.event_time), text(event.timezone)]
                .filter(Boolean).join(" — ");
            const metadata = [text(event.event_date), timing,
                assets(event) ? `Relacionada a: ${assets(event)}` : "",
                text(event.source_name) ? `Fonte: ${text(event.source_name)}` : ""
            ].filter(Boolean).join(" · ");
            const level = LEVEL_LABELS[event.importance] || "";
            return item({
                eyebrow: EVENT_LABELS[event.event_type] || "Outro",
                badge: level ? {
                    className: `priority priority-${level === "Alta" ? "high" : level === "Baixa" ? "low" : "moderate"}`,
                    text: level
                } : null,
                title: text(event.title), summary: text(event.summary), metadata
            });
        });
        panel("market-agenda").hidden = agenda.length === 0;
    }

    function showLoading() {
        panel("daily-error").hidden = true;
        panel("daily-loading").hidden = false;
    }

    function showError() {
        panel("daily-loading").hidden = true;
        panel("daily-error").hidden = false;
        panel("daily-error").textContent = "Não foi possível preparar a experiência diária.";
    }

    return Object.freeze({ render, showLoading, showError });
})();

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DailyExperienceRenderer };
}
