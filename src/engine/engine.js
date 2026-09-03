const REQUIRED_EVIDENCE = {
  product_not_received: [
    {
      key: "deliveryProof",
      label: "Proof of delivery"
    },
    {
      key: "trackingStatus",
      label: "Carrier tracking history",
      validate: (value) => ["delivered", "out_for_delivery", "service_accessed"].includes(value)
    },
    {
      key: "communicationEvidence",
      label: "Customer communication trail"
    },
    {
      key: "termsAccepted",
      label: "Terms and checkout acceptance"
    }
  ],
  fraudulent_transaction: [
    {
      key: "deviceFingerprintMatch",
      label: "Device fingerprint"
    },
    {
      key: "ipCountryMatch",
      label: "IP-country consistency"
    },
    {
      key: "deliveryProof",
      label: "Fulfillment evidence"
    }
  ],
  digital_service: [
    {
      key: "deliveryProof",
      label: "Access or usage logs"
    },
    {
      key: "customerAcknowledgedReceipt",
      label: "Customer acknowledgment"
    },
    {
      key: "termsAccepted",
      label: "Terms acceptance"
    }
  ]
};

function round(value) {
  return Math.round(value * 100) / 100;
}

export const SLA_TARGET_HOURS = Number(process.env.SLA_TARGET_HOURS || 72);

export function calculateDisputeSla(dispute, refDate = new Date()) {
  const normalized = normalizeDispute(dispute);
  const disputeTime = new Date(normalized.disputeDate || normalized.orderDate || refDate).getTime();
  const deadlineTime = disputeTime + SLA_TARGET_HOURS * 3600 * 1000;
  const refTime = new Date(refDate).getTime();
  const hoursRemaining = Math.round((deadlineTime - refTime) / (3600 * 1000));

  const isResolved = Boolean(normalized.sessionAction || (normalized.outcome && normalized.outcome !== "pending"));

  let status = "within_sla";
  if (isResolved) {
    status = "within_sla";
  } else if (hoursRemaining < 0) {
    status = "breached";
  } else if (hoursRemaining <= 12) {
    status = "at_risk";
  } else {
    status = "within_sla";
  }

  return {
    disputeId: normalized.id,
    slaTargetHours: SLA_TARGET_HOURS,
    disputeDate: normalized.disputeDate,
    deadlineIso: new Date(deadlineTime).toISOString(),
    hoursRemaining,
    isResolved,
    status
  };
}

export function normalizeDispute(rawDispute) {
  return {
    ...rawDispute,
    amount: Number(rawDispute.amount),
    previousDisputesByCustomer: Number(rawDispute.previousDisputesByCustomer || 0),
    analystReviewMinutes: Number(rawDispute.analystReviewMinutes || 30),
    evidenceDocs: rawDispute.evidenceDocs || []
  };
}

// Checks documentation completeness for the merchant's dispute defense
export function verifyEvidence(dispute) {
  const normalized = normalizeDispute(dispute);
  const requiredItems = REQUIRED_EVIDENCE[normalized.disputeType] || REQUIRED_EVIDENCE.product_not_received;

  const missingItems = requiredItems
    .filter((item) => {
      if (item.validate) {
        return !item.validate(normalized[item.key]);
      }
      return !normalized[item.key];
    })
    .map((item) => item.label);

  const riskFlags = [];
  if (normalized.refundInitiated) riskFlags.push("Refund already initiated before dispute resolution");
  if (!normalized.ipCountryMatch) riskFlags.push("IP geography mismatch");
  if (normalized.previousDisputesByCustomer >= 2) riskFlags.push("Repeat dispute behavior observed");
  if (!normalized.deliveryProof) riskFlags.push("No delivery or access proof present");
  if (!normalized.communicationEvidence) riskFlags.push("No customer communication trail attached");

  const completenessScore = round((requiredItems.length - missingItems.length) / requiredItems.length);

  return {
    completenessScore,
    missingItems,
    riskFlags,
    requiredItems: requiredItems.map((item) => item.label),
    sufficient: completenessScore >= 0.75 && missingItems.length <= 1
  };
}

