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

    function todayUtc() {
        const now = new Date();
        return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    }

    function isProfileValid(profile = investorProfile(), referenceDate = todayUtc()) {
        if (!profile || typeof profile !== "object") return false;
        const required = ["profile_name", "risk_level", "investment_horizon", "liquidity_needs", "capital_preservation_level", "review_date"];
        if (required.some((field) => !String(profile[field] || "").trim())) return false;
        const reviewDate = new Date(`${profile.review_date}T00:00:00Z`);
        return Number.isFinite(reviewDate.getTime()) && reviewDate >= referenceDate;
    }

    function profileDescription(profile = investorProfile()) {
        if (!profile) return "Perfil Estratégico ainda não preenchido";
        const risk = { LOW: "baixa tolerância a oscilações", MODERATE: "tolerância moderada a oscilações", HIGH: "alta tolerância a oscilações", VERY_HIGH: "tolerância muito alta a oscilações", VERY_LOW: "tolerância muito baixa a oscilações" }[profile.risk_level] || "tolerância declarada";
        const horizon = { SHORT_TERM: "curto prazo", MEDIUM_TERM: "médio prazo", LONG_TERM: "longo prazo", IMMEDIATE: "liquidez imediata", MULTI_HORIZON: "múltiplos horizontes" }[profile.investment_horizon] || "horizonte declarado";
        const liquidity = { HIGH: "alta necessidade de liquidez", MODERATE: "liquidez moderada", LOW: "baixa necessidade de liquidez" }[profile.liquidity_needs] || "liquidez declarada";
        return `${profile.profile_name || "Perfil Estratégico"}, com ${risk}, horizonte de ${horizon} e ${liquidity}`;
    }

    function sourceLabel(item) {
        if (item?.source) return `Fonte: ${item.source}. Inferência: acompanhar sem ordem de execução. Confiança: média.`;
        if (item?.updated_at || item?.occurred_at) return "Fonte: análise diária do ARGOS. Inferência: acompanhar sem ordem de execução. Confiança: média.";
        return "Evidência: carteira importada, Perfil Estratégico e indicadores internos já existentes. Inferência: acompanhar sem ordem de execução. Confiança: média.";
    }

    function firstRelevantReason(institution) {
        const { analyses, facts } = relevantDailyItems(institution);
        const analysis = analyses[0];
        if (analysis?.reason) return `Fato: ${analysis.reason} ${sourceLabel(analysis)}`;
        const fact = facts[0];
        if (fact?.summary) return `Fato: ${fact.summary} ${sourceLabel(fact)}`;
        const lookback = dashboard?.daily?.lookback_hours || 24;
        return `Fato: não há fato externo material confirmado para esta instituição nas últimas ${lookback} horas. Inferência: a conclusão depende mais da carteira importada e do perfil. Confiança: média. Evidência: boletim diário disponível no ARGOS.`;
    }

    function hasMacroData() {
        const facts = dailyFacts();
        const analyses = dailyAnalyses();
        return facts.some((fact) => fact.context_type === "macro" || normalize(fact.context).includes("macro"))
            || analyses.some((analysis) => normalize(analysis.status).includes("macro") || normalize(analysis.related_to).includes("macro"))
            || Boolean(dashboard?.daily?.market_context || dashboard?.macro || dashboard?.market_agenda);
    }

    function hasAssetData(institution) {
        const symbols = Array.isArray(institution?.asset_symbols) ? institution.asset_symbols : [];
        const { facts, analyses } = relevantDailyItems(institution || {});
        return symbols.length > 0 || analyses.length > 0 || facts.some((fact) => (fact.matched_portfolio_assets || []).length > 0);
    }

    function buildProjection(institution, profile, context) {
        const missing = [];

        if (!context.macroAvailable) {
            missing.push("cenário macroeconômico atual");
        }

        if (!context.assetAvailable) {
            missing.push("dados atuais dos ativos");
        }

        const quantitative = institution?.intelligence?.quantitative_analysis;
        const hasQuantitativeScenarios = Boolean(
            quantitative
            && quantitative.scenarios
            && quantitative.risk_metrics
        );

        if (missing.length || !hasQuantitativeScenarios) {
            const missingText = [
                ...missing,
                ...(!hasQuantitativeScenarios
                    ? ["modelagem quantitativa da carteira"]
                    : [])
            ];

            return {
                title: "Perspectiva para 12 meses",
                description:
                    `Fato: ainda faltam ${missingText.join(", ")} para uma projeção numérica robusta. ` +
                    "Inferência: o ARGOS não publica uma faixa de retorno enquanto essas bases não estiverem disponíveis. " +
                    "Confiança: alta sobre a limitação dos dados. " +
                    "Evidência: validação da carteira, dos ativos, do cenário macroeconômico e das métricas quantitativas."
            };
        }

        return {
            title: "Perspectiva para 12 meses",
            description:
                "Fato: a modelagem quantitativa necessária está disponível. " +
                "Inferência: os cenários serão apresentados a partir dos resultados calculados pelo motor quantitativo, e não por faixas predefinidas. " +
                "Confiança: condicionada à qualidade dos dados e às premissas dos cenários. " +
                "Evidência: carteira importada, dados dos ativos, cenário macroeconômico e métricas quantitativas do ARGOS."
        };
    }

    function buildHealthReport(institution) {
        const profile = investorProfile();
        const positions = Number(institution.position_count || 0);
        const currencies = Array.isArray(institution.currencies) ? institution.currencies : [];
        const warnings = warningTexts(institution);
        const incomplete = isImportIncomplete(institution);
        const { facts, analyses } = relevantDailyItems(institution);
        const macroAvailable = hasMacroData();
        const assetAvailable = hasAssetData(institution);

        if (incomplete) {
            const item = { title: "Dados insuficientes", description: "Fato: a importação da instituição está incompleta ou inconsistente. Inferência: o diagnóstico executivo fica bloqueado para evitar conclusões com dados antigos ou não confirmados. Confiança: alta. Evidência: validação da carteira importada." };
            return { situation: "Dados insuficientes", summary: `Dados insuficientes. A carteira de ${institution.name} ainda não possui importação atual confiável; por isso o ARGOS não conclui saúde, coerência, teses, projeção ou necessidade de alteração.`, attention: [item], risks: [item], theses: [item], changes: [item], projection: [item], action: [{ title: "Preciso agir agora?", description: "A carteira merece revisão mais aprofundada após uma importação válida. Não há ordem de execução nem indicação de instrumento." }], nextReview: [item] };
        }

        if (!isProfileValid(profile)) {
            const expired = profile && profile.review_date;
            const item = { title: expired ? "Perfil Estratégico vencido" : "Perfil Estratégico obrigatório", description: `${expired ? "Fato: o Perfil Estratégico passou da data de revisão anual." : "Fato: o Perfil Estratégico não está preenchido com todos os campos obrigatórios."} Inferência: sem perfil válido, não é possível avaliar equilíbrio, tolerância a oscilações, horizonte, liquidez ou representatividade patrimonial. Confiança: alta. Evidência: Perfil Estratégico salvo localmente.` };
            return { situation: "Perfil pendente", summary: `Perfil Estratégico obrigatório. A carteira de ${institution.name} tem dados importados, mas o diagnóstico fica bloqueado até o perfil estar preenchido e dentro do prazo de revisão anual.`, attention: [item], risks: [item], theses: [item], changes: [item], projection: [item], action: [{ title: "Preciso agir agora?", description: "Vale acompanhar. A próxima etapa clínica é atualizar o Perfil Estratégico antes de avaliar ajustes de carteira." }], nextReview: [item] };
        }

        const intelligence = institution.intelligence || {};
        const priority = intelligence.priority || {};
        const materiality = intelligence.materiality || {};
        const diversification = intelligence.diversification || {};
        const coverage = intelligence.coverage || {};
        const concentrations = Array.isArray(intelligence.concentration_by_currency)
            ? intelligence.concentration_by_currency
            : [];
        const duplicates = Array.isArray(intelligence.duplicate_exposures)
            ? intelligence.duplicate_exposures
            : [];

        const totalAssets = Number(
            coverage.consolidated_asset_count || positions || 0
        );
        const classifiedAssets = Number(
            coverage.assets_with_economic_class || 0
        );
        const coverageRatio = totalAssets
            ? classifiedAssets / totalAssets
            : 0;

        const strongest = concentrations.length
            ? concentrations.reduce((current, item) => (
                Number(item?.top_1_weight || 0) >
                Number(current?.top_1_weight || 0)
                    ? item
                    : current
            ), concentrations[0])
            : null;

        const strongestWeight = Number(
            strongest?.top_1_weight ||
            materiality.max_position_weight ||
            0
        );

        const duplicateCount = duplicates.filter(
            (item) => item.within_same_institution
        ).length;

        const conservative =
            ["VERY_LOW", "LOW"].includes(profile.risk_level)
            || profile.capital_preservation_level === "CRITICAL";

        const materialRisks = [];

        if (warnings.length) {
            materialRisks.push(
                "há pontos na qualidade dos dados que precisam ser conferidos"
            );
        }

        if (strongestWeight >= 0.35) {
            materialRisks.push(
                `o maior ativo representa ${(strongestWeight * 100).toFixed(1)}% da moeda mais concentrada`
            );
        } else if (strongestWeight > 0.20) {
            materialRisks.push(
                `o maior ativo representa ${(strongestWeight * 100).toFixed(1)}% da moeda mais concentrada, um peso relevante para acompanhamento`
            );
        }

        if (diversification.level === "Baixa") {
            materialRisks.push(
                "a carteira está pouco distribuída entre ativos ou classes"
            );
        } else if (diversification.level === "Média") {
            materialRisks.push(
                "a distribuição entre ativos e classes ainda apresenta alguma concentração"
            );
        }

        if (totalAssets && coverageRatio < 0.95) {
            materialRisks.push(
                `${(coverageRatio * 100).toFixed(1)}% dos ativos têm classificação econômica definida, o que limita parte da análise`
            );
        }

        if (duplicateCount) {
            materialRisks.push(
                `${duplicateCount} ${duplicateCount === 1 ? "ativo aparece" : "ativos aparecem"} mais de uma vez dentro da instituição`
            );
        }

        if (conservative && currencies.length > 1) {
            materialRisks.push(
                `a carteira tem exposição em ${currencies.length} moedas; para este perfil, o efeito cambial merece ser acompanhado`
            );
        }

        if (!macroAvailable) {
            materialRisks.push(
                "o cenário macroeconômico atual ainda não está disponível"
            );
        }

        if (!assetAvailable) {
            materialRisks.push(
                "faltam dados atuais dos ativos para aprofundar a leitura"
            );
        }

        const structuralLevel = priority.level || "Baixa";
        const situation =
            structuralLevel === "Alta"
                ? "Atenção"
                : structuralLevel === "Média"
                    ? "Em observação"
                    : "Sem alerta estrutural";

        const coherent =
            structuralLevel !== "Alta"
            && !warnings.length
            && !(conservative && currencies.length > 1);

        const actionLevel =
            structuralLevel === "Alta"
                ? "Há pontos relevantes que justificam uma análise mais aprofundada."
                : structuralLevel === "Média"
                    ? "Há pontos que merecem acompanhamento mais próximo."
                    : "Não há alerta estrutural dominante nos dados atuais.";

        const reading = intelligence.portfolio_reading
            || "A carteira foi importada, mas ainda não há uma leitura estrutural completa.";

        const health = {
            title: "Como está a carteira",
            description:
                `Leitura: ${reading} ` +
                `Fato: ${positions} investimentos importados` +
                `${currencies.length ? ` em ${currencies.join(" e ")}` : ""}. ` +
                `Inferência: ${actionLevel} ` +
                `Confiança: ${macroAvailable && assetAvailable ? "média" : "baixa"}. ` +
                "Evidência: carteira importada e métricas estruturais calculadas pelo ARGOS."
        };

        const profileItem = {
            title: "Como isso conversa com o seu perfil",
            description:
                `Fato: seu perfil está válido até ${profile.review_date} e considera ${profileDescription(profile)}. ` +
                `Inferência: ${coherent
                    ? "não há desalinhamento estrutural evidente nos dados disponíveis"
                    : "existem pontos que precisam ser considerados junto ao seu perfil antes de uma conclusão mais forte"}. ` +
                "Confiança: média. " +
                "Evidência: Perfil Estratégico e métricas da carteira importada. " +
                "Esta leitura avalia coerência e risco; não representa indicação de compra ou venda."
        };

        const risks = materialRisks.length
            ? materialRisks.slice(0, 5).map((risk) => ({
                title: "Ponto que merece atenção",
                description:
                    `Fato: ${risk}. ` +
                    "Inferência: esse ponto pode alterar o risco ou a leitura da carteira e merece entrar no aprofundamento. " +
                    "Confiança: média. " +
                    "Evidência: carteira importada e métricas estruturais calculadas pelo ARGOS."
            }))
            : [{
                title: "Pontos que merecem atenção",
                description:
                    "Fato: nenhum alerta estrutural dominante apareceu nas métricas atuais. " +
                    "Inferência: isso reduz a urgência estrutural, mas não elimina riscos de mercado, dos ativos ou do cenário econômico. " +
                    "Confiança: média. " +
                    "Evidência: carteira importada e métricas estruturais calculadas pelo ARGOS."
            }];
        const theses = assetAvailable && (analyses.length || facts.length) ? [...analyses, ...facts].slice(0, 3).map((item) => ({ title: item.title || "Tese em observação", description: `Fato: ${item.summary || item.reason || item.context || "evento acompanhado"}. Inferência: tese em observação, sem ordem de execução. Confiança: ${item.confidence || "média"}. ${sourceLabel(item)}` })) : [{ title: assetAvailable ? "Teses sem mudança material" : "Teses sem evidência suficiente", description: `${assetAvailable ? "Fato: não surgiu tese fortalecida ou enfraquecida material." : "Fato: não há dados atuais suficientes dos ativos."} Inferência: manter em observação. Confiança: ${assetAvailable ? "média" : "baixa"}. Evidência: análise individual dos ativos em segundo plano.` }];
        const projection = buildProjection(institution, profile, { macroAvailable, assetAvailable });
        return { situation, summary: `${health.description} ${actionLevel}`, attention: [health, profileItem, projection, { title: "Preciso agir agora?", description: `Fato: ${actionLevel} Inferência: sugestões, se houver, devem ser neutras e vinculadas à coerência com o perfil; não há ordem de execução nem indicação de instrumento. Confiança: média. Evidência: diagnóstico executivo atual.` }, { title: "O que está faltando?", description: `${!macroAvailable ? "Fato: falta cenário macroeconômico atual. " : ""}${!assetAvailable ? "Fato: Faltam dados atuais dos ativos. " : ""}${macroAvailable && assetAvailable ? "Fato: não há lacuna crítica evidente. Inferência: a próxima melhoria é refinar realidade de vida, liquidez e representatividade patrimonial do cliente." : "Inferência: sem essas bases, a conclusão permanece limitada."} Confiança: média. Evidência: Perfil Estratégico, carteira importada e validação de dados.` }], risks, theses, changes: [{ title: "Próxima revisão", description: `${firstRelevantReason(institution)} Próxima revisão: mudanças macro, fatos relevantes, alteração de perfil, liquidez ou concentração podem alterar a conclusão.` }], projection: [projection], action: [{ title: "Preciso agir agora?", description: actionLevel }], nextReview: [{ title: "Próxima revisão", description: "Reavaliar quando houver novos fatos das últimas 24 horas, mudança de cenário macro, alteração de perfil, vencimento anual do perfil ou inconsistência de importação." }] };
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
            window.alert(`Todas as instituições de ${owner.name} foram analisadas pelo Diagnóstico Executivo da Carteira.`);
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
            profileDescription,
            isProfileValid,
            buildHealthReport,
            setDashboardForTest(value) { dashboard = value; }
        })
    });
})();

if (typeof module !== "undefined") {
    module.exports = { InstitutionAnalysis };
}

if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", InstitutionAnalysis.load);
}
