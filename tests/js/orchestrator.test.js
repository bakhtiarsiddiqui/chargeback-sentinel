import test from "node:test";
import assert from "node:assert/strict";
import disputes from "../../data/disputes.json" with { type: "json" };
import { assessTransactionRisk } from "../../src/engine/transactionRiskAgent.js";
import { toMlFeatures } from "../../src/engine/mlAdapter.js";
import { runCasePipeline, normalizeDispute } from "../../src/engine/orchestrator.js";

test("TransactionRiskAgent assesses pre-transaction risk flags correctly", () => {
  const highRiskTxn = {
    amount: 6000,
    threeDsAuthenticated: false,
    ipCountryMatch: false,
    deviceFingerprintMatch: false,
    isFirstTimeCustomer: true
  };

  const assessment = assessTransactionRisk(highRiskTxn);
  assert.equal(assessment.agent, "TransactionRiskAgent");
  assert.ok(assessment.riskScore >= 0.6);
  assert.equal(assessment.decision, "block_or_challenge");
  assert.ok(assessment.flags.length >= 3);
});

test("mlAdapter transforms dispute record into valid snake_case ML feature payload", () => {
  const sampleDispute = disputes[0];
  console.log("sampleDispute raw:", JSON.stringify(sampleDispute, null, 2));
  const normalizedDispute = normalizeDispute({ ...sampleDispute, _evidenceCompletenessScore: 0.95 });
  console.log("normalizedDispute:", JSON.stringify(normalizedDispute, null, 2));
  const features = toMlFeatures(normalizedDispute);
  console.log("features from mlAdapter:", JSON.stringify(features, null, 2));

  console.log("Checking txn_amount: ", features.txn_amount, " === ", sampleDispute.amount);
  assert.equal(features.txn_amount, sampleDispute.amount);
  
  console.log("Checking device_id_match: ", features.device_id_match, " === ", Boolean(sampleDispute.deviceFingerprintMatch));
  assert.equal(features.device_id_match, Boolean(sampleDispute.deviceFingerprintMatch));
  
  console.log("Checking three_ds_authenticated: ", features.three_ds_authenticated, " === ", Boolean(sampleDispute.threeDsAuthenticated));
  assert.equal(features.three_ds_authenticated, Boolean(sampleDispute.threeDsAuthenticated));
  
  console.log("Checking completeness_score: ", features.completeness_score, " === 0.95");
  assert.equal(features.completeness_score, 0.95);
});

test("OrchestratorAgent executes 4-agent pipeline with graceful fallback if ML service offline", async () => {
  const result = await runCasePipeline(disputes[0], { mode: "assistive" });

  assert.equal(result.caseId, disputes[0].id);
  assert.equal(result.auditTrail.length, 4);
  assert.equal(result.transactionRisk.agent, "TransactionRiskAgent");
  assert.equal(result.evidence.sufficient, true);
  assert.equal(result.mlScoring.agent, "DisputeWinProbabilityAgent");
  assert.ok(result.mlScoring.winProbability >= 0 && result.mlScoring.winProbability <= 1);
  assert.ok(result.draft.draftText.includes("We respectfully contest dispute"));
});

test("OrchestratorAgent sets requiresHumanApproval for high value disputes in assistive mode", async () => {
  const highValueDispute = { ...disputes[0], amount: 7500 };
  const result = await runCasePipeline(highValueDispute, { mode: "assistive" });

  assert.equal(result.requiresHumanApproval, true);
});
