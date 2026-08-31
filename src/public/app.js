const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0
});

let selectedId = null;

function setStatus(message = "") {
  const banner = document.getElementById("app-status");
  if (!message) {
    banner.textContent = "";
    banner.classList.add("hidden");
    return;
  }

  banner.textContent = message;
  banner.classList.remove("hidden");
}

function formatDecision(decision) {
  return decision.replaceAll("_", " ");
}

function decisionClass(decision) {
  return decision || "needs_more_evidence";
}

function renderMetrics({ metrics, baseline }) {
  const cards = [
    {
      label: "Precision",
      value: `${Math.round(metrics.precision * 100)}%`,
      note: "Held-out contest recommendations that were actually worth contesting."
    },
    {
      label: "Recall",
      value: `${Math.round(metrics.recall * 100)}%`,
      note: "Held-out recoverable disputes the system successfully identified."
    },
    {
      label: "Expected Value",
      value: currency.format(metrics.expectedValueRecovered),
      note: "Estimated recoverable value from recommended contests."
    },
    {
      label: "False-Positive Cost",
      value: currency.format(metrics.falsePositiveCost),
      note: `Versus contest-all baseline ${currency.format(baseline.falsePositiveCost)}.`
    }
  ];

  document.getElementById("metrics-grid").innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card">
          <p class="mini-label">${card.label}</p>
          <strong>${card.value}</strong>
          <p>${card.note}</p>
        </article>
      `
    )
    .join("");
}

function renderQueue(queue) {
  const container = document.getElementById("queue");
  container.innerHTML = queue
    .map((item) => {
      const active = item.id === selectedId ? "active" : "";
      return `
        <button class="queue-item ${active}" data-id="${item.id}">
          <div class="queue-top">
            <span class="pill ${decisionClass(item.scoring.decision)}">${formatDecision(item.scoring.decision)}</span>
            <span>${currency.format(item.amount)}</span>
          </div>
          <h3>${item.merchantName} • ${item.id}</h3>
          <div class="queue-meta">
            <span>${item.disputeType.replaceAll("_", " ")}</span>
            <span>${Math.round(item.scoring.winProbability * 100)}% win probability</span>
            <span>${currency.format(item.scoring.expectedRecovery)} expected recovery</span>
          </div>
        </button>
      `;
    })
    .join("");

  container.querySelectorAll(".queue-item").forEach((button) => {
    button.addEventListener("click", () => {
      selectedId = button.dataset.id;
      renderQueue(queue);
      loadDetail(selectedId);
    });
  });
}

function writeList(id, items, emptyLabel) {
  const target = document.getElementById(id);
  const list = items.length ? items : [emptyLabel];
  target.innerHTML = list.map((item) => `<li>${item}</li>`).join("");
}

async function loadDetail(id) {
  const response = await fetch(`/api/disputes/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to load dispute ${id}`);
  }
  const payload = await response.json();
  const { dispute, verification, scoring, draft, auditTrail } = payload;

  document.getElementById("detail-empty").classList.add("hidden");
  document.getElementById("detail-content").classList.remove("hidden");
  document.getElementById("detail-title").textContent = `${dispute.merchantName} • ${dispute.id}`;

  const badge = document.getElementById("decision-badge");
  badge.textContent = formatDecision(scoring.decision);
  badge.className = `decision-badge ${decisionClass(scoring.decision)}`;

  document.getElementById("win-probability").textContent = `${Math.round(scoring.winProbability * 100)}%`;
  document.getElementById("expected-recovery").textContent = currency.format(scoring.expectedRecovery);
  document.getElementById("contest-cost").textContent = currency.format(scoring.contestCost);
  document.getElementById("draft-text").textContent = draft.draftText;

  writeList("reason-codes", scoring.reasonCodes, "No reason codes available.");
  writeList("missing-items", verification.missingItems, "Evidence packet is complete.");
  writeList("risk-flags", verification.riskFlags, "No major risk flags detected.");
  writeList("citations", draft.citations, "No citations available.");
  writeList("submission-checklist", draft.submissionChecklist, "No checklist items.");
  writeList("audit-trail", auditTrail, "No audit events.");
}

async function boot() {
  try {
    setStatus("");
    const [queueResponse, metricsResponse] = await Promise.all([
      fetch("/api/disputes"),
      fetch("/api/metrics")
    ]);

    if (!queueResponse.ok || !metricsResponse.ok) {
      throw new Error("API failed to load");
    }

    const [{ queue }, metricsPayload] = await Promise.all([
      queueResponse.json(),
      metricsResponse.json()
    ]);

    renderMetrics(metricsPayload);
    selectedId = queue[0]?.id || null;
    renderQueue(queue);
    if (selectedId) {
      await loadDetail(selectedId);
    }
  } catch (error) {
    console.error(error);
    setStatus(
      "The dashboard could not reach the local API. Start the server with `npm start` and refresh the page."
    );
  }
}

boot();
