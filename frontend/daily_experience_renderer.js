"use strict";

const DailyExperienceRenderer = (() => {
    const LIMITS = Object.freeze({ facts: 4, market: 5, ownerImpacts: 3 });

    function panel(id) {
        return document.getElementById(id);
    }

    function text(value) {
        return typeof value === "string" ? value.trim() : "";
    }

    function clean(value) {
        return text(value)
            .replace(/analysis-[a-z0-9]+/gi, "uma análise interna")
            .replace(/A prioridade deriva de uma análise interna,?\s*/i, "")
            .replace(/A prioridade deriva de[^.]*\.?/i, "")
            .replace(/A origem está relacionada ao ativo[^.]*\.?/gi, "")
            .replace(/Direção não é recomendação\.?/gi, "")
            .replace(/\s+·\s+·/g, " ·")
            .replace(/\s{2,}/g, " ")
            .trim();
    }

    function item(title, summary = "") {
        const row = document.createElement("article");
        row.className = "daily-flow-item";

        const marker = document.createElement("span");
        marker.className = "daily-flow-marker";
        marker.setAttribute("aria-hidden", "true");

        const body = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = clean(title);
        body.appendChild(heading);

        const description = clean(summary);
        if (description && description !== clean(title)) {
            const paragraph = document.createElement("p");
            paragraph.textContent = description;
            body.appendChild(paragraph);
        }

        row.append(marker, body);
        return row;
    }

    function renderList(sectionId, listId, countId, values, limit, mapper) {
        const section = panel(sectionId);
        const list = panel(listId);
        if (!section || !list) {
            return;
        }

        list.replaceChildren();
        values.slice(0, limit).forEach((value) => {
            const mapped = mapper(value);
            if (mapped && clean(mapped.title)) {
                list.appendChild(item(mapped.title, mapped.summary));
            }
        });

        section.hidden = list.children.length === 0;
        const count = panel(countId);
        if (count) {
            count.textContent = list.children.length
                ? `${list.children.length} ${list.children.length === 1 ? "tópico" : "tópicos"}`
                : "";
        }
    }

    function formatUpdate(isoValue) {
        const date = new Date(isoValue);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        return new Intl.DateTimeFormat("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "America/Sao_Paulo"
        }).format(date);
    }

    function marketItems(response) {
        const impacts = Array.isArray(response.impact_assessments)
            ? response.impact_assessments : [];
        const priorities = Array.isArray(response.priorities)
            ? response.priorities : [];

        const combined = impacts.map((impact) => ({
            title: impact.title,
            summary: impact.summary
        })).concat(priorities.map((priority) => ({
            title: priority.title,
            summary: priority.summary || priority.reason
        })));

        const seen = new Set();
        return combined.filter((entry) => {
            const key = clean(entry.title).toLowerCase();
            if (!key || seen.has(key)) {
                return false;
            }
            seen.add(key);
            return true;
        });
    }

    function renderOwnerStatus(containerId, ownerName) {
        const container = panel(containerId);
        if (!container) {
            return;
        }
        container.replaceChildren();
        container.appendChild(item(
            `Atualize as carteiras de ${ownerName} para calcular os impactos por posição.`,
            "A análise será feita por instituição e qualquer consolidação permanecerá restrita a este titular."
        ));
    }

    function bindDecisionActions() {
        const analyze = panel("dailyAnalyzePortfolios");
        const notNow = panel("dailyNotNow");

        if (analyze && !analyze.dataset.bound) {
            analyze.dataset.bound = "true";
            analyze.addEventListener("click", () => {
                const portfolioTab = document.querySelector('[data-tab="portfolios"]');
                if (portfolioTab) {
                    portfolioTab.click();
                }
            });
        }

        if (notNow && !notNow.dataset.bound) {
            notNow.dataset.bound = "true";
            notNow.addEventListener("click", () => {
                const decision = panel("daily-decision");
                if (decision) {
                    decision.hidden = true;
                }
            });
        }
    }

    function hideState() {
        panel("daily-loading").hidden = true;
        panel("daily-error").hidden = true;
    }

    function render(response) {
        if (!response || response.status !== "SUCCESS" || !response.header
                || !Array.isArray(response.facts)
                || !Array.isArray(response.priorities)
                || !Array.isArray(response.analyses)) {
            throw new TypeError("Invalid daily experience response");
        }

        hideState();
        panel("greeting").textContent = text(response.header.greeting);
        panel("currentDate").textContent = text(response.header.display_date);

        const updateTime = formatUpdate(response.generated_at);
        panel("lastUpdateLabel").textContent = updateTime ? "Atualizado" : "";
        panel("lastUpdate").textContent = updateTime ? `hoje às ${updateTime}` : "";

        renderList(
            "daily-facts", "importantFacts", "factsCount",
            response.facts, LIMITS.facts,
            (fact) => ({
                title: fact.title || fact.text,
                summary: fact.summary
            })
        );

        renderList(
            "daily-market-reaction", "marketReaction", "marketReactionCount",
            marketItems(response), LIMITS.market,
            (entry) => entry
        );

        renderOwnerStatus("neiInvestmentImpact", "Nei");
        renderOwnerStatus("jolikaInvestmentImpact", "Jolika");

        panel("daily-investment-impact").hidden = false;
        panel("daily-decision").hidden = false;
        bindDecisionActions();
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