export function scoreDispute(dispute) {
  const normalized = normalizeDispute(dispute);
  const evidence = verifyEvidence(normalized);

  let score = 0.45;
  const reasonCodes = [];

  if (normalized.deliveryProof) {
    score += 0.2;
    reasonCodes.push("Proof of delivery or access present");
  } else {
    score -= 0.18;
    reasonCodes.push("Delivery or access proof missing");
  }

  if (normalized.customerAcknowledgedReceipt) {
    score += 0.14;
    reasonCodes.push("Customer acknowledged receipt");
  }

  if (normalized.signedDelivery) {
    score += 0.08;
    reasonCodes.push("Signed delivery confirmation attached");
  }

  if (normalized.communicationEvidence) {
    score += 0.06;
    reasonCodes.push("Customer communication evidence available");
  } else {
    score -= 0.05;
    reasonCodes.push("Communication trail missing");
  }

  if (normalized.refundInitiated) {
    score -= 0.22;
    reasonCodes.push("Refund already initiated");
  }

  if (!normalized.ipCountryMatch) {
    score -= 0.08;
    reasonCodes.push("IP-country mismatch");
  }

  if (!normalized.deviceFingerprintMatch) {
    score -= 0.07;
    reasonCodes.push("Device fingerprint mismatch");
  }

  if (normalized.previousDisputesByCustomer >= 2) {
    score -= 0.05;
    reasonCodes.push("Customer has repeat dispute behavior");
  }

  if (normalized.amount >= 5000) {
    score += 0.04;
    reasonCodes.push("Higher ticket dispute justifies deeper contest review");
  }

  score += evidence.completenessScore * 0.12;

  const contestCost = round(150 + normalized.analystReviewMinutes * 8);
  const recoveryValue = normalized.amount * score;
  const expectedRecovery = round(recoveryValue - contestCost);

  let decision = "needs_more_evidence";
  if (score >= 0.72 && evidence.sufficient && expectedRecovery > 0) {
    decision = "ready_to_submit";
  } else if (score < 0.45 || expectedRecovery <= 0 || normalized.refundInitiated) {
    decision = "do_not_contest";
  }

  return {
    disputeId: normalized.id,
    winProbability: round(Math.min(Math.max(score, 0.05), 0.98)),
    expectedRecovery,
    contestCost,
    decision,
    reasonCodes,
    evidence
  };
}

const OLLAMA_URL = process.env.OLLAMA_URL || "http://127.0.0.1:11434";
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "llama3";

/**
 * Specialized agent responsible for drafting legal-grade merchant defense narratives.
 * Connects to a local Ollama LLM instance ('llama3' or 'mistral') or LangChain Express service.
 * Includes graceful, zero-downtime fallback to deterministic templates if offline or timing out.
 */
export class ResponseNarrativeAgent {
  constructor(options = {}) {
    this.ollamaUrl = options.ollamaUrl || OLLAMA_URL;
    this.model = options.model || OLLAMA_MODEL;
    this.timeoutMs = options.timeoutMs || 3000;
  }

