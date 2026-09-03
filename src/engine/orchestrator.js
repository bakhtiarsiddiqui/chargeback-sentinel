/**
 * Multi-Agent Orchestrator (src/engine/orchestrator.js)
 * ------------------------------------------------------
 * Coordinates specialized agents across pre-transaction risk scoring,
 * evidence verification, live ML win-probability inference, and defense narrative drafting.
 */

import { verifyEvidence, scoreDispute, draftResponse, normalizeDispute, ResponseNarrativeAgent } from "./engine.js";
import { assessTransactionRisk } from "./transactionRiskAgent.js";
import { toMlFeatures } from "./mlAdapter.js";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL || "http://127.0.0.1:8000";

function applyMlProbabilityToDraft(draft, winProbability) {
  if (typeof winProbability !== "number") {
    return draft;
  }

  const mlSentence = `Our review indicates a ${Math.round(winProbability * 100)}% contest success likelihood (ML-scored) based on merchant-side fulfillment and customer evidence.`;
  return {
    ...draft,
    draftText: draft.draftText.replace(
      /Our review indicates a \d+% contest success likelihood based on merchant-side fulfillment and customer evidence\./,
      mlSentence
    )
  };
}

export async function runCasePipeline(rawDispute, { mode = "assistive" } = {}) {
  const trace = [];
  const dispute = normalizeDispute(rawDispute);

  const txnRisk = assessTransactionRisk(dispute);
  trace.push({
    agent: "TransactionRiskAgent",
    status: txnRisk.riskScore >= 0.6 ? "warning" : "success",
    output: txnRisk,
    summary: `Assessed pre-txn risk score ${txnRisk.riskScore} (${txnRisk.decision}).`,
    timestamp: new Date().toISOString()
  });

  const evidence = verifyEvidence(dispute);
  trace.push({
    agent: "EvidenceVerificationAgent",
    status: evidence.sufficient ? "success" : "warning",
    output: evidence,
    summary: `Evidence completeness score ${evidence.completenessScore} (${evidence.missingItems.length} missing).`,
    timestamp: new Date().toISOString()
  });

  let mlScoring;
  try {
    const features = toMlFeatures(dispute);
    const response = await fetch(`${ML_SERVICE_URL}/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(features)
    });

    if (!response.ok) {
      throw new Error(`ML microservice HTTP error ${response.status}`);
    }

    mlScoring = await response.json();
    trace.push({
      agent: "DisputeWinProbabilityAgent",
      status: "success",
      output: mlScoring,
      summary: `Computed ML win probability ${Math.round(mlScoring.winProbability * 100)}% via scikit-learn model.`,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    mlScoring = {
      agent: "DisputeWinProbabilityAgent",
      winProbability: null,
      modelType: null,
      error: "ML agent unreachable, no fallback score computed",
      detail: String(error.message || error)
    };
    trace.push({
      agent: "DisputeWinProbabilityAgent",
      status: "warning",
      output: mlScoring,
      summary: "ML microservice offline — no win probability substituted from the heuristic engine.",
      timestamp: new Date().toISOString()
    });
  }

  const narrativeAgent = new ResponseNarrativeAgent();
  const winProbability = typeof mlScoring.winProbability === "number" ? mlScoring.winProbability : null;
  let draft = await narrativeAgent.generateDraft(dispute, evidence, mlScoring);
  trace.push({
    agent: "ResponseNarrativeAgent",
    status: "success",
    output: draft,
    summary: winProbability === null
      ? "Generated merchant defense narrative (heuristic likelihood left in draft; ML score unavailable)."
      : "Generated merchant defense narrative using ML-scored win probability.",
    timestamp: new Date().toISOString()
  });

  const heuristicScoring = scoreDispute(dispute);
  const requiresHumanApproval =
    mode === "assistive" && (dispute.amount >= 5000 || winProbability === null || winProbability < 0.6);

  return {
    caseId: dispute.id,
    mode,
    requiresHumanApproval,
    transactionRisk: txnRisk,
    evidence,
    mlScoring,
    heuristicScoring,
    draft,
    auditTrail: trace
  };
}
