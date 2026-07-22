"use strict";

const STATUS_LABELS = {
    pendente: "Pendente",
    em_construcao: "Em construção",
    pronto: "Pronto"
};

function setGreeting() {
    const greeting = document.getElementById("greeting");
    const currentDate = document.getElementById("currentDate");
    const now = new Date();
    const hour = now.getHours();

    if (hour < 12) {
        greeting.textContent = "Bom dia, Nei.";
    } else if (hour < 18) {
        greeting.textContent = "Boa tarde, Nei.";
    } else {
        greeting.textContent = "Boa noite, Nei.";
    }

    currentDate.textContent = new Intl.DateTimeFormat("pt-BR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
    }).format(now);
}

function formatUpdatedAt(value) {
    if (!value) {
        return "Não disponível";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Não disponível";
    }

    return new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    }).format(date);
}

function createExecutiveCard(item, index) {
    const article = document.createElement("article");
    article.className = "executive-card";

    const number = document.createElement("span");
    number.className = "card-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const area = document.createElement("p");
    area.className = "card-area";
    area.textContent = item.area;

    const title = document.createElement("h3");
    title.textContent = item.title;

    const summary = document.createElement("p");
    summary.className = "card-summary";
    summary.textContent = item.summary;

    const footer = document.createElement("div");
    footer.className = "card-footer";

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status;

    const action = document.createElement("span");
    action.className = "analysis-link";
    action.textContent = "Análise completa em preparação";

    footer.append(status, action);
    article.append(number, area, title, summary, footer);

    return article;
}

function createModuleCard(item) {
    const article = document.createElement("article");
    article.className = "module-card";
    article.id = item.id;

    const header = document.createElement("div");
    header.className = "module-header";

    const title = document.createElement("h3");
    title.textContent = item.title;

    const status = document.createElement("span");
    status.className = `status-badge status-${item.status}`;
    status.textContent = STATUS_LABELS[item.status] || item.status;

    const description = document.createElement("p");
    description.textContent = item.description;

    header.append(title, status);
    article.append(header, description);

    return article;
}

function renderCockpit(data) {
    const executiveCards = document.getElementById("executiveCards");
    const moduleCards = document.getElementById("moduleCards");
    const executiveCount = document.getElementById("executiveCount");
    const lastUpdate = document.getElementById("lastUpdate");

    executiveCards.innerHTML = "";
    moduleCards.innerHTML = "";

    const executiveItems = Array.isArray(data.executive) ? data.executive : [];
    const moduleItems = Array.isArray(data.sections) ? data.sections : [];

    executiveItems.forEach((item, index) => {
        executiveCards.appendChild(createExecutiveCard(item, index));
    });

    moduleItems.forEach((item) => {
        moduleCards.appendChild(createModuleCard(item));
    });

    executiveCount.textContent = `${executiveItems.length} conclusões`;
    lastUpdate.textContent = formatUpdatedAt(data.updated_at);
}

function renderError(message) {
    const executiveCards = document.getElementById("executiveCards");
    const moduleCards = document.getElementById("moduleCards");
    const lastUpdate = document.getElementById("lastUpdate");

    executiveCards.innerHTML = `<p class="error-message">${message}</p>`;
    moduleCards.innerHTML = "";
    lastUpdate.textContent = "Falha no carregamento";
}

async function loadCockpit() {
    try {
        const response = await fetch("/api/cockpit", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(`Erro HTTP ${response.status}`);
        }

        const payload = await response.json();

        if (!payload.ok || !payload.cockpit) {
            throw new Error(payload.error || "Resposta inválida do servidor.");
        }

        renderCockpit(payload.cockpit);
    } catch (error) {
        console.error(error);
        renderError("Não foi possível carregar o Cockpit Executivo.");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    setGreeting();
    loadCockpit();
});
