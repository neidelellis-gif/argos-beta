"use strict";

const PortfolioExecutive = (() => {
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
            const amount = element("strong", "portfolio-total-value", formatCurrency(value, currency));
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

            if (intelligence) {
                const priority = intelligence.priority;
                if (priority) {
                    const reasonLabels = {
                        concentration: "concentração relevante",
                        coverage: "cobertura de classificação incompleta",
                        cross_institution_duplicate: "ativo presente em mais de uma instituição"
                    };
                    const reasons = (priority.reasons || [])
                        .map((reason) => reasonLabels[reason] || reason);

                    const priorityTone =
                        priority.level === "Alta"
                            ? "warning"
                            : priority.level === "Baixa"
                                ? "success"
                                : "accent";

                    list.append(attentionRow(
                        "Prioridade de análise",
                        reasons.length
                            ? `${priority.level}. Fatores: ${reasons.join(" · ")}.`
                            : `${priority.level}. Nenhum fator estrutural elevou a prioridade de análise.`,
                        priorityTone
                    ));
                }

                const materiality = intelligence.materiality;
                if (materiality) {
                    const materialityPercent =
                        Number(materiality.max_position_weight || 0) * 100;
                    const materialityTone =
                        materiality.level === "Alta"
                            ? "warning"
                            : materiality.level === "Baixa"
                                ? "success"
                                : "accent";

                    list.append(attentionRow(
                        "Materialidade estrutural",
                        materiality.driver === "concentration"
                            ? `${materiality.level}. A maior exposição representa ${materialityPercent.toFixed(1)}% da moeda analisada.`
                            : `${materiality.level}. Nenhum fator estrutural dominante foi identificado.`,
                        materialityTone
                    ));
                }

                const diversification = intelligence.diversification;
                if (diversification) {
                    const assetHhi = Number(diversification.asset_hhi || 0);
                    const classHhi = Number(diversification.class_hhi || 0);
                    const diversificationTone =
                        diversification.level === "Alta"
                            ? "success"
                            : diversification.level === "Baixa"
                                ? "warning"
                                : "accent";

                    list.append(attentionRow(
                        "Diversificação estrutural",
                        diversification.driver
                            ? `${diversification.level}. HHI por ativos: ${assetHhi.toFixed(3)} · HHI por classes: ${classHhi.toFixed(3)}.`
                            : `${diversification.level}. A distribuição estrutural não apresenta concentração relevante pelas métricas atuais.`,
                        diversificationTone
                    ));
                }

                const coverage = intelligence.coverage || {};
                const totalAssets = Number(coverage.consolidated_asset_count || 0);
                const classifiedAssets = Number(coverage.assets_with_economic_class || 0);
                const coveragePercent = totalAssets
                    ? classifiedAssets / totalAssets * 100
                    : 0;

                list.append(attentionRow(
                    "Cobertura da classificação",
                    `${coveragePercent.toFixed(1)}% dos ativos consolidados possuem classe econômica definida.`,
                    coveragePercent >= 95 ? "success" : "warning"
                ));

                const concentrations = intelligence.concentration_by_currency || [];
                if (concentrations.length) {
                    const strongest = concentrations.reduce((current, item) => {
                        const currentWeight = Number(current?.top_1_weight || 0);
                        const itemWeight = Number(item?.top_1_weight || 0);
                        return itemWeight > currentWeight ? item : current;
                    }, concentrations[0]);

                    const strongestPercent = Number(strongest.top_1_weight || 0) * 100;
                    list.append(attentionRow(
                        "Maior concentração individual",
                        `${strongest.currency}: ${strongestPercent.toFixed(1)}% no maior ativo.`,
                        strongestPercent >= 25 ? "warning" : "success"
                    ));
                }

                const crossInstitutionDuplicates = (intelligence.duplicate_exposures || [])
                    .filter((item) => item.across_institutions).length;

                list.append(attentionRow(
                    "Duplicidades entre instituições",
                    crossInstitutionDuplicates
                        ? `${crossInstitutionDuplicates} ${crossInstitutionDuplicates === 1 ? "ativo aparece" : "ativos aparecem"} em mais de uma instituição.`
                        : "Nenhuma duplicidade entre instituições foi identificada.",
                    crossInstitutionDuplicates ? "warning" : "success"
                ));
            }

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

    function render() {
        const institutions = ownerInstitutions();
        renderTotals(institutions);
        renderAllocation(institutions);
        renderAttention(
            institutions,
            dashboard?.consolidated?.intelligence
        );
        renderInstitutions(institutions);
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
