import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import disputes from "../../data/disputes.json" with { type: "json" };
import {
  draftResponse,
  evaluateDisputes,
  normalizeDispute,
  scoreDispute,
  verifyEvidence
} from "../engine/engine.js";
import { runCasePipeline } from "../engine/orchestrator.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = process.env.PORT || 3000;
const host = process.env.HOST || "127.0.0.1";

const normalizedDisputes = disputes.map(normalizeDispute);
const heldOutDisputes = normalizedDisputes.slice(-3);
const queueDisputes = normalizedDisputes.slice(0, 3);

app.use(express.json());
app.use(express.static(path.join(__dirname, "../public")));

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "chargeback-sentinel-api",
    version: "1.0.0",
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

app.post("/api/case/process", async (req, res) => {
  try {
    const mode = req.body.mode || "assistive";
    const result = await runCasePipeline(req.body, { mode });
    res.json(result);
  } catch (error) {
    console.error("Multi-Agent Orchestrator Error:", error);
    res.status(500).json({ error: "Failed to run multi-agent case pipeline" });
  }
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
      `Ingested dispute ${dispute.id} — ${dispute.disputeType}, ${dispute.amount} ${dispute.currency}`,
      verification.missingItems.length === 0
        ? "Evidence check: all required items present"
        : `Evidence check: ${verification.missingItems.length} item(s) missing (${verification.missingItems.join(", ")})`,
      `Contest scoring: ${Math.round(scoring.winProbability * 100)}% win probability, expected recovery ${scoring.expectedRecovery} ${dispute.currency}`,
      `Decision: ${scoring.decision.replaceAll("_", " ")}`
    ]
  });
});

const server = app.listen(port, host, () => {
  console.log(`Chargeback Sentinel API listening on http://${host}:${port}`);
});

server.on("error", (error) => {
  console.error("Failed to start server", error);
  process.exitCode = 1;
});
