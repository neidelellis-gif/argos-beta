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

  const items = result.argos_ai.items
    .map((item) => `<li class="ai-item">${item}</li>`)
    .join("");

  setAiMessage(
    result.argos_ai.title,
    `<ul class="ai-list">${items}</ul>
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

  byId("topPositions").innerHTML = result.top_positions
    .map((position) => `
      <div class="position-row">
        <div class="position-symbol">${position.symbol}</div>
        <div class="position-weight">${position.weight.toFixed(2)}%</div>
        <div class="position-value ${state.showValues ? "" : "masked"}">
          ${formatMoney(position.total_value)}
        </div>
      </div>
    `)
    .join("");
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
