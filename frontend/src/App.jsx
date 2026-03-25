import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = "http://localhost:5000/api";

/* ═══════════════════════════════════════════════════════════════
   MOCK DATABASE — simulates backend DB lookups for standalone demo
   ═══════════════════════════════════════════════════════════════ */
const MOCK_DB = {
  orders: {
    "ORD-100001": { order_id:"ORD-100001", status:"delivered", total:161.99, items:[{product_name:"Wireless Noise-Canceling Headphones"}], tracking_number:"1Z999AA10123456784", carrier:"UPS", delivered_date:"2026-01-19", first_name:"Sarah", customer_id:"CUST-001001", transaction:{transaction_id:"TXN-200001",payment_method:"Visa ending 4242",refund_eligible:true,refund_deadline:"2026-02-19"}},
    "ORD-100002": { order_id:"ORD-100002", status:"delivered", total:92.38, items:[{product_name:"Smart LED Desk Lamp"},{product_name:"USB-C Hub Adapter"}], tracking_number:"9400111899223456789012", carrier:"USPS", delivered_date:"2026-01-28", first_name:"Mike", customer_id:"CUST-001002", transaction:{transaction_id:"TXN-200002",payment_method:"Mastercard ending 5555",refund_eligible:true,refund_deadline:"2026-02-28"}},
    "ORD-100003": { order_id:"ORD-100003", status:"in_transit", total:215.99, items:[{product_name:"Mechanical Keyboard RGB"},{product_name:"Ergonomic Mouse Pad XL"}], tracking_number:"794644790132", carrier:"FedEx", estimated_delivery:"2026-02-10", first_name:"Emily", customer_id:"CUST-001003", notes:"Weather delay in midwest distribution center"},
    "ORD-100004": { order_id:"ORD-100004", status:"processing", total:377.99, items:[{product_name:'4K Ultra Monitor 27"'}], first_name:"David", customer_id:"CUST-001004"},
    "ORD-100005": { order_id:"ORD-100005", status:"delivered", total:70.78, items:[{product_name:"Bluetooth Speaker Portable"}], delivered_date:"2025-12-08", first_name:"David", customer_id:"CUST-001004", transaction:{refund_eligible:false,refund_deadline:"2025-12-31"}},
    "ORD-100006": { order_id:"ORD-100006", status:"cancelled", total:148.38, items:[{product_name:"Smart Fitness Watch"}], first_name:"Lisa", customer_id:"CUST-001005", notes:"Customer requested cancellation before shipment"},
    "ORD-100007": { order_id:"ORD-100007", status:"returned", total:269.99, items:[{product_name:"Wireless Earbuds Pro"},{product_name:"Charging Case"}], first_name:"James", customer_id:"CUST-001006", transaction:{refund_eligible:false,refund_deadline:"2025-11-01"}}
  },
  customers: {
    "CUST-001001": { customer_id:"CUST-001001", first_name:"Sarah", last_name:"Johnson", email:"sarah.johnson@email.com", subscription:{plan_name:"pro",plan_price:29.99,billing_cycle:"monthly",status:"active",auto_renew:true}, orders:["ORD-100001"]},
    "CUST-001002": { customer_id:"CUST-001002", first_name:"Mike", last_name:"Chen", email:"mike.chen@email.com", subscription:{plan_name:"basic",plan_price:9.99,billing_cycle:"monthly",status:"active"}, orders:["ORD-100002"]},
    "CUST-001003": { customer_id:"CUST-001003", first_name:"Emily", last_name:"Davis", email:"emily.davis@email.com", subscription:{plan_name:"pro",plan_price:29.99,billing_cycle:"monthly",status:"cancelled"}, orders:["ORD-100003"]},
    "CUST-001004": { customer_id:"CUST-001004", first_name:"David", last_name:"Wilson", email:"david.wilson@email.com", subscription:{plan_name:"enterprise",plan_price:99.99,billing_cycle:"annual",status:"active"}, orders:["ORD-100004","ORD-100005"]},
    "CUST-001005": { customer_id:"CUST-001005", first_name:"Lisa", last_name:"Martinez", email:"lisa.martinez@email.com", subscription:{plan_name:"free",plan_price:0,billing_cycle:"monthly",status:"active"}, orders:["ORD-100006"]},
    "CUST-001006": { customer_id:"CUST-001006", first_name:"James", last_name:"Brown", email:"james.brown@email.com", subscription:{plan_name:"basic",plan_price:9.99,billing_cycle:"monthly",status:"paused"}, orders:["ORD-100007"]}
  },
  transactions: {
    "TXN-200001": {transaction_id:"TXN-200001",type:"charge",status:"completed",amount:161.99,payment_method:"Visa ending 4242",refund_eligible:true,refund_deadline:"2026-02-19",transaction_date:"2026-01-10",first_name:"Sarah"},
    "TXN-200002": {transaction_id:"TXN-200002",type:"charge",status:"completed",amount:92.38,payment_method:"Mastercard ending 5555",refund_eligible:true,refund_deadline:"2026-02-28",transaction_date:"2026-01-20",first_name:"Mike"},
    "TXN-200003": {transaction_id:"TXN-200003",type:"charge",status:"completed",amount:215.99,payment_method:"Visa ending 1234",refund_eligible:true,transaction_date:"2026-02-01",first_name:"Emily"}
  }
};

/* ═══════════════════════════════════════════════════════════════
   MOCK API — generates genuine responses from mock DB
   ═══════════════════════════════════════════════════════════════ */
