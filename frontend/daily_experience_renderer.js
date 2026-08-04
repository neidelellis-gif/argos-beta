"use strict";

const DailyExperienceRenderer = (() => {
    const LIMITS = Object.freeze({ facts: 4, market: 5, ownerImpacts: 3 });

    const OWNER_ASSETS = Object.freeze({
        nei: new Set([
            "BTC", "BITCOIN", "ETH", "ETHER", "ETHEREUM", "SOL", "SOLANA", "SUI", "APT", "NEAR",
            "ARB", "AXL", "RAY", "LDO", "AAVE", "PENDLE", "CRV", "UNI", "ENS", "RNDR", "FET",
            "TAO", "ETHFI", "WLD", "HYPE", "DOGE", "SHIB", "PEPE", "WIF", "ENA", "AVAX", "ONDO", "LINK"
        ]),
        jolika: new Set([
            "AIQ", "EQIX", "DXCM", "URA", "GLD", "ARKQ", "XLI", "FEZ", "ICE", "QTUM", "BNC", "HDV"
        ])
    });

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

    function normalizeAsset(value) {
        return text(value).toUpperCase().replace(/[^A-Z0-9]/g, "");
    }

    function assetNames(value) {
        return Array.isArray(value?.affected_assets)
            ? value.affected_assets.filter((asset) => typeof asset === "string" && asset.trim())
            : [];
    }

    function item(title, summary = "", className = "") {
        const row = document.createElement("article");
        row.className = `daily-flow-item ${className}`.trim();

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

    function statusLabel(direction) {
        const normalized = text(direction).toUpperCase();
        if (normalized === "POSITIVE") return { label: "Positivo", className: "positive" };
        if (normalized === "NEGATIVE") return { label: "Negativo", className: "negative" };
        return { label: "Acompanhar", className: "watch" };
    }

    function impactCard(asset, impact) {
        const status = statusLabel(impact.impact_direction);
        const card = document.createElement("article");
        card.className = `daily-asset-impact daily-asset-impact-${status.className}`;

        const top = document.createElement("div");
        top.className = "daily-asset-impact-top";
        const ticker = document.createElement("strong");
        ticker.textContent = asset;
        const badge = document.createElement("span");
        badge.className = `daily-impact-badge daily-impact-badge-${status.className}`;
        badge.textContent = status.label;
        top.append(ticker, badge);

        const description = document.createElement("p");
        description.textContent = clean(impact.summary || impact.title || "Ativo relacionado ao cenário atual.");
        card.append(top, description);
        return card;
    }

    function renderList(sectionId, listId, countId, values, limit, mapper, className = "") {
        const section = panel(sectionId);
        const list = panel(listId);
        if (!section || !list) return 0;

        list.replaceChildren();
        values.slice(0, limit).forEach((value) => {
            const mapped = mapper(value);
            if (mapped && clean(mapped.title)) {
                list.appendChild(item(mapped.title, mapped.summary, className));
            }
        });

        section.hidden = list.children.length === 0;
        const count = panel(countId);
        if (count) {
            count.textContent = list.children.length
                ? `${list.children.length} ${list.children.length === 1 ? "tópico" : "tópicos"}`
                : "";
        }
        return list.children.length;
    }

    function formatUpdate(isoValue) {
        const date = new Date(isoValue);
        if (Number.isNaN(date.getTime())) return "";
        return new Intl.DateTimeFormat("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: "America/Sao_Paulo"
        }).format(date);
    }

    function marketItems(response) {
        const impacts = Array.isArray(response.impact_assessments) ? response.impact_assessments : [];
        const priorities = Array.isArray(response.priorities) ? response.priorities : [];
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
            if (!key || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function ownerForAsset(asset) {
        const normalized = normalizeAsset(asset);
        if (OWNER_ASSETS.nei.has(normalized)) return "nei";
        if (OWNER_ASSETS.jolika.has(normalized)) return "jolika";
        return null;
    }

    function renderOwnerImpacts(response) {
        const containers = {
            nei: panel("neiInvestmentImpact"),
            jolika: panel("jolikaInvestmentImpact")
        };
        Object.values(containers).forEach((container) => container?.replaceChildren());

        const impacts = Array.isArray(response.impact_assessments) ? response.impact_assessments : [];
        const grouped = { nei: [], jolika: [] };

        impacts.forEach((impact) => {
            assetNames(impact).forEach((asset) => {
                const owner = ownerForAsset(asset);
                if (owner && grouped[owner].length < LIMITS.ownerImpacts) {
                    grouped[owner].push({ asset, impact });
                }
            });
        });

        ["nei", "jolika"].forEach((owner) => {
            const container = containers[owner];
            if (!container) return;
            if (grouped[owner].length) {
                grouped[owner].forEach(({ asset, impact }) => container.appendChild(impactCard(asset, impact)));
            } else {
                const ownerName = owner === "nei" ? "Nei" : "Jolika";
                container.appendChild(item(
                    `Nenhuma implicação específica foi identificada para ${ownerName} nesta leitura.`,
                    "A posição mais recente permanece como referência."
                ));
            }
        });
    }

    function bindDecisionActions() {
        const analyze = panel("dailyAnalyzePortfolios");
        const notNow = panel("dailyNotNow");

        if (analyze && !analyze.dataset.bound) {
            analyze.dataset.bound = "true";
            analyze.addEventListener("click", () => {
                window.location.href = "/analysis_start.html";
            });
        }

        if (notNow && !notNow.dataset.bound) {
            notNow.dataset.bound = "true";
            notNow.addEventListener("click", () => {
                notNow.textContent = "Continuar depois";
                notNow.setAttribute("aria-label", "A análise poderá ser aprofundada depois");
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

        const factsSection = panel("daily-facts");
        const factsRendered = renderList(
            "daily-facts", "importantFacts", "factsCount",
            response.facts, LIMITS.facts,
            (fact) => ({ title: fact.title || fact.text, summary: fact.summary }),
            "daily-flow-item-featured"
        );

        if (factsRendered === 0 && factsSection) {
            const factsList = panel("importantFacts");
            factsList.appendChild(item(
                "Nenhum fato relevante foi incorporado nas últimas 24 horas.",
                "A leitura do mercado aparece somente depois desta verificação."
            ));
            factsSection.hidden = false;
        }

        renderList(
            "daily-market-reaction", "marketReaction", "marketReactionCount",
            marketItems(response), LIMITS.market,
            (entry) => entry,
            "daily-flow-item-market"
        );

        renderOwnerImpacts(response);
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
