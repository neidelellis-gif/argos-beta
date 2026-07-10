const state = { result: null, showValues: false };

const byId = (id) => document.getElementById(id);

function showScreen(name) {
  ["homeScreen", "jolikaScreen", "neiScreen"].forEach((id) => {
    byId(id).classList.add("hidden");
  });
  byId(name).classList.remove("hidden");
}

function formatMoney(value) {
  if (!state.showValues) return "••••••";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD"
  }).format(value);
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(new Error(`Não foi possível ler ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

function setAiMessage(title, html) {
  byId("aiTitle").textContent = title;
  byId("argosResponse").innerHTML = html;
}

function setFileName(inputId, outputId) {
  const input = byId(inputId);
  const output = byId(outputId);

  input.addEventListener("change", () => {
    const file = input.files[0];
    output.textContent = file ? file.name : "Nenhum arquivo selecionado";
  });
}

function renderResult(result) {
  state.result = result;
  byId("resultsSection").classList.remove("hidden");
  byId("toggleValues").classList.remove("hidden");

  const aiItems = state.showValues
    ? [
        `Total consolidado: ${formatMoney(result.totals["Total consolidado"])}`,
        `UBS: ${formatMoney(result.totals["Total UBS"])}`,
        `Santander: ${formatMoney(result.totals["Total Santander"])}`,
      ]
    : [
        "UBS e Santander carregados com sucesso.",
      ];

  const aiText = aiItems.map((item) => `<li class="ai-item">${item}</li>`).join("");

  setAiMessage(
    result.argos_ai.title,
    `<ul class="ai-list">${aiText}</ul>
     <div class="next-action">
       <strong>Próxima ação</strong><br>
       ${result.argos_ai.next_action}
     </div>`
  );

  byId("totals").innerHTML = Object.entries(result.totals)
    .map(([label, value]) => `
      <div class="total-card">
        <div class="total-label">${label}</div>
        <div class="money-value ${state.showValues ? "" : "masked"}">
          ${formatMoney(value)}
        </div>
      </div>
    `)
    .join("");

  byId("topPositions").innerHTML = renderTopHoldings(result.top_positions);
}

function renderHoldingsValue(value) {
  return state.showValues
    ? formatMoney(value)
    : "••••••";
}

function renderAssetName(position) {
  const symbol = position.symbol || "";
  const name = position.name || "";
  const hasDistinctName = !!name && name.trim().toUpperCase() !== symbol.trim().toUpperCase();

  return `
    <div class="asset-cell">
      <strong class="position-symbol">${symbol}</strong>
      ${hasDistinctName ? `<span class="position-name">${name}</span>` : ""}
    </div>
  `;
}

function renderTopHoldings(positions) {
  const institutionNames = ["UBS", "Santander"];

  return `
    <div class="top-table">
      <div class="top-table-row top-table-header">
        <div class="top-table-cell top-table-heading">Ativo</div>
        ${institutionNames
          .map(
            (name) => `<div class="top-table-cell top-table-heading">${name}</div>`
          )
          .join("")}
        <div class="top-table-cell top-table-heading">Consolidado</div>
      </div>
      ${positions
        .sort((a, b) => b.total_value - a.total_value)
        .map((position) => {
          const institutionMap = new Map(
            (position.institutions || []).map((institution) => [institution.name, institution])
          );

          const institutionCells = institutionNames
            .map((institutionName) => {
              const institution = institutionMap.get(institutionName);
              const hasValue = institution && institution.value;
              const valueDisplay = hasValue
                ? renderHoldingsValue(institution.value)
                : "—";
              const percentDisplay = hasValue
                ? `${institution.weight_in_institution.toFixed(2)}%`
                : "—";

              return `
                <div class="top-table-cell">
                  <span>${valueDisplay}</span>
                  <span class="position-subtext">${percentDisplay}</span>
                </div>
              `;
            })
            .join("");

          const consolidatedValueDisplay = position.total_value
            ? renderHoldingsValue(position.total_value)
            : "—";

          return `
            <div class="top-table-row" data-symbol="${position.symbol}">
              <div class="top-table-cell">
                ${renderAssetName(position)}
              </div>
              ${institutionCells}
              <div class="top-table-cell">
                <span>${consolidatedValueDisplay}</span>
                <span class="position-subtext">${position.weight.toFixed(2)}%</span>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

async function analyzeJolika() {
  const ubs = byId("ubsFile").files[0];
  const santander = byId("santanderFile").files[0];

  if (!ubs || !santander) {
    setAiMessage(
      "Arquivos necessários",
      "<p class='error-message'>Selecione os arquivos da UBS e do Santander.</p>"
    );
    return;
  }

  const button = byId("analyzeJolika");
  button.disabled = true;
  button.textContent = "ANALISANDO...";

  setAiMessage(
    "Análise em andamento",
    "<p>Lendo as carteiras e consolidando a Jolika.</p>"
  );

  try {
    const payload = {
      portfolio: "JOLIKA",
      files: {
        ubs: {
          name: ubs.name,
          content: await fileToBase64(ubs)
        },
        santander: {
          name: santander.name,
          content: await fileToBase64(santander)
        }
      }
    };

    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "A análise não pôde ser concluída.");
    }

    renderResult(data.result);
  } catch (error) {
    setAiMessage(
      "Não foi possível analisar",
      `<p class="error-message">${error.message}</p>`
    );
  } finally {
    button.disabled = false;
    button.textContent = "ANALISAR CARTEIRAS";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setFileName("ubsFile", "ubsFileName");
  setFileName("santanderFile", "santanderFileName");
  setFileName("agoraFile", "agoraFileName");
  setFileName("cryptoFile", "cryptoFileName");

  document.querySelectorAll("[data-portfolio]").forEach((button) => {
    button.addEventListener("click", () => {
      const portfolio = button.dataset.portfolio;

      showScreen(portfolio === "JOLIKA" ? "jolikaScreen" : "neiScreen");

      setAiMessage(
        portfolio,
        `<p>${
          portfolio === "JOLIKA"
            ? "Selecione os arquivos UBS e Santander."
            : "Selecione os arquivos Agora e Cripto."
        }</p>`
      );
    });
  });

  document.querySelectorAll('[data-action="home"]').forEach((button) => {
    button.addEventListener("click", () => {
      showScreen("homeScreen");
      setAiMessage("Bem-vindo", "<p>Selecione um patrimônio para iniciar.</p>");
    });
  });

  byId("analyzeJolika").addEventListener("click", analyzeJolika);

  byId("analyzeNei").addEventListener("click", () => {
    setAiMessage(
      "NEI",
      "<p>A integração da carteira pessoal ainda não está ativa neste MVP.</p>"
    );
  });

  byId("toggleValues").addEventListener("click", () => {
    state.showValues = !state.showValues;
    byId("toggleValues").textContent = state.showValues
      ? "🙈 Ocultar valores"
      : "👁 Mostrar valores";

    if (state.result) renderResult(state.result);
  });
});
