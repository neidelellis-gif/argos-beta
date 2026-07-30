"use strict";

const DailyExperienceRenderer = (() => {
    const LIMITS = Object.freeze({ facts: 5, priorities: 2, analyses: 2 });
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
        if (!response || response.status !== "SUCCESS" || response.contract_version !== "1.0"
                || !response.header || !Array.isArray(response.facts)
                || !Array.isArray(response.priorities) || !Array.isArray(response.analyses)) {
            throw new TypeError("Invalid daily experience response");
        }

        hideState();
        panel("greeting").textContent = text(response.header.greeting);
        panel("currentDate").textContent = text(response.header.display_date);
        panel("lastUpdateLabel").textContent = "Experiência gerada em";
        panel("lastUpdate").textContent = text(response.generated_at);

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

        // Agenda is not part of public contract 1.0. Keep its prepared panel hidden.
        panel("market-agenda").hidden = true;
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
