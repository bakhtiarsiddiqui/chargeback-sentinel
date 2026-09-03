const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0
});

let selectedId = null;
let currentDisputePayload = null;

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
  return (decision || "").replaceAll("_", " ");
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

function renderAgentTimeline(auditTrail = []) {
  const container = document.getElementById("agent-timeline");
  if (!auditTrail || !auditTrail.length) {
    container.innerHTML = "<div class='empty-timeline'>No agent execution events logged.</div>";
    return;
  }

  container.innerHTML = auditTrail
    .map((step) => {
      const statusIcon = step.status === "success" ? "✅" : step.status === "warning" ? "⚠️" : "ℹ️";
      const timestampStr = step.timestamp ? new Date(step.timestamp).toLocaleTimeString() : "";
      const agentTitle = typeof step === "string" ? step : step.agent;
      const summaryText = typeof step === "string" ? "" : step.summary || "";
      const rawOutputJson = typeof step === "object" && step.output ? JSON.stringify(step.output, null, 2) : "";

      return `
        <div class="timeline-step ${step.status || 'info'}">
          <div class="step-header">
            <span class="step-icon">${statusIcon}</span>
            <strong class="agent-name">${agentTitle}</strong>
            <span class="step-time">${timestampStr}</span>
          </div>
          ${summaryText ? `<p class="step-summary">${summaryText}</p>` : ""}
          ${
            rawOutputJson
              ? `<details class="step-details"><summary>View Raw Agent Output</summary><pre>${rawOutputJson}</pre></details>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

async function runMultiAgentPipeline() {
  if (!currentDisputePayload) return;

  const btn = document.getElementById("run-pipeline-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Running Pipeline...";

  try {
    const response = await fetch("/api/case/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...currentDisputePayload, mode: "assistive" })
    });

    if (!response.ok) {
      throw new Error("Multi-Agent Orchestrator request failed");
    }

    const result = await response.json();
    const { mlScoring, heuristicScoring, evidence, draft, auditTrail, requiresHumanApproval } = result;

    // Update Win Probability with live ML model result
    const winProb = mlScoring.winProbability !== undefined ? mlScoring.winProbability : heuristicScoring.winProbability;
    document.getElementById("win-probability").textContent = `${Math.round(winProb * 100)}%`;

    const modelBadge = document.getElementById("ml-model-badge");
    if (mlScoring.modelType) {
      modelBadge.textContent = mlScoring.modelType;
      modelBadge.className = mlScoring.error ? "sub-tag warning-tag" : "sub-tag success-tag";
    }

    // Toggle Human Approval Banner
    const approvalBanner = document.getElementById("human-approval-banner");
    if (requiresHumanApproval) {
      approvalBanner.classList.remove("hidden");
    } else {
      approvalBanner.classList.add("hidden");
    }

    // Update Draft & Verification lists
    document.getElementById("draft-text").textContent = draft.draftText;
    writeList("reason-codes", heuristicScoring.reasonCodes, "No reason codes available.");
    writeList("missing-items", evidence.missingItems, "Evidence packet is complete.");
    writeList("risk-flags", evidence.riskFlags, "No major risk flags detected.");
    writeList("citations", draft.citations, "No citations available.");
    writeList("submission-checklist", draft.submissionChecklist, "No checklist items.");

    // Render step-by-step Multi-Agent Audit Timeline
    renderAgentTimeline(auditTrail);
  } catch (error) {
    console.error("Pipeline Error:", error);
    setStatus("Failed to execute Multi-Agent Pipeline. Make sure the API server and ML service are running.");
  } finally {
    btn.disabled = false;
    btn.textContent = "⚡ Run Multi-Agent Pipeline";
  }
}

async function loadDetail(id) {
  const response = await fetch(`/api/disputes/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to load dispute ${id}`);
  }
  const payload = await response.json();
  const { dispute, verification, scoring, draft, auditTrail } = payload;
  currentDisputePayload = dispute;

  document.getElementById("detail-empty").classList.add("hidden");
  document.getElementById("detail-content").classList.remove("hidden");
  document.getElementById("detail-title").textContent = `${dispute.merchantName} • ${dispute.id}`;
  document.getElementById("human-approval-banner").classList.add("hidden");

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

  renderAgentTimeline(auditTrail);
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

    document.getElementById("run-pipeline-btn").addEventListener("click", runMultiAgentPipeline);
  } catch (error) {
    console.error(error);
    setStatus(
      "The dashboard could not reach the local API. Start the server with `npm start` and refresh the page."
    );
  }
}

boot();
