/**
 * Multi-Agent Orchestrator (src/engine/orchestrator.js)
 * ------------------------------------------------------
 * Coordinates specialized agents across pre-transaction risk scoring,
 * evidence verification, live ML win-probability inference, and defense narrative drafting.
 */

import { verifyEvidence, scoreDispute, draftResponse, normalizeDispute } from "./engine.js";
import { assessTransactionRisk } from "./transactionRiskAgent.js";
import { toMlFeatures } from "./mlAdapter.js";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL || "http://127.0.0.1:8000";

export async function runCasePipeline(rawDispute, { mode = "assistive" } = {}) {
  const trace = [];
  const dispute = normalizeDispute(rawDispute);

  // Agent 1: Pre-Transaction Risk Agent
  const txnRisk = assessTransactionRisk(dispute);
  trace.push({
    agent: "TransactionRiskAgent",
    status: txnRisk.riskScore >= 0.6 ? "warning" : "success",
    output: txnRisk,
    summary: `Assessed pre-txn risk score ${txnRisk.riskScore} (${txnRisk.decision}).`,
    timestamp: new Date().toISOString()
  });

  // Agent 2: Evidence Verification Agent
  const evidence = verifyEvidence(dispute);
  trace.push({
    agent: "EvidenceVerificationAgent",
    status: evidence.sufficient ? "success" : "warning",
    output: evidence,
    summary: `Evidence completeness score ${evidence.completenessScore} (${evidence.missingItems.length} missing).`,
    timestamp: new Date().toISOString()
  });

  // Agent 3: Dispute Win Probability Agent (HTTP call to Python FastAPI ML microservice)
  let mlScoring;
  try {
    const features = toMlFeatures({ ...dispute, _evidenceCompletenessScore: evidence.completenessScore });
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
    // Fallback gracefully to JS heuristic engine if ML microservice is unreachable
    const heuristic = scoreDispute(dispute);
    mlScoring = {
      agent: "DisputeWinProbabilityAgent",
      winProbability: heuristic.winProbability,
      modelType: "Heuristic Engine (Fallback)",
      error: "ML service unreachable, using fallback heuristic",
      dataNotice: "Fallback mode active"
    };
    trace.push({
      agent: "DisputeWinProbabilityAgent",
      status: "warning",
      output: mlScoring,
      summary: `ML microservice offline — fallback heuristic estimated win probability ${Math.round(heuristic.winProbability * 100)}%.`,
      timestamp: new Date().toISOString()
    });
  }

  // Agent 4: Response Narrative Agent
  const draft = draftResponse(dispute, evidence);
  trace.push({
    agent: "ResponseNarrativeAgent",
    status: "success",
    output: draft,
    summary: "Generated merchant defense narrative & submission checklist.",
    timestamp: new Date().toISOString()
  });

  // Heuristic decision logic for recovery calculations
  const heuristicScoring = scoreDispute(dispute);

  // Governance Policy: Assistive mode flags cases for human analyst review if high-value or low win-confidence
  const requiresHumanApproval =
    mode === "assistive" && (dispute.amount >= 5000 || (mlScoring.winProbability ?? 1) < 0.60);

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