function mockAPI(message, chatHistory = []) {
  const lower = message.toLowerCase();
  const upper = message.toUpperCase();
  const tokens = lower.split(/\s+/);

  // Extract IDs from current message
  const ids = {};
  let match;
  if ((match = upper.match(/ORD-\d{5,7}/))) ids.order_id = match[0];
  if ((match = upper.match(/CUST-\d{5,7}/))) ids.customer_id = match[0];
  if ((match = upper.match(/TXN-\d{5,7}/))) ids.transaction_id = match[0];

  // Fallback: scan recent history newest-first when current message has no IDs
  if (!ids.order_id && !ids.customer_id && !ids.transaction_id) {
    for (let i = chatHistory.length - 1; i >= 0; i--) {
      const prev = chatHistory[i];
      if (!prev || !prev.text) continue;
      const prevUpper = prev.text.toUpperCase();
      if (!ids.order_id && (match = prevUpper.match(/ORD-\d{5,7}/))) ids.order_id = match[0];
      if (!ids.customer_id && (match = prevUpper.match(/CUST-\d{5,7}/))) ids.customer_id = match[0];
      if (!ids.transaction_id && (match = prevUpper.match(/TXN-\d{5,7}/))) ids.transaction_id = match[0];
      if (ids.order_id && ids.customer_id && ids.transaction_id) break;
    }
  }

  // Build context string from recent history for multi-turn flow detection
  const historyText = chatHistory.slice(-6).map(m => m.text || "").join(" ").toLowerCase();
  const CONFIRMATION_WORDS = ["yes", "sure", "proceed", "confirm", "ok", "okay", "do it", "go ahead", "please", "yep", "yeah"];
  const REFUND_WORDS = ["refund", "money back", "reimburse", "return"];
  const isConfirmation = CONFIRMATION_WORDS.some(w => lower.includes(w));
  const inRefundFlow   = REFUND_WORDS.some(w => lower.includes(w)) || REFUND_WORDS.some(w => historyText.includes(w));

  // Sentiment
  const negW = ["terrible","awful","frustrated","angry","hate","worst","horrible","furious","broken","useless","disappointed"];
  const posW = ["great","amazing","thanks","wonderful","happy","love","excellent","perfect","appreciate"];
  const negM = negW.filter(w => tokens.includes(w));
  const posM = posW.filter(w => tokens.includes(w));
  const sentScore = posM.length > 0 && negM.length === 0 ? 0.6 : negM.length > 0 ? -0.7 : 0;
  const sentLabel = sentScore > 0.2 ? "positive" : sentScore < -0.2 ? "negative" : "neutral";
  const intensity = Math.max(negM.length, posM.length) / Math.max(tokens.length, 1);

  // Intent classification
  const intentDefs = {
    billing:["bill","charge","invoice","payment","refund","money","price","cost"],
    technical:["bug","error","crash","slow","broken","fix","login","password"],
    account:["account","profile","settings","email","delete","update","privacy"],
    shipping:["ship","deliver","track","package","arrive","lost","damaged"],
    order_status:["order","status","tracking","shipped","delivered","processing","when","eta"],
    refund:["refund","money back","reimburse","return money"],
    subscription:["subscription","plan","upgrade","downgrade","renew"],
    greeting:["hello","hi","help","hey"],
    thanks:["thanks","thank you","appreciate"],
    farewell:["bye","goodbye"]
  };
  let bestIntent = "unknown", bestScore = 0, allIntents = [], matchedKws = {};
  for (const [cat, kws] of Object.entries(intentDefs)) {
    const matched = kws.filter(k => k.includes(' ') ? lower.includes(k) : tokens.includes(k) || tokens.some(t => (t.startsWith(k) || k.startsWith(t)) && Math.abs(t.length - k.length) <= 3));
    if (matched.length > 0) {
      const score = Math.min(matched.length / Math.min(kws.length, 5) + matched.length * 0.15, 1.0);
      allIntents.push({ intent: cat, score: Math.round(score * 1000) / 1000 });
      matchedKws[cat] = matched;
      if (score > bestScore) { bestScore = score; bestIntent = cat; }
    }
  }
  allIntents.sort((a, b) => b.score - a.score);

  // Database lookups
  let dbFound = false, dbLookups = [], dbErrors = [], dataUsed = [], dataVerified = false;
  let responseText = "", source = "fallback";
  const empathy = sentLabel === "negative" && intensity > 0.15 ? "I understand this is frustrating, and I sincerely apologize. " : "";

  const order = ids.order_id ? MOCK_DB.orders[ids.order_id] : null;
  const customer = ids.customer_id ? MOCK_DB.customers[ids.customer_id] : null;
  const transaction = ids.transaction_id ? MOCK_DB.transactions[ids.transaction_id] : null;

  if (ids.order_id) dbLookups.push(`Looked up order ${ids.order_id}`);
  if (ids.customer_id) dbLookups.push(`Looked up customer ${ids.customer_id}`);
  if (ids.transaction_id) dbLookups.push(`Looked up transaction ${ids.transaction_id}`);
  if (ids.order_id && !order) dbErrors.push(`Order ${ids.order_id} not found.`);
  if (ids.customer_id && !customer) dbErrors.push(`Customer ${ids.customer_id} not found.`);
  if (ids.transaction_id && !transaction) dbErrors.push(`Transaction ${ids.transaction_id} not found.`);

  // Conversational bypass — takes priority over any active DB context
  const CONVERSATIONAL_PHRASES = ["thank you", "thanks", "bye", "goodbye", "that's all", "that is all", "nothing else", "all good"];
  const isConversational = ["greeting", "thanks", "farewell"].includes(bestIntent) ||
    CONVERSATIONAL_PHRASES.some(ph => lower.includes(ph));
  if (isConversational) {
    if (bestIntent === "greeting" || ["hello", "hi", "hey"].some(w => lower.includes(w))) {
      return { response: "Hello! I'm your AI support assistant. Share an order ID (ORD-100001), customer ID (CUST-001001), or describe your issue!", intent: { primary_intent: "greeting" }, sentiment: { label: "neutral", score: 0.5 }, source: "greeting", confidence: { score: 85 }, handoff: { recommended: false } };
    }
    if (bestIntent === "farewell" || ["bye", "goodbye", "that's all", "that is all", "nothing else"].some(w => lower.includes(w))) {
      return { response: "Goodbye! Don't hesitate to reach out if you need anything. Take care!", intent: { primary_intent: "farewell" }, sentiment: { label: "neutral", score: 0.5 }, source: "farewell", confidence: { score: 85 }, handoff: { recommended: false } };
    }
    return { response: "You're welcome! Let me know if you need help with anything else.", intent: { primary_intent: "thanks" }, sentiment: { label: "positive", score: 0.6 }, source: "thanks", confidence: { score: 85 }, handoff: { recommended: false } };
  }

  // Build genuine response from data
  if (dbErrors.length > 0) {
    responseText = `${empathy}${dbErrors.join(" ")} Could you double-check the ID?`;
    source = "id_not_found";
  } else if (order) {
    dbFound = true; dataVerified = true; dataUsed.push(`order:${order.order_id}`);
    const items = order.items.map(i => i.product_name).join(", ");
    const isRefund = REFUND_WORDS.some(w => lower.includes(w));

    if (isRefund || (isConfirmation && inRefundFlow)) {
      if (order.transaction && order.transaction.refund_eligible) {
        if (isConfirmation && inRefundFlow) {
          responseText = `${empathy}Your refund of $${order.total} for order ${order.order_id} has been successfully initiated. It will be returned to your ${order.transaction.payment_method} within 5-7 business days. You'll receive a confirmation email shortly. Is there anything else I can help with?`;
          source = "db_refund_processed";
        } else {
          responseText = `${empathy}Order ${order.order_id} is eligible for a full refund of $${order.total}. It will be processed to your ${order.transaction.payment_method} within 5-7 business days. Items: ${items}. Would you like me to proceed with the refund?`;
          source = "db_refund_eligible";
        }
      } else if (order.transaction && !order.transaction.refund_eligible) {
        responseText = `${empathy}Order ${order.order_id} is outside the 30-day refund window (deadline: ${order.transaction.refund_deadline}). Total: $${order.total}. Items: ${items}. Want me to connect you with a specialist?`;
        source = "db_refund_ineligible";
      } else {
        responseText = `${empathy}I understand you'd like a refund for order ${order.order_id}, but I was unable to locate the original transaction to verify eligibility. Let me connect you with a specialist who can process this directly.`;
        source = "db_refund_no_transaction";
      }
    } else if (order.status === "delivered") {
      responseText = `${empathy}Order ${order.order_id} was delivered on ${order.delivered_date}. Items: ${items}. Total: $${order.total}. Anything else about this order?`;
      source = "db_order_delivered";
    } else if (["shipped", "in_transit", "out_for_delivery"].includes(order.status)) {
      const track = order.tracking_number ? ` Tracking: ${order.tracking_number} via ${order.carrier}.` : "";
      const eta = order.estimated_delivery ? ` ETA: ${order.estimated_delivery}.` : "";
      const note = order.notes ? ` Note: ${order.notes}` : "";
      responseText = `${empathy}Order ${order.order_id} is ${order.status.replace(/_/g, " ")}.${track}${eta}${note} Items: ${items}.`;
      source = "db_order_in_transit";
    } else if (order.status === "processing") {
      responseText = `${empathy}Order ${order.order_id} is being processed. Items: ${items}. Total: $${order.total}. You'll get tracking once it ships.`;
      source = "db_order_processing";
    } else if (order.status === "cancelled") {
      responseText = `${empathy}Order ${order.order_id} was cancelled.${order.notes ? " " + order.notes + "." : ""} Items: ${items}. Total: $${order.total}.`;
      source = "db_order_cancelled";
    } else if (order.status === "returned") {
      responseText = `${empathy}Order ${order.order_id} was returned. Items: ${items}. Total: $${order.total}. Refund takes 5-7 business days.`;
      source = "db_order_returned";
    } else {
      responseText = `${empathy}Order ${order.order_id}: ${order.status.toUpperCase()}, $${order.total}. Items: ${items}.`;
      source = "db_order_generic";
    }
  } else if (transaction) {
    dbFound = true; dataVerified = true; dataUsed.push(`txn:${transaction.transaction_id}`);
    const isRefundIntent = ["refund", "billing"].includes(bestIntent) ||
      REFUND_WORDS.some(w => lower.includes(w));
    if (isRefundIntent || (isConfirmation && inRefundFlow)) {
      if (transaction.refund_eligible) {
        if (isConfirmation && inRefundFlow) {
          responseText = `${empathy}Your refund of $${transaction.amount} for transaction ${transaction.transaction_id} has been successfully initiated. It will be returned to your ${transaction.payment_method} within 5-7 business days. You'll receive a confirmation email shortly. Is there anything else I can help with?`;
          source = "db_txn_refund_processed";
        } else {
          responseText = `${empathy}Transaction ${transaction.transaction_id} is eligible for a refund of $${transaction.amount}. The refund will be processed to your ${transaction.payment_method} within 5-7 business days (deadline: ${transaction.refund_deadline}). Would you like me to initiate it?`;
          source = "db_txn_refund_eligible";
        }
      } else if (transaction.status === "refunded") {
        responseText = `${empathy}Transaction ${transaction.transaction_id} has already been fully refunded. The $${transaction.amount} should be back on your ${transaction.payment_method}. Anything else I can help with?`;
        source = "db_txn_already_refunded";
      } else {
        responseText = `${empathy}Transaction ${transaction.transaction_id} is not eligible for a refund (status: ${transaction.status}). Would you like me to connect you with a specialist?`;
        source = "db_txn_refund_ineligible";
      }
    } else {
      responseText = `${empathy}Transaction ${transaction.transaction_id} found: ${transaction.type} | ${transaction.status} | $${transaction.amount} | ${transaction.payment_method} | ${transaction.transaction_date}.${transaction.refund_eligible ? ` Refund eligible (deadline: ${transaction.refund_deadline}).` : ""}`;
      source = "db_transaction";
    }
  } else if (customer) {
    dbFound = true; dataVerified = true; dataUsed.push(`customer:${customer.customer_id}`);
    const orderList = customer.orders.map(oid => { const o = MOCK_DB.orders[oid]; return o ? `${oid} (${o.status}, $${o.total})` : oid; }).join("; ");
    const s = customer.subscription;
    if (bestIntent === "subscription" && s) {
      const auto = s.auto_renew ? "auto-renews" : "does not auto-renew";
      responseText = `${empathy}Subscription for account ${customer.customer_id}: ${s.plan_name.toUpperCase()} plan at $${s.plan_price}/${s.billing_cycle}. Status: ${s.status} — ${auto}. Would you like to upgrade, downgrade, or cancel?`;
      source = "db_customer_subscription";
    } else if (["order_status", "shipping"].includes(bestIntent) && customer.orders.length > 0) {
      responseText = `${empathy}Recent orders for account ${customer.customer_id}: ${orderList}. Share a specific order ID for full tracking details.`;
      source = "db_customer_orders";
    } else {
      responseText = `${empathy}Account ${customer.customer_id} found. Email: ${customer.email}. Orders: ${orderList}. Plan: ${s.plan_name.toUpperCase()} ($${s.plan_price}/${s.billing_cycle}) — ${s.status}. How can I help?`;
      source = "db_customer_overview";
    }
  } else if (bestIntent === "greeting") {
    responseText = "Hello! I'm your AI support assistant with transparent confidence scoring. Share an order ID (ORD-100001), customer ID (CUST-001001), or describe your issue!";
    source = "greeting";
  } else if (bestIntent === "thanks") {
    responseText = "You're welcome! Anything else I can help with?"; source = "thanks";
  } else if (bestIntent === "farewell") {
    responseText = "Goodbye! Reach out anytime. Take care!"; source = "farewell";
  } else if (["order_status", "shipping"].includes(bestIntent)) {
    responseText = `${empathy}I'd love to help! Could you provide your order ID (e.g. ORD-100001)?`; source = "needs_order_id";
  } else if (["refund", "billing"].includes(bestIntent)) {
    responseText = `${empathy}I can help! Please share your order ID (e.g. ORD-100002) or transaction ID (e.g. TXN-200001).`; source = "needs_billing_id";
  } else if (bestIntent === "subscription") {
    responseText = `${empathy}I can help with subscriptions! Share your customer ID (e.g. CUST-001001).`; source = "needs_sub_id";
  } else if (bestIntent === "technical") {
    responseText = `${empathy}Sorry about the issue! Could you describe: (1) what you were doing, (2) what happened, (3) any error messages?`; source = "technical_help";
  } else if (bestIntent === "account") {
    responseText = `${empathy}I can help with your account! Share your customer ID (e.g. CUST-001001).`; source = "account_help";
  } else {
    responseText = `${empathy}I can help with orders, refunds, billing, subscriptions, and accounts. Try sharing an order ID (ORD-XXXXXX) or customer ID!`; source = "fallback";
  }

  // Confidence calculation with 5 factors (weights: 20/10/15/15/40)
  const CONV_OVERRIDE_WORDS = ["yes","sure","ok","okay","proceed","confirm","thanks","thank you","bye","goodbye","yep","yeah","go ahead","please","do it"];
  const isConvOverride = tokens.length <= 3 && CONV_OVERRIDE_WORDS.some(w => lower.includes(w));

  const intentScoreVal = isConvOverride ? 1.0 : bestScore;
  const f1 = intentScoreVal * 0.20;
  const clarityVal = isConvOverride ? 1.0 : (allIntents.length >= 2 ? Math.min((allIntents[0].score - allIntents[1].score) * 2, 1) : (allIntents.length === 1 ? allIntents[0].score : 0));
  const f2 = clarityVal * 0.10;
  const specVal = isConvOverride ? 1.0 : (tokens.length <= 2 ? 0.3 : tokens.length <= 5 ? 0.6 : tokens.length <= 15 ? 0.9 : 1.0);
  const f3 = specVal * 0.15;
  const f4 = 0.7 * 0.15;
  const dvVal = dbFound ? 1.0 : (dbErrors.length > 0 ? 0.3 : 0);
  const f5 = dvVal * 0.40;
  const totalConf = Math.round((f1 + f2 + f3 + f4 + f5) * 1000) / 10;
  const confLevel = totalConf >= 75 ? "high" : totalConf >= 50 ? "medium" : totalConf >= 30 ? "low" : "very_low";

  const missing = [];
  if (tokens.length <= 3 && !isConvOverride) missing.push("More details about your situation");
  if (!dbFound && !dbErrors.length && ["order_status", "shipping", "refund", "billing"].includes(bestIntent))
    missing.push("Your order ID (e.g. ORD-100001) or transaction ID");

  return {
    response: responseText,
    interaction_id: `mock-${Date.now()}`,
    response_meta: { source, data_verified: dataVerified, data_used: dataUsed },
    confidence: {
      score: totalConf, level: confLevel,
      description: confLevel === "high" ? "Highly confident — verified against database." : confLevel === "medium" ? "Moderately confident. An ID would improve accuracy." : confLevel === "low" ? "Limited confidence. More details would help." : "Not confident. Recommending human agent.",
      factors: [
        { name: "Intent Match Strength", weight: "20%", raw_score: Math.round(intentScoreVal * 100), weighted_score: Math.round(f1 * 100), explanation: isConvOverride ? "Contextual confirmation/conversational phrase detected (100%)" : `Matched '${bestIntent}' category` },
        { name: "Intent Clarity", weight: "10%", raw_score: Math.round(clarityVal * 100), weighted_score: Math.round(f2 * 100), explanation: isConvOverride ? "Contextual confirmation/conversational phrase detected (100%)" : (allIntents.length >= 2 ? "Multiple categories detected" : "Single clear category") },
        { name: "Query Specificity", weight: "15%", raw_score: Math.round(specVal * 100), weighted_score: Math.round(f3 * 100), explanation: isConvOverride ? "Contextual confirmation/conversational phrase detected (100%)" : `${tokens.length} words in query` },
        { name: "Sentiment Alignment", weight: "15%", raw_score: 70, weighted_score: Math.round(f4 * 100), explanation: "Sentiment consistency check" },
        { name: "Data Verification", weight: "40%", raw_score: Math.round(dvVal * 100), weighted_score: Math.round(f5 * 100), explanation: dbFound ? `Verified: ${dbLookups.join(", ")}` : dbErrors.length ? "ID not found" : "No IDs provided" }
      ],
      missing_information: missing
    },
    explainability: {
      intent: { detected: bestIntent, all_candidates: allIntents, matched_keywords: matchedKws, explanations: allIntents.map(i => `'${i.intent}': ${(i.score * 100).toFixed(0)}%`) },
      sentiment: { label: sentLabel, score: sentScore, intensity: Math.round(intensity * 100) / 100, positive_signals: posM, negative_signals: negM, explanations: [...posM.map(w => `Positive: '${w}'`), ...negM.map(w => `Negative: '${w}'`)] },
      database: { ids_extracted: ids, lookups_performed: dbLookups, data_found: dbFound, errors: dbErrors }
    },
    handoff: { recommended: totalConf < 35 || intensity > 0.6, reasons: totalConf < 35 ? ["Low confidence"] : intensity > 0.6 ? ["High frustration"] : [], message: totalConf < 35 || intensity > 0.6 ? "Connecting you with a human agent." : null }
  };
}

