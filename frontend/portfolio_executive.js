"use strict";

const PortfolioExecutive = (() => {
    const INVESTOR_PROFILE_KEY = "argos.investor-profile";
    let dashboard = null;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function normalize(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim()
            .toLowerCase();
    }

    function ownerInstitutions() {
        const owner = ArgosAnalysisContext.getActiveOwner();
        const allowed = new Set(owner.institutions.map(normalize));
        return (dashboard && Array.isArray(dashboard.institutions)
            ? dashboard.institutions
            : []).filter((institution) => allowed.has(normalize(institution.name)));
    }

    function investorProfile() {
        try {
            const stored = JSON.parse(
                window.localStorage.getItem(INVESTOR_PROFILE_KEY) || "null"
            );
            return stored?.profile || null;
        } catch (_) {
            return null;
        }
    }

    function todayUtc() {
        const now = new Date();
        return new Date(Date.UTC(
            now.getUTCFullYear(),
            now.getUTCMonth(),
            now.getUTCDate()
        ));
    }

    function isProfileValid(
        profile = investorProfile(),
        referenceDate = todayUtc()
    ) {
        if (!profile || typeof profile !== "object") {
            return false;
        }

        const required = [
            "profile_name",
            "risk_level",
            "investment_horizon",
            "liquidity_needs",
            "capital_preservation_level",
            "review_date"
        ];

        if (required.some(
            (field) => !String(profile[field] || "").trim()
        )) {
            return false;
        }

        const reviewDate = new Date(
            `${profile.review_date}T00:00:00Z`
        );

        return Number.isFinite(reviewDate.getTime())
            && reviewDate >= referenceDate;
    }

    function pendingProfileReading(intelligence) {
        const coverage = intelligence?.coverage || {};
        const total = Number(
            coverage.consolidated_asset_count ?? 0
        );
        const identified = Number(
            coverage.assets_with_identifier ?? 0
        );
        const missing = Number(
            coverage.assets_without_identifier ?? 0
        );

        const identificationText =
            total > 0 && missing === 0
                ? "Todas as posições foram identificadas."
                : total > 0
                    ? `${identified} de ${total} ativos consolidados foram identificados.`
                    : "As posições importadas foram identificadas.";

        const materialityWeight = Number(
            intelligence?.materiality?.max_position_weight
        );

        const concentrationWeights = (
            intelligence?.concentration_by_currency || []
        )
            .map((item) => Number(item?.top_1_weight))
            .filter((value) => Number.isFinite(value));

        const rawWeight = Number.isFinite(materialityWeight)
            ? materialityWeight
            : concentrationWeights.length
                ? Math.max(...concentrationWeights)
                : null;

        const positionText = Number.isFinite(rawWeight)
            ? ` A sua maior posição representa ${(rawWeight * 100).toFixed(1)}% da carteira.`
            : "";

        return (
            `${identificationText}${positionText} ` +
            "A leitura estratégica será concluída após o preenchimento do Perfil Estratégico."
        );
    }

    function formatCurrency(value, currency) {
        const number = Number(value);
        if (!Number.isFinite(number)) {
            return "—";
        }
        const locale = currency === "BRL" ? "pt-BR" : "en-US";
        const symbol = { BRL: "R$", USD: "US$", EUR: "€" }[currency] || currency;
        return `${symbol} ${new Intl.NumberFormat(locale, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(number)}`;
    }

    function totalsByCurrency(institutions) {
        return institutions.reduce((totals, institution) => {
            Object.entries(institution.totals_by_currency || {}).forEach(([currency, value]) => {
                totals[currency] = (totals[currency] || 0) + Number(value || 0);
            });
            return totals;
        }, {});
    }

    function renderTotals(institutions) {
        const container = document.getElementById("portfolioExecutiveTotals");
        container.replaceChildren();
        const totals = totalsByCurrency(institutions);
        const entries = Object.entries(totals);

        if (entries.length === 0) {
            container.append(element(
                "p",
                "portfolio-empty",
                "Nenhuma carteira foi importada para este titular."
            ));
            return;
        }

        entries.forEach(([currency, value]) => {
            const row = element("div", "portfolio-total-row");
            const label = element("span", "portfolio-total-label", `Patrimônio em ${currency}`);
            const formattedValue = formatCurrency(value, currency);
            const amount = element(
                "strong",
                "portfolio-total-value financial-value",
                formattedValue
            );
            amount.dataset.value = formattedValue;

            if (
                typeof dashboardValuesVisible !== "undefined"
                && !dashboardValuesVisible
            ) {
                amount.textContent = "••••";
            }

            row.append(label, amount);
            container.append(row);
        });
    }

    function renderAllocation(institutions) {
        const container = document.getElementById("portfolioExecutiveAllocation");
        container.replaceChildren();
        const totals = totalsByCurrency(institutions);
        const entries = Object.entries(totals);
        const grandTotal = entries.reduce((sum, [, value]) => sum + Math.abs(Number(value)), 0);

        if (!grandTotal) {
            container.append(element(
                "p",
                "portfolio-empty",
                "A distribuição será exibida depois da importação das carteiras."
            ));
            return;
        }

        const bars = element("div", "portfolio-allocation-bars");
        entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).forEach(([currency, value]) => {
            const percentage = Math.abs(Number(value)) / grandTotal * 100;
            const row = element("div", "portfolio-allocation-row");
            const label = element("span", "portfolio-total-label", currency);
            const track = element("div", "portfolio-allocation-track");
            const fill = element("div", "portfolio-allocation-fill");
            fill.style.width = `${Math.max(2, percentage)}%`;
            track.append(fill);
            row.append(label, track, element("span", "portfolio-row-meta", `${percentage.toFixed(1)}%`));
            bars.append(row);
        });
        container.append(bars);
    }

    function renderAttention(institutions, intelligence) {
        const container = document.getElementById("portfolioExecutiveAttention");
        container.replaceChildren();
        const owner = ArgosAnalysisContext.getActiveOwner();
        const loaded = new Set(institutions.map((institution) => normalize(institution.name)));
        const missing = owner.institutions.filter((name) => !loaded.has(normalize(name)));
        const list = element("div", "portfolio-attention-list");

        if (institutions.length === 0) {
            list.append(attentionRow(
                "Importação necessária",
                `Importe as carteiras de ${owner.name} para iniciar as análises individuais.`
            ));
        } else {
            list.append(attentionRow(
                "Análises individuais primeiro",
                `${institutions.length} ${institutions.length === 1 ? "instituição carregada" : "instituições carregadas"}. O consolidado permanece bloqueado.`,
                "accent"
            ));

            /*
             * Regra patrimonial do ARGOS:
             * inteligência consolidada não pode ser exibida antes da
             * autorização explícita do usuário para consolidar.
             *
             * Nesta etapa, cada instituição permanece integralmente
             * independente, inclusive quando existem ativos iguais.
             */

            if (missing.length) {
                list.append(attentionRow(
                    "Carteiras ainda não carregadas",
                    missing.join(" · ")
                ));
            } else {
                list.append(attentionRow(
                    "Importação completa",
                    "Todas as instituições previstas estão carregadas. A próxima etapa é concluir cada análise individual."
                ));
            }
        }
        container.append(list);
    }

    function attentionRow(title, description, tone = "accent") {
        const row = element(
            "div",
            `portfolio-attention-row portfolio-attention-${tone}`
        );
        const content = element("div");
        content.append(
            element("strong", "portfolio-institution-name", title),
            element("p", "portfolio-row-meta", description)
        );
        row.append(content);
        return row;
    }

    function openInstitutionAnalysis(institutionName) {
        const owner = ArgosAnalysisContext.getActiveOwner();
        const query = new URLSearchParams({
            owner: owner.id,
            institution: institutionName
        });
        window.location.href = `/institution_analysis.html?${query.toString()}`;
    }

    function renderInstitutions(institutions) {
        const container = document.getElementById("portfolioExecutiveInstitutions");
        container.replaceChildren();
        const owner = ArgosAnalysisContext.getActiveOwner();

        if (institutions.length === 0) {
            container.append(element(
                "p",
                "portfolio-empty",
                `Nenhuma instituição de ${owner.name} foi carregada.`
            ));
            return;
        }

        const list = element("div", "portfolio-institution-list");
        institutions.forEach((institution) => {
            const button = element("button", "portfolio-institution-button");
            button.type = "button";
            button.dataset.institution = institution.name;
            const row = element("div", "portfolio-institution-row");
            const left = element("div");
            left.append(
                element("strong", "portfolio-institution-name", institution.name),
                element("p", "portfolio-row-meta", `${institution.position_count} posições · ${(institution.currencies || []).join(" · ")}`)
            );
            const right = element("span", "portfolio-status", "Abrir análise individual →");
            row.append(left, right);
            button.append(row);
            button.addEventListener("click", () => openInstitutionAnalysis(institution.name));
            list.append(button);
        });
        container.append(list);
    }

    const COMPLETED_KEY = "argos.completed-institutions";
    const CONSOLIDATION_AUTHORIZATION_KEY = "argos.consolidation-authorized";

    function normalizeInstitutionName(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim()
            .toLowerCase();
    }

    function completedInstitutionsForOwner(owner) {
        try {
            const stored = JSON.parse(
                window.localStorage.getItem(COMPLETED_KEY) || "{}"
            );
            return new Set(
                Array.isArray(stored[owner.id])
                    ? stored[owner.id].map(normalizeInstitutionName)
                    : []
            );
        } catch (_) {
            return new Set();
        }
    }

    function consolidationAuthorizationMap() {
        try {
            return JSON.parse(
                window.localStorage.getItem(
                    CONSOLIDATION_AUTHORIZATION_KEY
                ) || "{}"
            );
        } catch (_) {
            return {};
        }
    }

    function isConsolidationAuthorized(owner) {
        return Boolean(consolidationAuthorizationMap()[owner.id]);
    }

    function authorizeConsolidation(owner) {
        const stored = consolidationAuthorizationMap();
        stored[owner.id] = true;
        window.localStorage.setItem(
            CONSOLIDATION_AUTHORIZATION_KEY,
            JSON.stringify(stored)
        );
    }

    function renderConsolidationControl(institutions) {
        const button = document.getElementsByClassName
            ? document.getElementsByClassName("portfolio-consolidate-button")[0]
            : null;
        if (!button) return;

        const owner = ArgosAnalysisContext.getActiveOwner();
        const completed = completedInstitutionsForOwner(owner);

        const required = institutions
            .map((institution) => normalizeInstitutionName(institution.name));

        const allCompleted = (
            required.length > 0
            && required.every((name) => completed.has(name))
        );

        const authorized = isConsolidationAuthorized(owner);

        button.disabled = !allCompleted || authorized;

        if (authorized) {
            button.textContent = "Consolidação autorizada";
            return;
        }

        button.textContent = "Consolidar carteiras";

        if (!button.dataset.consolidationBound) {
            button.dataset.consolidationBound = "true";
            button.addEventListener("click", () => {
                const activeOwner = ArgosAnalysisContext.getActiveOwner();
                const currentInstitutions = ownerInstitutions();
                const currentCompleted = completedInstitutionsForOwner(
                    activeOwner
                );
                const currentRequired = currentInstitutions.map(
                    (institution) =>
                        normalizeInstitutionName(institution.name)
                );

                const canAuthorize = (
                    currentRequired.length > 0
                    && currentRequired.every(
                        (name) => currentCompleted.has(name)
                    )
                );

                if (!canAuthorize) return;

                authorizeConsolidation(activeOwner);
                render();
            });
        }
    }

    function render() {
        const institutions = ownerInstitutions();
        renderTotals(institutions);
        renderAllocation(institutions);
        renderAttention(
            institutions,
            dashboard?.consolidated?.intelligence
        );
        renderInstitutions(institutions);
        renderConsolidationControl(institutions);
        const owner = ArgosAnalysisContext.getActiveOwner();
        const ownerName = document.getElementById("portfolioOwnerName");
        if (ownerName) {
            ownerName.textContent = owner.name;
        }
    }

    async function load() {
        try {
            const response = await fetch("/api/dashboard", { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`Erro HTTP ${response.status}`);
            }
            dashboard = await response.json();
            render();
        } catch (error) {
            console.error("Portfolio executive failed", error);
            [
                "portfolioExecutiveTotals",
                "portfolioExecutiveAllocation",
                "portfolioExecutiveAttention",
                "portfolioExecutiveInstitutions"
            ].forEach((id) => {
                const container = document.getElementById(id);
                if (container) {
                    container.replaceChildren(element(
                        "p",
                        "portfolio-empty",
                        "Não foi possível carregar os dados patrimoniais."
                    ));
                }
            });
        }
    }

    function setupImportDrawer() {
        const toggle = document.getElementById("portfolioImportToggle");
        const drawer = document.getElementById("portfolioImportDrawer");
        if (toggle && drawer) {
            toggle.addEventListener("click", () => {
                drawer.hidden = !drawer.hidden;
                toggle.textContent = drawer.hidden ? "Importar carteiras" : "Fechar importação";
            });
        }

        const progressText = document.getElementById("importProgressText");
        if (progressText) {
            new MutationObserver(() => {
                if (progressText.textContent.includes("concluída")) {
                    load();
                }
            }).observe(progressText, { childList: true, subtree: true, characterData: true });
        }
    }

    function setup() {
        setupImportDrawer();
        window.addEventListener("argos:owner-change", render);
        load();
    }

    return Object.freeze({ setup, load, render });
})();

document.addEventListener("DOMContentLoaded", PortfolioExecutive.setup);
