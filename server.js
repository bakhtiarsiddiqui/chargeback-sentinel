import express from "express";
import disputes from "./data/disputes.json" with { type: "json" };
import {
  draftResponse,
  evaluateDisputes,
  normalizeDispute,
  scoreDispute,
  verifyEvidence
} from "./lib/engine.js";

const app = express();
const port = process.env.PORT || 3000;
const host = process.env.HOST || "127.0.0.1";

const normalizedDisputes = disputes.map(normalizeDispute);
const heldOutDisputes = normalizedDisputes.slice(-3);
const queueDisputes = normalizedDisputes.slice(0, 3);

app.use(express.json());
app.use(express.static("public"));

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "ai-chargeback-risk-manager",
    date: new Date().toISOString()
  });
});

app.get("/api/disputes", (_req, res) => {
  const queue = queueDisputes.map((dispute) => {
    const scoring = scoreDispute(dispute);
    return {
      ...dispute,
      scoring
    };
  });
  res.json({ queue });
});

app.get("/api/metrics", (_req, res) => {
  const metrics = evaluateDisputes(heldOutDisputes);
  const contestAllFalsePositiveCost = heldOutDisputes
    .filter((dispute) => dispute.outcome !== "won")
    .reduce((sum, dispute) => sum + 150 + dispute.analystReviewMinutes * 8, 0);

  res.json({
    metrics,
    baseline: {
      strategy: "contest_all",
      falsePositiveCost: Math.round(contestAllFalsePositiveCost * 100) / 100
    }
  });
});

app.post("/score-dispute", (req, res) => {
  const dispute = normalizeDispute(req.body);
  res.json(scoreDispute(dispute));
});

app.post("/verify-evidence", (req, res) => {
  const dispute = normalizeDispute(req.body);
  res.json(verifyEvidence(dispute));
});

app.post("/draft-response", (req, res) => {
  const dispute = normalizeDispute(req.body);
  const verification = verifyEvidence(dispute);
  res.json(draftResponse(dispute, verification));
});

app.get("/api/disputes/:id", (req, res) => {
  const dispute = normalizedDisputes.find((item) => item.id === req.params.id);
  if (!dispute) {
    res.status(404).json({ error: "Dispute not found" });
    return;
  }

  const verification = verifyEvidence(dispute);
  const scoring = scoreDispute(dispute);
  const draft = draftResponse(dispute, verification);

  res.json({
    dispute,
    verification,
    scoring,
    draft,
    auditTrail: [
      "Ingested merchant order and payment metadata",
      "Validated evidence completeness by dispute type",
      "Computed contest value against analyst cost",
      "Generated analyst-ready defense narrative"
    ]
  });
});

const server = app.listen(port, host, () => {
  console.log(`AI Chargeback Risk Manager listening on http://${host}:${port}`);
});

server.on("error", (error) => {
  console.error("Failed to start server", error);
  process.exitCode = 1;
});