/* ═══════════════════════════════════════════════════════════════
   UI COMPONENTS
   ═══════════════════════════════════════════════════════════════ */

const ConfidenceMeter = ({ score, level }) => {
  const color = score >= 75 ? "#10b981" : score >= 50 ? "#f59e0b" : score >= 30 ? "#f97316" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ position: "relative", width: 52, height: 52 }}>
        <svg width="52" height="52" viewBox="0 0 52 52">
          <circle cx="26" cy="26" r="22" fill="none" stroke="#0f172a" strokeWidth="4" />
          <circle cx="26" cy="26" r="22" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${(score / 100) * 138.2} 138.2`} strokeLinecap="round"
            transform="rotate(-90 26 26)" style={{ transition: "stroke-dasharray 0.8s ease" }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>
          {Math.round(score)}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color, textTransform: "uppercase", letterSpacing: 1 }}>{level}</div>
        <div style={{ fontSize: 11, color: "#64748b" }}>confidence</div>
      </div>
    </div>
  );
};

const FactorBar = ({ factor }) => {
  const pct = Math.min(factor.raw_score, 100);
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: "#cbd5e1", fontWeight: 500 }}>{factor.name} <span style={{ color: "#475569" }}>({factor.weight})</span></span>
        <span style={{ color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace" }}>{factor.raw_score}%</span>
      </div>
      <div style={{ height: 6, background: "#0f172a", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: pct >= 70 ? "#10b981" : pct >= 40 ? "#f59e0b" : "#ef4444", borderRadius: 3, transition: "width 0.6s ease" }} />
      </div>
      <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>{factor.explanation}</div>
    </div>
  );
};

const DataBadge = ({ meta }) => {
  if (!meta) return null;
  const v = meta.data_verified;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600,
      background: v ? "#052e16" : "#0f172a", border: `1px solid ${v ? "#16a34a" : "#1e293b"}`, color: v ? "#4ade80" : "#94a3b8" }}>
      {v ? "\u2713 DB Verified" : "\u25CB No DB Data"}
      {meta.source && <span style={{ opacity: 0.6 }}> &bull; {meta.source.replace(/_/g, " ")}</span>}
    </span>
  );
};

const ExplainPanel = ({ data, isOpen, toggle }) => {
  if (!data) return null;
  const db = data.explainability?.database;
  return (
    <div style={{ marginTop: 8 }}>
      <button onClick={toggle} style={{ background: "none", border: "1px solid #1e293b", borderRadius: 8, color: "#94a3b8", fontSize: 12, padding: "6px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ transform: isOpen ? "rotate(90deg)" : "none", transition: "transform 0.2s", display: "inline-block" }}>&#x25B6;</span>
        {isOpen ? "Hide" : "Show"} AI Reasoning
      </button>
      {isOpen && (
        <div style={{ marginTop: 10, padding: 16, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 10, animation: "fadeIn 0.3s ease" }}>
          <h4 style={{ margin: "0 0 10px", fontSize: 13, color: "#f8fafc", fontWeight: 600 }}>Confidence Breakdown</h4>
          {data.confidence.factors.map((f, i) => <FactorBar key={i} factor={f} />)}

          {db && db.lookups_performed?.length > 0 && (
            <div style={{ marginBottom: 16, padding: 12, background: "#0a1128", border: "1px solid #1e3a8a", borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: "#60a5fa", fontWeight: 600, marginBottom: 4 }}>Database Lookups</div>
              {db.lookups_performed.map((l, i) => <div key={i} style={{ fontSize: 12, color: "#93c5fd", marginBottom: 2 }}>&bull; {l}</div>)}
              {db.ids_extracted && Object.keys(db.ids_extracted).length > 0 && (
                <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>IDs: {JSON.stringify(db.ids_extracted)}</div>
              )}
            </div>
          )}

          <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#f8fafc", fontWeight: 600 }}>Intent Analysis</h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {data.explainability.intent.all_candidates.map((c, i) => (
              <span key={i} style={{ padding: "3px 10px", borderRadius: 20, fontSize: 12, background: i === 0 ? "#1e3a8a" : "#0f172a", border: `1px solid ${i === 0 ? "#14b8a6" : "#1e293b"}`, color: i === 0 ? "#93c5fd" : "#94a3b8" }}>
                {c.intent}: {(c.score * 100).toFixed(0)}%
              </span>
            ))}
          </div>

          <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#f8fafc", fontWeight: 600 }}>Sentiment</h4>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600,
            background: data.explainability.sentiment.label === "positive" ? "#052e16" : data.explainability.sentiment.label === "negative" ? "#350a0a" : "#172554",
            border: `1px solid ${data.explainability.sentiment.label === "positive" ? "#16a34a" : data.explainability.sentiment.label === "negative" ? "#dc2626" : "#2563eb"}`,
            color: data.explainability.sentiment.label === "positive" ? "#4ade80" : data.explainability.sentiment.label === "negative" ? "#f87171" : "#60a5fa" }}>
            {data.explainability.sentiment.label === "positive" ? "\u2191" : data.explainability.sentiment.label === "negative" ? "\u2193" : "\u2192"} {data.explainability.sentiment.label} ({data.explainability.sentiment.score})
          </span>

          {data.confidence.missing_information?.length > 0 && (
            <div style={{ marginTop: 12, padding: 12, background: "#1c1917", border: "1px solid #78350f", borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600, marginBottom: 4 }}>Information I'm missing:</div>
              {data.confidence.missing_information.map((m, i) => <div key={i} style={{ fontSize: 12, color: "#d97706", marginBottom: 2 }}>&bull; {m}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   FEEDBACK BUTTONS (Feature 6)
   ═══════════════════════════════════════════════════════════════ */
const FeedbackButtons = ({ interactionId, useMock, onFeedback }) => {
  const [submitted, setSubmitted] = useState(null); // "up" | "down" | null

  const submit = async (type) => {
    const rating = type === "up" ? 5 : 1;
    setSubmitted(type);
    if (onFeedback) onFeedback(type);
    if (!useMock && interactionId) {
      try {
        await fetch(`${API_URL}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ interaction_id: interactionId, rating })
        });
      } catch { /* silent */ }
    }
  };

  if (submitted) {
    return (
      <div style={{ marginTop: 6, fontSize: 12, color: "#64748b" }}>
        {submitted === "up" ? "\u{1F44D}" : "\u{1F44E}"} Feedback recorded — thank you!
      </div>
    );
  }

  return (
    <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center" }}>
      <span style={{ fontSize: 11, color: "#475569" }}>Was this helpful?</span>
      <button onClick={() => submit("up")}
        style={{ background: "none", border: "1px solid #1e293b", borderRadius: 6, padding: "3px 10px", cursor: "pointer", fontSize: 14, color: "#94a3b8", lineHeight: 1 }}
        title="Helpful">{"\u{1F44D}"}</button>
      <button onClick={() => submit("down")}
        style={{ background: "none", border: "1px solid #1e293b", borderRadius: 6, padding: "3px 10px", cursor: "pointer", fontSize: 14, color: "#94a3b8", lineHeight: 1 }}
        title="Not helpful">{"\u{1F44E}"}</button>
    </div>
  );
};

