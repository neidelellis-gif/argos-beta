"use strict";

const InstitutionAnalysis = (() => {
    const COMPLETED_KEY = "argos.completed-institutions";
    const IMPORT_STATUS_KEY = "argos.institution-import-status";
    const INVESTOR_PROFILE_KEY = "argos.investor-profile";
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

    function importStatusMap() {
        try {
            return JSON.parse(window.localStorage.getItem(IMPORT_STATUS_KEY) || "{}");
        } catch (_) {
            return {};
        }
    }

    function importStatusFor(institution) {
        const status = importStatusMap()[normalize(institution?.name)];
        return status && status.status !== "success" ? status : null;
    }

    function applyImportStatus(institution) {
        const status = importStatusFor(institution);
        return status ? { ...institution, import_status: status } : institution;
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

    function warningTexts(institution) {
        return Array.isArray(institution.warnings) ? institution.warnings.map(String) : [];
    }

    function isImportIncomplete(institution) {
        const positions = Number(institution?.position_count || 0);
        const totals = Object.entries(institution?.totals_by_currency || {});
        const warnings = warningTexts(institution || {}).map(normalize);
        return Boolean(institution?.import_status)
            || positions <= 0
            || !totals.length
            || warnings.some((warning) => (
                warning.includes("ainda nao carregada")
                || warning.includes("incomplet")
                || warning.includes("insuficient")
            ));
    }

    function dailyFacts() {
        return Array.isArray(dashboard?.daily?.important_facts)
            ? dashboard.daily.important_facts
            : [];
    }

    function dailyAnalyses() {
        return Array.isArray(dashboard?.daily?.analyses)
            ? dashboard.daily.analyses
            : [];
    }

    function relevantDailyItems(institution) {
        const name = normalize(institution?.name);
        const facts = dailyFacts().filter((fact) => {
            const context = normalize(fact.context || "");
            const source = normalize(fact.source || "");
            return fact.context_type === "portfolio"
                || fact.context_type === "macro"
                || context.includes("carteira")
                || context.includes(name)
                || source.includes(name);
        });
        const analyses = dailyAnalyses().filter((analysis) => {
            const status = normalize(analysis.status || "");
            const related = normalize(analysis.related_to || "");
            return status.includes("carteira")
                || status.includes(name)
                || related.length > 0;
        });
        return { facts, analyses };
    }

    function investorProfile() {
        try {
            const stored = JSON.parse(window.localStorage.getItem(INVESTOR_PROFILE_KEY) || "null");
            return stored?.profile || null;
        } catch (_) {
            return null;
        }
    }

    function profileDescription(profile = investorProfile()) {
        if (!profile) return "perfil do investidor ainda não preenchido";
        const risk = { LOW: "baixo risco", MODERATE: "risco moderado", HIGH: "risco alto", VERY_HIGH: "risco muito alto", VERY_LOW: "risco muito baixo" }[profile.risk_level] || "risco declarado";
        const horizon = { SHORT_TERM: "curto prazo", MEDIUM_TERM: "médio prazo", LONG_TERM: "longo prazo", IMMEDIATE: "liquidez imediata", MULTI_HORIZON: "múltiplos horizontes" }[profile.investment_horizon] || "horizonte declarado";
        return `${profile.profile_name || "perfil cadastrado"}, com ${risk} e horizonte de ${horizon}`;
    }

    function sourceLabel(item) {
        if (item?.source) return `Fonte: ${item.source}.`;
        if (item?.updated_at || item?.occurred_at) return "Fonte: análise diária do ARGOS.";
        return "Evidência: diagnóstico interno da carteira.";
    }

    function firstRelevantReason(institution) {
        const { analyses, facts } = relevantDailyItems(institution);
        const analysis = analyses[0];
        if (analysis?.reason) return `${analysis.reason} ${sourceLabel(analysis)}`;
        const fact = facts[0];
        if (fact?.summary) return `${fact.summary} ${sourceLabel(fact)}`;
        const lookback = dashboard?.daily?.lookback_hours || 48;
        return `As análises em segundo plano não destacaram fato externo relevante para esta instituição nas últimas ${lookback} horas.`;
    }

    function buildHealthReport(institution) {
        const profile = investorProfile();
        const positions = Number(institution.position_count || 0);
        const currencies = Array.isArray(institution.currencies) ? institution.currencies : [];
        const warnings = warningTexts(institution);
        const incomplete = isImportIncomplete(institution);
        const { facts, analyses } = relevantDailyItems(institution);
        const hasPortfolioSignal = facts.some((fact) => fact.context_type === "portfolio" || (fact.matched_portfolio_assets || []).length)
            || analyses.some((analysis) => analysis.related_to);
        const hasHighPriority = facts.some((fact) => fact.priority === "Alta")
            || (dashboard?.daily?.priorities || []).some((priority) => priority.level === "Alta");
        const hasMacroSignal = facts.some((fact) => fact.context_type === "macro")
            || analyses.some((analysis) => normalize(analysis.status).includes("macro"));
        const repeatedAssets = Number(dashboard?.consolidated?.repeated_asset_count || 0);

        if (incomplete) {
            return {
                situation: "Dados insuficientes",
                summary: `Dados insuficientes. A carteira de ${institution.name} ainda não foi importada corretamente; o Motor de Saúde não usa dados antigos para concluir coerência, riscos ou necessidade de ação.`,
                attention: [{
                    title: "Dados insuficientes",
                    description: "Ainda não há base atual confiável para responder como está a carteira. Complete uma importação válida antes de avaliar saúde, riscos ou mudanças."
                }],
                risks: [{
                    title: "Dados insuficientes",
                    description: "O maior risco agora é operacional: decidir com informação incompleta ou antiga."
                }],
                theses: [{
                    title: "Dados insuficientes",
                    description: "Nenhuma tese deve ser avaliada enquanto a base desta instituição estiver incompleta."
                }],
                changes: [{
                    title: "O que mudou desde a última análise?",
                    description: "A mudança relevante é que esta instituição ainda não possui uma importação válida para a análise atual."
                }]
            };
        }

        if (!profile) {
            return {
                situation: "Perfil pendente",
                summary: `Perfil pendente. A carteira de ${institution.name} pode ter dados importados, mas o Motor de Saúde não conclui equilíbrio, risco ou coerência sem o Perfil do Investidor preenchido.`,
                attention: [{
                    title: "Perfil do investidor pendente",
                    description: "Preencha as quatro perguntas oficiais no primeiro acesso para liberar conclusões sobre equilíbrio, risco e coerência."
                }],
                risks: [{
                    title: "Risco não classificado",
                    description: "Sem perfil declarado, qualquer conclusão de risco seria genérica e foi bloqueada pelo Motor de Saúde."
                }],
                theses: [{
                    title: "Coerência não avaliada",
                    description: "As teses da carteira só são interpretadas depois de confrontadas com objetivo, tolerância a risco, horizonte e liquidez declarados."
                }],
                changes: [{
                    title: "O que mudou desde a última análise?",
                    description: "A pendência relevante é cadastrar o Perfil do Investidor antes da análise de saúde."
                }]
            };
        }

        const riskDescriptions = [];
        if (warnings.length) riskDescriptions.push("há pontos de qualidade da importação que precisam ser conferidos antes de qualquer conclusão fina");
        if (positions === 1) riskDescriptions.push(`a carteira está concentrada em uma única posição identificada, ponto sensível para ${profileDescription(profile)}`);
        if (positions > 30) riskDescriptions.push("a carteira está muito fragmentada e pode exigir acompanhamento excessivo");
        if (currencies.length > 1 && profile.risk_level !== "HIGH") riskDescriptions.push(`existe exposição a mais de uma moeda (${currencies.join(" e ")}), acima do que deve ser tratado com cautela para ${profileDescription(profile)}`);
        if (hasMacroSignal) riskDescriptions.push("o contexto macro apareceu nas análises de fundo e pode afetar a leitura da carteira");
        if (repeatedAssets > 0) riskDescriptions.push("há ativos repetidos em mais de uma instituição do patrimônio, o que deve ser observado na consolidação");

        const conservativeProfile = ["VERY_LOW", "LOW"].includes(profile.risk_level) || profile.capital_preservation_level === "CRITICAL";
        const liquidityMismatch = profile.liquidity_needs === "HIGH" && positions <= 1;
        const coherent = !warnings.length && positions > 1 && !hasHighPriority && !liquidityMismatch && !(conservativeProfile && currencies.length > 1);
        const actionNeeded = hasHighPriority || warnings.length || positions === 1 || liquidityMismatch || (conservativeProfile && currencies.length > 1);
        const situation = actionNeeded ? "Atenção" : hasPortfolioSignal || hasMacroSignal ? "Em observação" : "Saudável";
        const currencyText = currencies.length ? `, distribuída em ${currencies.join(" e ")}` : "";
        const summary = `${institution.name} está ${situation.toLowerCase()}: ${positions} investimentos foram identificados${currencyText}. A carteira ${coherent ? "continua coerente" : "merece revisão pontual"} com o ${profileDescription()}; ${actionNeeded ? "há pontos que pedem atenção, mas sem recomendação de compra ou venda." : "não há sinal suficiente para exigir ação imediata."}`;

        return {
            situation,
            summary,
            attention: [
                {
                    title: "Como está minha carteira?",
                    description: `${positions} investimentos foram identificados nesta instituição. A leitura considera explicitamente ${profileDescription(profile)}. ${warnings.length ? "Há ressalvas operacionais." : "A base é suficiente para um diagnóstico executivo simples."}`
                },
                {
                    title: "Ela continua coerente com meu perfil?",
                    description: coherent
                        ? `Sim, com a evidência disponível ela permanece compatível com o ${profileDescription()}.`
                        : `Parcialmente. Ela pode continuar compatível com o ${profileDescription()}, mas os pontos abaixo precisam ser acompanhados antes de uma conclusão confortável.`
                },
                {
                    title: "Preciso agir agora?",
                    description: actionNeeded
                        ? "Não há recomendação automática de compra ou venda. O que existe é necessidade de revisar os pontos marcados antes de decidir."
                        : "Não. O diagnóstico atual indica acompanhamento, sem ação imediata necessária."
                }
            ],
            risks: riskDescriptions.length ? riskDescriptions.slice(0, 4).map((description) => ({
                title: "Risco relevante",
                description: `${description}. Evidência: carteira importada e análises em segundo plano do ARGOS.`
            })) : [{
                title: "Nenhum risco dominante identificado",
                description: "As análises atuais não destacaram concentração, incoerência operacional ou evento externo dominante para esta instituição."
            }],
            theses: (analyses.length || facts.length) ? [...analyses, ...facts].slice(0, 3).map((item) => ({
                title: item.title || "Tese em observação",
                description: `${item.reason || item.summary || item.context || "Ponto acompanhado pelas análises em segundo plano."} ${sourceLabel(item)}`
            })) : [{
                title: "Nenhuma tese exige atenção imediata",
                description: "Macro, notícias, indicadores quantitativos, ativos e carteira não apontaram uma tese prioritária para esta instituição agora."
            }],
            changes: [{
                title: "O que mudou desde a última análise?",
                description: firstRelevantReason(institution)
            }]
        };
    }

    function buildSummary(institution) {
        return buildHealthReport(institution).summary;
    }

    function attentionItems(institution) {
        return buildHealthReport(institution).attention;
    }

    function riskItems(institution) {
        return buildHealthReport(institution).risks;
    }

    function favorableItems(institution) {
        return buildHealthReport(institution).theses;
    }

    function renderAllocation(institution) {
        const container = $("allocationList");
        container.replaceChildren();
        if (isImportIncomplete(institution)) {
            container.append(element("p", "institution-empty", "A distribuição será exibida somente após uma importação válida desta instituição."));
            return;
        }
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
        const institution = applyImportStatus(selectedInstitution());
        if (!institution) return;
        const done = isCompleted(institution.name);

        $("ownerLabel").textContent = `Patrimônio de ${owner.name}`;
        $("institutionName").textContent = institution.name;
        $("institutionMeta").textContent = `${owner.name} · análise individual · ${new Intl.DateTimeFormat("pt-BR").format(new Date())}`;
        $("executiveSummary").textContent = buildSummary(institution);
        const incomplete = isImportIncomplete(institution);
        $("metricValue").textContent = incomplete ? "Não disponível" : institutionValue(institution);
        $("metricPositions").textContent = incomplete ? "—" : String(institution.position_count || 0);
        $("metricCurrencies").textContent = incomplete ? "—" : (institution.currencies || []).join(" · ") || "—";
        const healthReport = buildHealthReport(institution);
        $("metricSituation").textContent = healthReport.situation;
        $("attentionCount").textContent = `${healthReport.attention.length} respostas`;

        const status = $("institutionStatus");
        status.textContent = done ? "Concluída" : "Em análise";
        status.classList.toggle("done", done);
        $("completeInstitution").textContent = incomplete ? "Complete a importação para concluir" : done ? "Ir para a próxima instituição →" : "Concluir análise desta instituição →";
        $("completeInstitution").disabled = incomplete;

        renderList("attentionList", healthReport.attention, "Nenhuma resposta prioritária foi gerada.");
        renderList("riskList", healthReport.risks, "Nenhum risco específico foi identificado com os dados disponíveis.");
        renderList("favorableList", healthReport.theses, "Nenhuma tese específica foi confirmada ainda.");
        renderList("assetList", healthReport.changes, "Nenhuma mudança relevante foi identificada desde a última análise.");
        renderAllocation(institution);
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
            if (isImportIncomplete(institution)) return;
            if (!isCompleted(institution.name)) markCompleted(institution.name);
            if (currentIndex < institutions.length - 1) {
                goToIndex(currentIndex + 1);
                return;
            }
            render();
            window.alert(`Todas as instituições de ${owner.name} foram analisadas pelo Motor de Saúde da Carteira.`);
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

    return Object.freeze({
        load,
        _test: Object.freeze({
            buildSummary,
            attentionItems,
            riskItems,
            favorableItems,
            isImportIncomplete,
            applyImportStatus,
            importStatusFor,
            investorProfile,
            profileDescription
        })
    });
})();

if (typeof module !== "undefined") {
    module.exports = { InstitutionAnalysis };
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", InstitutionAnalysis.load);
}
