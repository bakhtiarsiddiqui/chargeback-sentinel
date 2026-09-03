/**
 * ML Feature Adapter (src/engine/mlAdapter.js)
 * ---------------------------------------------
 * Bridges camelCase dispute records to the Python ML service schema.
 * Completeness is computed server-side from authentication signals; this adapter
 * sends raw country fields so geo-match is not inferred as true when both are missing.
 */

export function toMlFeatures(normalizedDispute) {
  const billingCountry = normalizedDispute.billingCountry || "IN";
  const ipMatch = Boolean(normalizedDispute.ipCountryMatch);
  const cardholderIpCountry =
    normalizedDispute.cardholderIpCountry || (ipMatch ? billingCountry : "AE");

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
    cardholder_ip_country: cardholderIpCountry,
    billing_country: billingCountry,
    ip_country_matches_billing_country: cardholderIpCountry === billingCountry
  };
}