const ChatMessage = ({ msg, explainOpen, toggleExplain, useMock }) => {
  const isUser = msg.role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 16, animation: "slideUp 0.3s ease" }}>
      <div style={{ maxWidth: "82%", minWidth: 120 }}>
        <div style={{ padding: "12px 16px", borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "#0f172a",
          color: isUser ? "#fff" : "#f8fafc", fontSize: 14, lineHeight: 1.6, boxShadow: "0 2px 8px rgba(0,0,0,0.2)" }}>
          {msg.text}
        </div>
        {!isUser && msg.apiData && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <ConfidenceMeter score={msg.apiData.confidence.score} level={msg.apiData.confidence.level} />
              <DataBadge meta={msg.apiData.response_meta} />
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 4, maxWidth: 400 }}>{msg.apiData.confidence.description}</div>
            <FeedbackButtons interactionId={msg.apiData.interaction_id} useMock={useMock} />
          </div>
        )}
        {!isUser && msg.apiData?.handoff?.recommended && (
          <div style={{ marginTop: 8, padding: 10, background: "#2d1515", border: "1px solid #991b1b", borderRadius: 8, fontSize: 12, color: "#fca5a5" }}>
            <strong>Human handoff:</strong> {msg.apiData.handoff.reasons.join("; ")}
            <button style={{ display: "block", marginTop: 6, padding: "6px 14px", background: "#dc2626", border: "none", borderRadius: 6, color: "#fff", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>Connect with Agent</button>
          </div>
        )}
        {!isUser && msg.apiData && <ExplainPanel data={msg.apiData} isOpen={explainOpen} toggle={toggleExplain} />}
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   ANALYTICS DASHBOARD (Feature 5)
   ═══════════════════════════════════════════════════════════════ */
const StatCard = ({ label, value, sub, color = "#f8fafc" }) => (
  <div style={{ flex: "1 1 180px", padding: 20, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 12 }}>
    <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4, textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
    <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>{sub}</div>}
  </div>
);

const IntentBar = ({ intent, count, max }) => {
  const pct = max > 0 ? (count / max) * 100 : 0;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
        <span style={{ color: "#cbd5e1" }}>{intent}</span>
        <span style={{ color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace" }}>{count}</span>
      </div>
      <div style={{ height: 6, background: "#0f172a", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "linear-gradient(90deg, #14b8a6, #3b82f6)", borderRadius: 3, transition: "width 0.6s ease" }} />
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   LOGIN PAGE
   ═══════════════════════════════════════════════════════════════ */
function LoginPage({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        onSuccess(data.token);
      } else {
        setError(data.error || "Invalid credentials");
      }
    } catch {
      setError("Could not reach server. Make sure the backend is running.");
    }
    setLoading(false);
  }

  return (
    <div style={{ minHeight: "100vh", background: "#020617", color: "#f8fafc", fontFamily: "'Inter', -apple-system, sans-serif", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        input:focus { outline: none; }
      `}</style>

      <div style={{ animation: "slideUp 0.3s ease", width: "100%", maxWidth: 400, padding: "0 24px" }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "linear-gradient(135deg, #14b8a6, #3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, margin: "0 auto 16px" }}>{"\u{1F916}"}</div>
          <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5 }}>Intelligent Support</div>
          <div style={{ fontSize: 13, color: "#64748b", marginTop: 6 }}>Sign in to access the platform</div>
        </div>

        {/* Card */}
        <div style={{ background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 16, padding: 32 }}>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Username</div>
              <input value={username} onChange={e => setUsername(e.target.value)} autoFocus required
                placeholder="Enter your username"
                style={{ width: "100%", padding: "11px 14px", borderRadius: 10, border: "1px solid #1e293b", background: "#0f172a", color: "#f8fafc", fontSize: 14, fontFamily: "inherit" }} />
            </div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Password</div>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required
                placeholder="Enter your password"
                style={{ width: "100%", padding: "11px 14px", borderRadius: 10, border: "1px solid #1e293b", background: "#0f172a", color: "#f8fafc", fontSize: 14, fontFamily: "inherit" }} />
            </div>
            {error && (
              <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 14px", color: "#f87171", fontSize: 13, marginBottom: 20 }}>
                {error}
              </div>
            )}
            <button type="submit" disabled={loading}
              style={{ width: "100%", padding: "12px", borderRadius: 10, border: "none", background: loading ? "#0f172a" : "linear-gradient(135deg, #2563eb, #3b82f6)", color: "#fff", fontSize: 15, fontWeight: 600, cursor: loading ? "default" : "pointer", letterSpacing: -0.2 }}>
              {loading ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>

        <div style={{ textAlign: "center", marginTop: 20, fontSize: 11, color: "#1e293b" }}>
          NLP &bull; Database Verified &bull; Confidence Scoring &bull; Explainable AI
        </div>
      </div>
    </div>
  );
}

const AnalyticsDashboard = ({ useMock, token, onAuthError }) => {
  const [data, setData] = useState(null);
  const [retrain, setRetrain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (useMock) {
      // Generate mock analytics
      await new Promise(r => setTimeout(r, 300));
      setData({
        total_queries: 142,
        handoff_count: 8,
        resolution_rate: 94.4,
        avg_confidence: 62.3,
        avg_feedback_rating: 4.1,
        total_feedback: 37,
        intent_distribution: [
          { detected_intent: "order_status", cnt: 42 },
          { detected_intent: "billing", cnt: 28 },
          { detected_intent: "refund", cnt: 22 },
          { detected_intent: "shipping", cnt: 18 },
          { detected_intent: "technical", cnt: 12 },
          { detected_intent: "subscription", cnt: 9 },
          { detected_intent: "account", cnt: 6 },
          { detected_intent: "greeting", cnt: 5 }
        ],
        recent_feedback: [
          { rating: 5, comment: "Got my order info immediately!", user_message: "Status of ORD-100001", detected_intent: "order_status", confidence_score: 82.1, created_at: "2026-03-23T10:15:00" },
          { rating: 1, comment: "Didn't understand my question", user_message: "quantum flux error in my order", detected_intent: "unknown", confidence_score: 12.0, retrain_flag: true, created_at: "2026-03-23T09:42:00" },
          { rating: 4, comment: null, user_message: "Refund for ORD-100002", detected_intent: "refund", confidence_score: 76.5, created_at: "2026-03-22T16:30:00" },
          { rating: 2, comment: "Had to rephrase multiple times", user_message: "my thing isnt working", detected_intent: "technical", confidence_score: 28.0, retrain_flag: true, created_at: "2026-03-22T14:20:00" },
          { rating: 5, comment: "Loved the transparency!", user_message: "Show me CUST-001004", detected_intent: "account", confidence_score: 88.3, created_at: "2026-03-22T11:05:00" }
        ],
        daily_volume: [
          { day: "2026-03-17", cnt: 18 }, { day: "2026-03-18", cnt: 22 },
          { day: "2026-03-19", cnt: 15 }, { day: "2026-03-20", cnt: 25 },
          { day: "2026-03-21", cnt: 20 }, { day: "2026-03-22", cnt: 28 },
          { day: "2026-03-23", cnt: 14 }
        ]
      });
      setRetrain({
        candidates: [
          { interaction_id: "mock-1", user_message: "quantum flux error in my order", detected_intent: "unknown", confidence_score: 12.0, rating: 1, comment: "Didn't understand my question", response_source: "fallback", created_at: "2026-03-23T09:42:00" },
          { interaction_id: "mock-2", user_message: "my thing isnt working", detected_intent: "technical", confidence_score: 28.0, rating: 2, comment: "Had to rephrase multiple times", response_source: "technical_help", created_at: "2026-03-22T14:20:00" }
        ],
        count: 2
      });
      setLoading(false);
      return;
    }
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const [analyticsRes, retrainRes] = await Promise.all([
        fetch(`${API_URL}/analytics`, { headers }),
        fetch(`${API_URL}/retrain_feedback`, { headers })
      ]);
      if (analyticsRes.status === 401) { onAuthError(); return; }
      if (!analyticsRes.ok) throw new Error("Analytics endpoint unavailable");
      setData(await analyticsRes.json());
      if (retrainRes.ok) setRetrain(await retrainRes.json());
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }, [useMock, token, onAuthError]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
        Loading analytics...
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "#f87171" }}>
        <div>{error}</div>
        <button onClick={fetchData} style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #1e293b", background: "#0f172a", color: "#f8fafc", cursor: "pointer", fontSize: 13 }}>Retry</button>
      </div>
    );
  }
  if (!data) return null;

  const maxIntent = data.intent_distribution.length > 0 ? data.intent_distribution[0].cnt : 1;
  const dailyMax = data.daily_volume.length > 0 ? Math.max(...data.daily_volume.map(d => d.cnt)) : 1;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
      {/* KPI Cards */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        <StatCard label="Total Queries" value={data.total_queries} />
        <StatCard label="Resolution Rate" value={`${data.resolution_rate}%`} sub={`${data.handoff_count} handoffs`} color="#10b981" />
        <StatCard label="Avg Confidence" value={`${data.avg_confidence}%`} color={data.avg_confidence >= 60 ? "#10b981" : data.avg_confidence >= 40 ? "#f59e0b" : "#ef4444"} />
        <StatCard label="Avg Rating" value={data.avg_feedback_rating.toFixed(1)} sub={`${data.total_feedback} reviews`} color="#f59e0b" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
        {/* Intent Distribution */}
        <div style={{ padding: 20, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 12 }}>
          <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600, color: "#f8fafc" }}>Query Trends (Top Intents)</h3>
          {data.intent_distribution.map((d, i) => (
            <IntentBar key={i} intent={d.detected_intent} count={d.cnt} max={maxIntent} />
          ))}
        </div>

        {/* Daily Volume Chart */}
        <div style={{ padding: 20, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 12 }}>
          <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600, color: "#f8fafc" }}>Daily Query Volume</h3>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 140 }}>
            {data.daily_volume.map((d, i) => (
              <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                <div style={{ fontSize: 10, color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace" }}>{d.cnt}</div>
                <div style={{ width: "100%", background: "linear-gradient(180deg, #14b8a6, #1e40af)", borderRadius: "3px 3px 0 0", height: `${(d.cnt / dailyMax) * 110}px`, transition: "height 0.5s ease", minHeight: 4 }} />
                <div style={{ fontSize: 9, color: "#475569", whiteSpace: "nowrap" }}>{String(d.day).slice(5)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Feedback */}
      <div style={{ padding: 20, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 12, marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600, color: "#f8fafc" }}>Recent Feedback</h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                {["Rating", "User Message", "Intent", "Confidence", "Comment", "Time"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "#64748b", fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.recent_feedback.map((fb, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #0b0f19" }}>
                  <td style={{ padding: "8px 10px" }}>
                    <span style={{ display: "inline-block", width: 28, textAlign: "center", padding: "2px 0", borderRadius: 4, fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
                      background: fb.rating >= 4 ? "#052e16" : fb.rating <= 2 ? "#350a0a" : "#172554",
                      color: fb.rating >= 4 ? "#4ade80" : fb.rating <= 2 ? "#f87171" : "#60a5fa" }}>
                      {fb.rating}
                    </span>
                  </td>
                  <td style={{ padding: "8px 10px", color: "#cbd5e1", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{fb.user_message}</td>
                  <td style={{ padding: "8px 10px", color: "#94a3b8" }}>{fb.detected_intent}</td>
                  <td style={{ padding: "8px 10px", color: "#94a3b8", fontFamily: "'JetBrains Mono', monospace" }}>{fb.confidence_score}%</td>
                  <td style={{ padding: "8px 10px", color: "#64748b", fontStyle: fb.comment ? "normal" : "italic" }}>{fb.comment || "—"}</td>
                  <td style={{ padding: "8px 10px", color: "#475569", whiteSpace: "nowrap" }}>{fb.created_at ? new Date(fb.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Retrain Candidates (Feature 6) */}
      {retrain && retrain.candidates && retrain.candidates.length > 0 && (
        <div style={{ padding: 20, background: "#1a0a00", border: "1px solid #78350f", borderRadius: 12 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: 14, fontWeight: 600, color: "#fbbf24" }}>Needs Retraining ({retrain.count})</h3>
          <p style={{ margin: "0 0 14px", fontSize: 12, color: "#a16207" }}>These interactions received poor ratings and are flagged for NLP improvement.</p>
          {retrain.candidates.map((c, i) => (
            <div key={i} style={{ padding: 12, background: "#0b0f19", border: "1px solid #1e293b", borderRadius: 8, marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 12, color: "#f8fafc", fontWeight: 500 }}>"{c.user_message}"</span>
                <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: "#350a0a", color: "#f87171", fontWeight: 600 }}>
                  Rating: {c.rating}/5
                </span>
              </div>
              <div style={{ display: "flex", gap: 12, fontSize: 11, color: "#64748b" }}>
                <span>Intent: <strong style={{ color: "#94a3b8" }}>{c.detected_intent}</strong></span>
                <span>Confidence: <strong style={{ color: "#94a3b8" }}>{c.confidence_score}%</strong></span>
                <span>Source: <strong style={{ color: "#94a3b8" }}>{c.response_source}</strong></span>
              </div>
              {c.comment && <div style={{ marginTop: 4, fontSize: 11, color: "#a16207", fontStyle: "italic" }}>"{c.comment}"</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════ */
export default function App() {
  const [messages, setMessages] = useState([
    { id: 0, role: "bot", text: "Hello! I'm your AI support assistant, your AI support assistant with Transparent Confidence Scoring. I can look up orders, check refunds, review subscriptions, and more. Try: ORD-100001, CUST-001004, or TXN-200002!", apiData: null }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [explainStates, setExplainStates] = useState({});
  const [useMock, setUseMock] = useState(true);
  const [view, setView] = useState("chat"); // "chat" | "dashboard"
  const [token, setToken] = useState(() => localStorage.getItem("admin_token") || null);
  const isAuthenticated = !!token;
  const [sessionId] = useState(() => crypto.randomUUID());
  const bottomRef = useRef(null);

  function handleLoginSuccess(newToken) {
    localStorage.setItem("admin_token", newToken);
    setToken(newToken);
    setView("chat");
  }
  function handleLogout() {
    localStorage.removeItem("admin_token");
    setToken(null);
  }
  function handleAuthError() {
    localStorage.removeItem("admin_token");
    setToken(null);
  }

  if (!isAuthenticated) return <LoginPage onSuccess={handleLoginSuccess} />;

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { id: Date.now(), role: "user", text: input.trim() };
    setMessages(p => [...p, userMsg]);
    setInput("");
    setLoading(true);
    try {
      let data;
      if (useMock) {
        await new Promise(r => setTimeout(r, 400 + Math.random() * 400));
        data = mockAPI(userMsg.text, messages);
      } else {
        const res = await fetch(`${API_URL}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: userMsg.text, session_id: sessionId }) });
        data = await res.json();
      }
      setMessages(p => [...p, { id: Date.now() + 1, role: "bot", text: data.response, apiData: data }]);
    } catch {
      setMessages(p => [...p, { id: Date.now() + 1, role: "bot", text: "Error connecting to the server. Please try again.", apiData: null }]);
    }
    setLoading(false);
  };

  const toggleExplain = (id) => setExplainStates(p => ({ ...p, [id]: !p[id] }));

  const quickPrompts = [
    "What is the status of ORD-100001?",
    "I want a refund for ORD-100002",
    "Where is my order ORD-100003?",
    "Show me customer CUST-001004",
    "Check transaction TXN-200001",
    "I'm frustrated, my package is late"
  ];

  return (
    <div style={{ minHeight: "100vh", background: "#020617", color: "#f8fafc", fontFamily: "'Inter', -apple-system, sans-serif", display: "flex", flexDirection: "column" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
        input:focus { outline: none; } button:hover { opacity: 0.9; }
      `}</style>

      {/* Header */}
      <div style={{ padding: "16px 24px", borderBottom: "1px solid #1e293b", background: "linear-gradient(180deg, #0f172a, #020617)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: "linear-gradient(135deg, #14b8a6, #3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>{"\u{1F916}"}</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3 }}>Intelligent Support</div>
            <div style={{ fontSize: 11, color: "#64748b" }}>NLP &bull; Database Verified &bull; Confidence Scoring &bull; Explainable AI</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* View Toggle */}
          <div style={{ display: "flex", background: "#0f172a", borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b" }}>
            <button onClick={() => setView("chat")}
              style={{ padding: "6px 14px", fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer",
                background: view === "chat" ? "#14b8a6" : "transparent", color: view === "chat" ? "#fff" : "#64748b" }}>
              Chat
            </button>
            <button onClick={() => setView("dashboard")}
              style={{ padding: "6px 14px", fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer",
                background: view === "dashboard" ? "#14b8a6" : "transparent", color: view === "dashboard" ? "#fff" : "#64748b" }}>
              Dashboard
            </button>
          </div>
          {isAuthenticated && (
            <button onClick={handleLogout}
              style={{ padding: "6px 12px", fontSize: 12, fontWeight: 600, borderRadius: 6, border: "1px solid #1e293b", background: "transparent", color: "#94a3b8", cursor: "pointer" }}>
              Logout
            </button>
          )}
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b", cursor: "pointer" }}>
            <input type="checkbox" checked={!useMock} onChange={e => setUseMock(!e.target.checked)} style={{ accentColor: "#14b8a6" }} />
            Live API
          </label>
        </div>
      </div>

      {view === "chat" ? (
        <>
          {/* Quick Prompts */}
          <div style={{ padding: "10px 24px", display: "flex", gap: 8, overflowX: "auto", borderBottom: "1px solid #0b0f19" }}>
            {quickPrompts.map((p, i) => (
              <button key={i} onClick={() => setInput(p)} style={{ whiteSpace: "nowrap", padding: "6px 14px", borderRadius: 20, border: "1px solid #1e293b", background: "#0b0f19", color: "#94a3b8", fontSize: 12, cursor: "pointer", flexShrink: 0 }}>{p}</button>
            ))}
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
            {messages.map(msg => (
              <ChatMessage key={msg.id} msg={msg} explainOpen={explainStates[msg.id] || false} toggleExplain={() => toggleExplain(msg.id)} useMock={useMock} />
            ))}
            {loading && (
              <div style={{ display: "flex", gap: 6, padding: 16 }}>
                {[0, 1, 2].map(i => <div key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: "#14b8a6", animation: `pulse 1s ease infinite ${i * 0.15}s` }} />)}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ padding: "16px 24px", borderTop: "1px solid #1e293b", background: "#0b0f19" }}>
            <div style={{ display: "flex", gap: 10, maxWidth: 800, margin: "0 auto" }}>
              <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
                placeholder="Ask about an order (ORD-100001), customer (CUST-001001), or describe your issue..."
                style={{ flex: 1, padding: "12px 18px", borderRadius: 12, border: "1px solid #1e293b", background: "#0f172a", color: "#f8fafc", fontSize: 14, fontFamily: "inherit" }} />
              <button onClick={send} disabled={loading || !input.trim()}
                style={{ padding: "12px 24px", borderRadius: 12, border: "none", background: loading || !input.trim() ? "#0f172a" : "linear-gradient(135deg, #2563eb, #3b82f6)", color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || !input.trim() ? "default" : "pointer" }}>
                Send
              </button>
            </div>
            <div style={{ textAlign: "center", marginTop: 8, fontSize: 11, color: "#475569" }}>
              Transparent Confidence Scoring &bull; Database Verified Responses &bull; Click "Show AI Reasoning" for full breakdown
            </div>
          </div>
        </>
      ) : (
        <AnalyticsDashboard useMock={useMock} token={token} onAuthError={handleAuthError} />
      )}

    </div>
  );
}
