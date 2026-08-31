import test from "node:test";
import assert from "node:assert/strict";
import disputes from "../data/disputes.json" with { type: "json" };
import { draftResponse, evaluateDisputes, scoreDispute, verifyEvidence } from "../lib/engine.js";

test("ready_to_submit is assigned to strong evidence disputes", () => {
  const result = scoreDispute(disputes[0]);
  assert.equal(result.decision, "ready_to_submit");
  assert.ok(result.winProbability >= 0.72);
});

test("evidence verifier flags missing delivery proof", () => {
  const verification = verifyEvidence(disputes[2]);
  assert.ok(verification.missingItems.includes("Proof of delivery"));
  assert.equal(verification.sufficient, false);
});

test("draft response includes actionable recommendation", () => {
  const draft = draftResponse(disputes[1]);
  assert.match(draft.draftText, /Recommended action:/);
  assert.ok(draft.submissionChecklist.length > 0);
});

test("held-out evaluation returns bounded metrics", () => {
  const metrics = evaluateDisputes(disputes.slice(-3));
  assert.ok(metrics.precision >= 0 && metrics.precision <= 1);
  assert.ok(metrics.recall >= 0 && metrics.recall <= 1);
  assert.ok(metrics.falsePositiveCost >= 0);
});