  /**
   * Asynchronously generate narrative text for the dispute cover letter.
   *
   * @param {Object} dispute - Normalized dispute record
   * @param {Object} evidence - Verification object from verifyEvidence
   * @param {Object} mlScoring - Win probability & decision scoring object
   * @returns {Promise<string>} The cover letter narrative text
   */
  async _generateNarrativeText(dispute, evidence = null, mlScoring = null) {
    const normalized = normalizeDispute(dispute);
    const ver = evidence || verifyEvidence(normalized);
    const scoring = mlScoring || scoreDispute(normalized);
    const winProb = typeof scoring.winProbability === "number" ? Math.round(scoring.winProbability * 100) : null;

    // ── Deterministic Fallback Template ──────────────────────────────────────
    const fallbackText = [
      `We respectfully contest dispute ${normalized.id} for ${normalized.amount} ${normalized.currency}.`,
      winProb !== null
        ? `Our review indicates a ${winProb}% contest success likelihood based on merchant-side fulfillment and customer evidence.`
        : "Our review indicates contest success likelihood is being evaluated based on merchant-side fulfillment and customer evidence.",
      normalized.deliveryProof
        ? `The order shows a fulfillment status of "${normalized.trackingStatus}" and supporting proof has been attached.`
        : "We currently lack complete fulfillment proof and recommend collecting carrier or service access records before submission.",
      normalized.customerAcknowledgedReceipt
        ? "The customer communication trail includes an acknowledgment of receipt or usage."
        : "No direct customer acknowledgment is currently attached.",
      normalized.refundInitiated
        ? "A refund has already been initiated, which materially lowers the value of contesting this dispute."
        : "No merchant refund was initiated before the dispute, preserving the economic value of contesting.",
      `Recommended action: ${(scoring.decision || "needs_review").replaceAll("_", " ")}.`
    ].join(" ");

    // ── Attempt Local LLM Call (Ollama / LangChain Express) ──────────────────
    try {
      const systemPrompt = `You are a Fintech Chargeback Disputes Specialist representing merchant partners before card issuers (Visa, Mastercard, RuPay, Amex).
Your objective is to generate a highly professional, authoritative, and formal dispute cover letter contesting an invalid chargeback.
Incorporate exact transaction variables, evidence completeness metrics, and specific security authentication flags (3DS 2.0, CVV, AVS, IP match, Device match).
Do NOT fabricate non-existent transaction facts. Keep the response concise, assertive, and legal-grade.`;

      const userPrompt = `
Generate a formal chargeback contest cover letter for the following dispute case:

[TRANSACTION VARIABLES]
- Dispute ID: ${normalized.id}
- Dispute Amount: ${normalized.amount} ${normalized.currency}
- Dispute Category/Reason: ${normalized.disputeType}
- Transaction Timestamp / Date: ${normalized.disputeDate || "N/A"}

[SECURITY & AUTHENTICATION FLAGS]
- 3DS 2.0 Authenticated: ${Boolean(normalized.threeDsAuthenticated)}
- CVV Match Status: ${Boolean(normalized.cvvMatch)}
- AVS Address Match Status: ${Boolean(normalized.avsMatch)}
- Device Fingerprint Match: ${Boolean(normalized.deviceFingerprintMatch)}
- IP / Country Match: ${Boolean(normalized.ipCountryMatch)}

[FULFILLMENT & EVIDENCE METRICS]
- Evidence Completeness Score: ${Math.round((ver.completenessScore || 0) * 100)}%
- Delivery / Access Proof Attached: ${Boolean(normalized.deliveryProof)}
- Carrier Tracking Status: ${normalized.trackingStatus || "N/A"}
- Customer Acknowledgment Present: ${Boolean(normalized.customerAcknowledgedReceipt)}
- Terms & Refund Policy Accepted: ${Boolean(normalized.termsAccepted)}
- Prior Refund Initiated: ${Boolean(normalized.refundInitiated)}
- Attached Evidence Files: ${(normalized.evidenceDocs || []).join(", ") || "None"}
- Model Win Probability: ${winProb !== null ? `${winProb}%` : "N/A"}
- Recommended Action: ${(scoring.decision || "needs_review").replaceAll("_", " ")}

Write a concise 2-paragraph formal bank cover letter starting with "We respectfully contest dispute ${normalized.id}..." and concluding with "Recommended action: ${(scoring.decision || "needs_review").replaceAll("_", " ")}."`;

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);

      const response = await fetch(`${this.ollamaUrl}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: this.model,
          prompt: `${systemPrompt}\n\n${userPrompt}`,
          stream: false,
          options: { temperature: 0.2 }
        }),
        signal: controller.signal
      });

      clearTimeout(timer);

      if (!response.ok) {
        return fallbackText;
      }

      const data = await response.json();
      const llmText = (data.response || data.message?.content || "").trim();

      if (llmText && llmText.length > 30) {
        return llmText;
      }
    } catch {
      // Local LLM / Ollama offline or timed out — return fallback without throwing
    }

    return fallbackText;
  }

  /**
   * Asynchronously generate full response payload.
   */
  async generateDraft(dispute, verification = verifyEvidence(dispute), mlScoring = null) {
    const normalized = normalizeDispute(dispute);
    const ver = verification || verifyEvidence(normalized);
    const scoring = mlScoring || scoreDispute(normalized);
    const citations = [];
    const checklist = [];

    if (normalized.evidenceDocs.length) {
      citations.push(...normalized.evidenceDocs.map((doc) => `Attached: ${doc}`));
    }
    if (normalized.deliveryProof) citations.push("Order was fulfilled according to merchant records");
    if (normalized.customerAcknowledgedReceipt) citations.push("Customer acknowledgment is present in the communication trail");
    if (normalized.termsAccepted) citations.push("Checkout terms and merchant policy were accepted");

    checklist.push("Confirm dispute reason code matches the response narrative");
    checklist.push(...ver.requiredItems.map((item) => `Include: ${item}`));
    if (ver.missingItems.length) {
      checklist.push(...ver.missingItems.map((item) => `Collect before submission: ${item}`));
    }

    const draftText = await this._generateNarrativeText(normalized, ver, scoring);

    return {
      draftText,
      citations,
      submissionChecklist: [...new Set(checklist)]
    };
  }

  /**
   * Asynchronously builds the evidence PDF payload, waiting for async narrative text generation.
   */
  async _buildEvidencePdf(dispute, verification = verifyEvidence(dispute), mlScoring = null) {
    const normalized = normalizeDispute(dispute);
    const ver = verification || verifyEvidence(normalized);
    const scoring = mlScoring || scoreDispute(normalized);
    const narrativeText = await this._generateNarrativeText(normalized, ver, scoring);

    return {
      disputeId: normalized.id,
      generatedAt: new Date().toISOString(),
      disputeDetails: {
        amount: `${normalized.amount} ${normalized.currency}`,
        type: normalized.disputeType,
        date: normalized.disputeDate
      },
      verificationSummary: {
        completenessScore: ver.completenessScore,
        sufficient: ver.sufficient,
        missingItems: ver.missingItems
      },
      mlScoring: {
        winProbability: scoring.winProbability,
        decision: scoring.decision,
        reasonCodes: scoring.reasonCodes
      },
      coverLetterText: narrativeText,
      attachments: normalized.evidenceDocs || []
    };
  }
}

/**
 * Synchronous/async backward-compatibility wrapper for legacy callers.
 */
export function draftResponse(dispute, verification = verifyEvidence(dispute)) {
  const normalized = normalizeDispute(dispute);
  const scoring = scoreDispute(normalized);
  const citations = [];
  const checklist = [];

  if (normalized.evidenceDocs.length) {
    citations.push(...normalized.evidenceDocs.map((doc) => `Attached: ${doc}`));
  }
  if (normalized.deliveryProof) citations.push("Order was fulfilled according to merchant records");
  if (normalized.customerAcknowledgedReceipt) citations.push("Customer acknowledgment is present in the communication trail");
  if (normalized.termsAccepted) citations.push("Checkout terms and merchant policy were accepted");

  checklist.push("Confirm dispute reason code matches the response narrative");
  checklist.push(...verification.requiredItems.map((item) => `Include: ${item}`));
  if (verification.missingItems.length) {
    checklist.push(...verification.missingItems.map((item) => `Collect before submission: ${item}`));
  }

  const winProb = typeof scoring.winProbability === "number" ? Math.round(scoring.winProbability * 100) : null;
  const draftText = [
    `We respectfully contest dispute ${normalized.id} for ${normalized.amount} ${normalized.currency}.`,
    winProb !== null
      ? `Our review indicates a ${winProb}% contest success likelihood based on merchant-side fulfillment and customer evidence.`
      : "Our review indicates contest success likelihood is being evaluated based on merchant-side fulfillment and customer evidence.",
    normalized.deliveryProof
      ? `The order shows a fulfillment status of "${normalized.trackingStatus}" and supporting proof has been attached.`
      : "We currently lack complete fulfillment proof and recommend collecting carrier or service access records before submission.",
    normalized.customerAcknowledgedReceipt
      ? "The customer communication trail includes an acknowledgment of receipt or usage."
      : "No direct customer acknowledgment is currently attached.",
    normalized.refundInitiated
      ? "A refund has already been initiated, which materially lowers the value of contesting this dispute."
      : "No merchant refund was initiated before the dispute, preserving the economic value of contesting.",
    `Recommended action: ${(scoring.decision || "needs_review").replaceAll("_", " ")}.`
  ].join(" ");

  return {
    draftText,
    citations,
    submissionChecklist: [...new Set(checklist)]
  };
}

export function evaluateDisputes(disputes) {
  const labeled = disputes.map((dispute) => {
    const scoring = scoreDispute(dispute);
    const actualPositive = dispute.outcome === "won";
    const predictedPositive = scoring.decision === "ready_to_submit";
    return {
      ...scoring,
      actualPositive,
      predictedPositive,
      actualOutcome: dispute.outcome,
      analystMinutesSaved: predictedPositive ? Math.max(dispute.analystReviewMinutes - 12, 0) : 6
    };
  });

  const tp = labeled.filter((item) => item.actualPositive && item.predictedPositive).length;
  const fp = labeled.filter((item) => !item.actualPositive && item.predictedPositive).length;
  const fn = labeled.filter((item) => item.actualPositive && !item.predictedPositive).length;
  const precision = tp + fp === 0 ? 0 : tp / (tp + fp);
  const recall = tp + fn === 0 ? 0 : tp / (tp + fn);
  const f1 = precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall);

  const evidenceAccuracy =
    labeled.filter((item) => {
      const actuallyRecoverable = item.actualOutcome === "won";
      return item.evidence.sufficient === actuallyRecoverable;
    }).length / labeled.length;

  const falsePositiveCost = labeled
    .filter((item) => !item.actualPositive && item.predictedPositive)
    .reduce((sum, item) => sum + item.contestCost, 0);

  const expectedValueRecovered = labeled
    .filter((item) => item.predictedPositive)
    .reduce((sum, item) => sum + Math.max(item.expectedRecovery, 0), 0);

  const avgAnalystTimeSaved =
    labeled.reduce((sum, item) => sum + item.analystMinutesSaved, 0) / labeled.length;

  return {
    precision: round(precision),
    recall: round(recall),
    f1: round(f1),
    evidenceAccuracy: round(evidenceAccuracy),
    falsePositiveCost: round(falsePositiveCost),
    expectedValueRecovered: round(expectedValueRecovered),
    avgAnalystTimeSaved: round(avgAnalystTimeSaved),
    totalDisputes: labeled.length
  };
}
