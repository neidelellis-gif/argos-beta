"use strict";

const AnalysisStart = (() => {
    let dashboard = null;
    let selectedMethod = null;
    let selectedOwner = null;

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

    function institutionDataFor(owner) {
        const allowed = new Set(owner.institutions.map(normalize));
        return Array.isArray(dashboard?.institutions)
            ? dashboard.institutions.filter((item) => allowed.has(normalize(item.name)))
            : [];
    }

    function renderPreviousStatus() {
        const institutions = Array.isArray(dashboard?.institutions) ? dashboard.institutions : [];
        const status = $("previousPortfolioStatus");
        const summary = $("previousPortfolioSummary");
        const button = $("usePreviousPortfolio");

        if (!institutions.length) {
            status.textContent = "Nenhuma carteira anterior foi encontrada.";
            summary.textContent = "Escolha colar ou anexar uma carteira atualizada.";
            button.disabled = true;
            return;
        }

        const positions = institutions.reduce((total, item) => total + Number(item.position_count || 0), 0);
        status.textContent = `${institutions.length} instituições · ${positions} posições disponíveis`;
        summary.textContent = `O ARGOS encontrou ${institutions.length} instituições na última posição registrada.`;
        button.disabled = false;
    }

    function selectMethod(method) {
        selectedMethod = method;
        document.querySelectorAll(".analysis-method").forEach((button) => {
            button.classList.toggle("active", button.dataset.method === method);
        });

        $("methodPanel").hidden = false;
        ["previous", "paste", "upload"].forEach((name) => {
            $(`${name}Panel`).hidden = name !== method;
        });
        $("ownerStage").hidden = true;
        $("institutionStage").hidden = true;
    }

    function renderOwners() {
        const container = $("ownerOptions");
        const owners = ArgosAnalysisContext.getOwners();
        container.replaceChildren();

        owners.forEach((owner) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "analysis-owner-option";
            const available = institutionDataFor(owner).length;
            button.innerHTML = `<strong>${owner.name}</strong><small>${available} ${available === 1 ? "instituição disponível" : "instituições disponíveis"}</small>`;
            button.addEventListener("click", () => selectOwner(owner, button));
            container.appendChild(button);
        });

        $("ownerStage").hidden = false;
        $("ownerStage").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function selectOwner(owner, button) {
        selectedOwner = owner;
        ArgosAnalysisContext.setActiveOwner(owner.id);
        document.querySelectorAll(".analysis-owner-option").forEach((item) => {
            item.classList.toggle("active", item === button);
        });
        renderInstitutions();
    }

    function renderInstitutions() {
        const list = $("institutionList");
        list.replaceChildren();
        const available = institutionDataFor(selectedOwner);
        const names = selectedMethod === "previous" && available.length
            ? available.map((item) => ({ name: item.name, detail: `${item.position_count || 0} posições` }))
            : selectedOwner.institutions.map((name) => ({ name, detail: "A confirmar após a leitura da carteira" }));

        names.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "analysis-institution-row";
            row.innerHTML = `<strong>${String(index + 1).padStart(2, "0")} · ${item.name}</strong><span>${item.detail}</span>`;
            list.appendChild(row);
        });

        $("institutionStage").hidden = false;
        $("institutionStage").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function continueToOwners() {
        renderOwners();
    }

    function setupMethods() {
        document.querySelectorAll(".analysis-method").forEach((button) => {
            button.addEventListener("click", () => selectMethod(button.dataset.method));
        });

        $("usePreviousPortfolio").addEventListener("click", continueToOwners);

        const paste = $("portfolioPaste");
        paste.addEventListener("input", () => {
            $("usePastedPortfolio").disabled = paste.value.trim().length < 10;
        });
        $("usePastedPortfolio").addEventListener("click", continueToOwners);

        const files = $("analysisFiles");
        files.addEventListener("change", () => {
            const names = Array.from(files.files || []).map((file) => file.name);
            $("analysisFileStatus").textContent = names.length
                ? `${names.length} ${names.length === 1 ? "arquivo selecionado" : "arquivos selecionados"}: ${names.join(" · ")}`
                : "Nenhum arquivo selecionado.";
            $("useUploadedPortfolio").disabled = names.length === 0;
        });
        $("useUploadedPortfolio").addEventListener("click", continueToOwners);

        $("startIndividualAnalysis").addEventListener("click", () => {
            const owner = selectedOwner ? selectedOwner.name : "titular selecionado";
            window.alert(`A preparação foi concluída para ${owner}. A análise individual por instituição será implementada na Sprint 3.`);
        });
    }

    async function loadDashboard() {
        try {
            const response = await fetch("/api/dashboard", { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`Erro HTTP ${response.status}`);
            }
            dashboard = await response.json();
        } catch (error) {
            console.error("Analysis start dashboard load failed", error);
            dashboard = { institutions: [] };
        }
        renderPreviousStatus();
    }

    function setup() {
        setupMethods();
        loadDashboard();
    }

    return Object.freeze({ setup });
})();

document.addEventListener("DOMContentLoaded", AnalysisStart.setup);
