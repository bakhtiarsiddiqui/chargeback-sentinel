/**
 * TransactionRiskAgent
 * --------------------
 * Evaluates pre-transaction risk flags at authorization time.
 * Pure threshold & rule logic (explicitly non-ML for transparent risk governance).
 */

function round(value) {
  return Math.round(value * 100) / 100;
}

export function assessTransactionRisk(txn) {
  let riskScore = 0;
  const flags = [];

  const amount = Number(txn.amount || 0);
  const threeDs = Boolean(txn.threeDsAuthenticated || txn.three_ds_authenticated);
  const ipMatch = Boolean(txn.ipCountryMatch || txn.ip_country_matches_billing_country);
  const deviceMatch = Boolean(txn.deviceFingerprintMatch || txn.device_id_match);
  const historyCount = Number(txn.customerTxnHistoryCount || txn.customer_txn_history_count || (txn.previousDisputesByCustomer === 0 ? 0 : 1));
  const isFirstTime = txn.isFirstTimeCustomer !== undefined ? Boolean(txn.isFirstTimeCustomer) : historyCount === 0;

  if (amount >= 5000 && !threeDs) {
    riskScore += 0.35;
    flags.push("High-value transaction without 2FA/3DS (RBI >₹5,000 threshold requirement)");
  }

  if (!ipMatch) {
    riskScore += 0.25;
    flags.push("IP-billing country geography mismatch");
  }

  if (!deviceMatch) {
    riskScore += 0.20;
    flags.push("Unrecognized device fingerprint");
  }

  if (isFirstTime && amount >= 3000) {
    riskScore += 0.15;
    flags.push("First-time customer with above-average transaction value");
  }

  riskScore = Math.min(riskScore, 0.98);

  let decision = "allow";
  if (riskScore >= 0.6) {
    decision = "block_or_challenge";
  } else if (riskScore >= 0.3) {
    decision = "step_up_auth";
  }

  return {
    agent: "TransactionRiskAgent",
    riskScore: round(riskScore),
    decision,
    flags
  };
}
