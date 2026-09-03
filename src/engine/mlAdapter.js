/**
 * ML Feature Adapter (src/engine/mlAdapter.js)
 * ---------------------------------------------
 * Bridges legacy/frontend dispute schemas (camelCase) to the Python ML microservice schema (snake_case).
 */

export function toMlFeatures(normalizedDispute) {
  return {
    txn_amount: Number(normalizedDispute.amount || 0),
    previous_txns_from_device: Number(normalizedDispute.previousTxnsFromDevice ?? 1),
    customer_txn_history_count: Number(normalizedDispute.customerTxnHistoryCount ?? 1),
    customer_disputed_before_count: Number(normalizedDispute.previousDisputesByCustomer ?? 0),
    device_id_match: Boolean(normalizedDispute.deviceFingerprintMatch ?? false),
    cvv_match: Boolean(normalizedDispute.cvvMatch ?? true),
    avs_match: Boolean(normalizedDispute.avsMatch ?? true),
    is_first_time_customer: normalizedDispute.isFirstTimeCustomer !== undefined
      ? Boolean(normalizedDispute.isFirstTimeCustomer)
      : (normalizedDispute.previousDisputesByCustomer ?? 0) === 0,
    delivery_address_match_billing: Boolean(normalizedDispute.deliveryAddressMatchBilling ?? true),
    three_ds_authenticated: Boolean(normalizedDispute.threeDsAuthenticated ?? false),
    refund_issued: Boolean(normalizedDispute.refundInitiated ?? false),
    ip_country_matches_billing_country: Boolean(normalizedDispute.ipCountryMatch ?? false),
    completeness_score: Number(normalizedDispute._evidenceCompletenessScore ?? 0)
  };
}
