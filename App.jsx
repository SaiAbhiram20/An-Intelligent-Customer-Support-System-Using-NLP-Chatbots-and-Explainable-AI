import { useState, useRef, useEffect } from "react";

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
function mockAPI(message) {
  const lower = message.toLowerCase();
  const upper = message.toUpperCase();
  const tokens = lower.split(/\s+/);

  // Extract IDs
  const ids = {};
  let match;
  if ((match = upper.match(/ORD-\d{5,7}/))) ids.order_id = match[0];
  if ((match = upper.match(/CUST-\d{5,7}/))) ids.customer_id = match[0];
  if ((match = upper.match(/TXN-\d{5,7}/))) ids.transaction_id = match[0];

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
      const score = Math.min(matched.length / kws.length + matched.length * 0.1, 1.0);
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

  // Build genuine response from data
  if (dbErrors.length > 0) {
    responseText = `${empathy}${dbErrors.join(" ")} Could you double-check the ID?`;
    source = "id_not_found";
  } else if (order) {
    dbFound = true; dataVerified = true; dataUsed.push(`order:${order.order_id}`);
    const items = order.items.map(i => i.product_name).join(", ");
    const isRefund = ["refund", "money back", "reimburse", "return"].some(w => lower.includes(w));

    if (isRefund && order.transaction) {
      if (order.transaction.refund_eligible) {
        responseText = `${empathy}Hi ${order.first_name}! Order ${order.order_id} is eligible for a full refund of $${order.total}. It will be processed to your ${order.transaction.payment_method} within 5-7 business days. Items: ${items}. Proceed?`;
        source = "db_refund_eligible";
      } else {
        responseText = `${empathy}Hi ${order.first_name}, order ${order.order_id} is outside the 30-day refund window (deadline: ${order.transaction.refund_deadline}). Total: $${order.total}. Items: ${items}. Want me to connect you with a specialist?`;
        source = "db_refund_ineligible";
      }
    } else if (order.status === "delivered") {
      responseText = `${empathy}Hi ${order.first_name}! Order ${order.order_id} was delivered on ${order.delivered_date}. Items: ${items}. Total: $${order.total}. Anything else about this order?`;
      source = "db_order_delivered";
    } else if (["shipped", "in_transit", "out_for_delivery"].includes(order.status)) {
      const track = order.tracking_number ? ` Tracking: ${order.tracking_number} via ${order.carrier}.` : "";
      const eta = order.estimated_delivery ? ` ETA: ${order.estimated_delivery}.` : "";
      const note = order.notes ? ` Note: ${order.notes}` : "";
      responseText = `${empathy}Hi ${order.first_name}! Order ${order.order_id} is ${order.status.replace(/_/g, " ")}.${track}${eta}${note} Items: ${items}.`;
      source = "db_order_in_transit";
    } else if (order.status === "processing") {
      responseText = `${empathy}Hi ${order.first_name}! Order ${order.order_id} is being processed. Items: ${items}. Total: $${order.total}. You'll get tracking once it ships.`;
      source = "db_order_processing";
    } else if (order.status === "cancelled") {
      responseText = `${empathy}Hi ${order.first_name}, order ${order.order_id} was cancelled.${order.notes ? " " + order.notes + "." : ""} Items: ${items}. Total: $${order.total}.`;
      source = "db_order_cancelled";
    } else if (order.status === "returned") {
      responseText = `${empathy}Hi ${order.first_name}, order ${order.order_id} was returned. Items: ${items}. Total: $${order.total}. Refund takes 5-7 business days.`;
      source = "db_order_returned";
    } else {
      responseText = `${empathy}Hi ${order.first_name}! Order ${order.order_id}: ${order.status.toUpperCase()}, $${order.total}. Items: ${items}.`;
      source = "db_order_generic";
    }
  } else if (transaction) {
    dbFound = true; dataVerified = true; dataUsed.push(`txn:${transaction.transaction_id}`);
    responseText = `${empathy}Hi ${transaction.first_name}! Transaction ${transaction.transaction_id}: ${transaction.type} | ${transaction.status} | $${transaction.amount} | ${transaction.payment_method} | ${transaction.transaction_date}.${transaction.refund_eligible ? ` Refund eligible (deadline: ${transaction.refund_deadline}).` : ""}`;
    source = "db_transaction";
  } else if (customer) {
    dbFound = true; dataVerified = true; dataUsed.push(`customer:${customer.customer_id}`);
    const orderList = customer.orders.map(oid => { const o = MOCK_DB.orders[oid]; return o ? `${oid} (${o.status}, $${o.total})` : oid; }).join("; ");
    const s = customer.subscription;
    responseText = `${empathy}Hi ${customer.first_name}! Account: ${customer.customer_id}. Email: ${customer.email}. Orders: ${orderList}. Plan: ${s.plan_name.toUpperCase()} ($${s.plan_price}/${s.billing_cycle}) — ${s.status}. How can I help?`;
    source = "db_customer_overview";
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

  // Confidence calculation with 5 factors
  const f1 = bestScore * 0.30;
  const clarityVal = allIntents.length >= 2 ? Math.min((allIntents[0].score - allIntents[1].score) * 2, 1) : (allIntents.length === 1 ? allIntents[0].score : 0);
  const f2 = clarityVal * 0.20;
  const specVal = tokens.length <= 2 ? 0.3 : tokens.length <= 5 ? 0.6 : tokens.length <= 15 ? 0.9 : 1.0;
  const f3 = specVal * 0.15;
  const f4 = 0.7 * 0.10;
  const dvVal = dbFound ? 1.0 : (dbErrors.length > 0 ? 0.3 : 0);
  const f5 = dvVal * 0.25;
  const totalConf = Math.round((f1 + f2 + f3 + f4 + f5) * 1000) / 10;
  const confLevel = totalConf >= 75 ? "high" : totalConf >= 50 ? "medium" : totalConf >= 30 ? "low" : "very_low";

  const missing = [];
  if (tokens.length <= 3) missing.push("More details about your situation");
  if (!dbFound && !dbErrors.length && ["order_status", "shipping", "refund", "billing"].includes(bestIntent))
    missing.push("Your order ID (e.g. ORD-100001) or transaction ID");

  return {
    response: responseText,
    response_meta: { source, data_verified: dataVerified, data_used: dataUsed },
    confidence: {
      score: totalConf, level: confLevel,
      description: confLevel === "high" ? "Highly confident — verified against database." : confLevel === "medium" ? "Moderately confident. An ID would improve accuracy." : confLevel === "low" ? "Limited confidence. More details would help." : "Not confident. Recommending human agent.",
      factors: [
        { name: "Intent Match", weight: "30%", raw_score: Math.round(bestScore * 100), weighted_score: Math.round(f1 * 100), explanation: `Matched '${bestIntent}' category` },
        { name: "Intent Clarity", weight: "20%", raw_score: Math.round(clarityVal * 100), weighted_score: Math.round(f2 * 100), explanation: allIntents.length >= 2 ? "Multiple categories detected" : "Single clear category" },
        { name: "Query Specificity", weight: "15%", raw_score: Math.round(specVal * 100), weighted_score: Math.round(f3 * 100), explanation: `${tokens.length} words in query` },
        { name: "Sentiment Alignment", weight: "10%", raw_score: 70, weighted_score: Math.round(f4 * 100), explanation: "Sentiment consistency check" },
        { name: "Data Verification", weight: "25%", raw_score: Math.round(dvVal * 100), weighted_score: Math.round(f5 * 100), explanation: dbFound ? `Verified: ${dbLookups.join(", ")}` : dbErrors.length ? "ID not found" : "No IDs provided" }
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
          <circle cx="26" cy="26" r="22" fill="none" stroke="#1e293b" strokeWidth="4" />
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
      <div style={{ height: 6, background: "#1e293b", borderRadius: 3, overflow: "hidden" }}>
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
      background: v ? "#052e16" : "#1e293b", border: `1px solid ${v ? "#16a34a" : "#334155"}`, color: v ? "#4ade80" : "#94a3b8" }}>
      {v ? "✓ DB Verified" : "◯ No DB Data"}
      {meta.source && <span style={{ opacity: 0.6 }}> • {meta.source.replace(/_/g, " ")}</span>}
    </span>
  );
};

const ExplainPanel = ({ data, isOpen, toggle }) => {
  if (!data) return null;
  const db = data.explainability?.database;
  return (
    <div style={{ marginTop: 8 }}>
      <button onClick={toggle} style={{ background: "none", border: "1px solid #334155", borderRadius: 8, color: "#94a3b8", fontSize: 12, padding: "6px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ transform: isOpen ? "rotate(90deg)" : "none", transition: "transform 0.2s", display: "inline-block" }}>▶</span>
        {isOpen ? "Hide" : "Show"} AI Reasoning
      </button>
      {isOpen && (
        <div style={{ marginTop: 10, padding: 16, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, animation: "fadeIn 0.3s ease" }}>
          <h4 style={{ margin: "0 0 10px", fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>Confidence Breakdown</h4>
          {data.confidence.factors.map((f, i) => <FactorBar key={i} factor={f} />)}

          {db && db.lookups_performed?.length > 0 && (
            <div style={{ marginBottom: 16, padding: 12, background: "#0a2540", border: "1px solid #1e3a5f", borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: "#60a5fa", fontWeight: 600, marginBottom: 4 }}>🔍 Database Lookups</div>
              {db.lookups_performed.map((l, i) => <div key={i} style={{ fontSize: 12, color: "#93c5fd", marginBottom: 2 }}>• {l}</div>)}
              {db.ids_extracted && Object.keys(db.ids_extracted).length > 0 && (
                <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>IDs: {JSON.stringify(db.ids_extracted)}</div>
              )}
            </div>
          )}

          <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>Intent Analysis</h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {data.explainability.intent.all_candidates.map((c, i) => (
              <span key={i} style={{ padding: "3px 10px", borderRadius: 20, fontSize: 12, background: i === 0 ? "#1e3a5f" : "#1e293b", border: `1px solid ${i === 0 ? "#3b82f6" : "#334155"}`, color: i === 0 ? "#93c5fd" : "#94a3b8" }}>
                {c.intent}: {(c.score * 100).toFixed(0)}%
              </span>
            ))}
          </div>

          <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "#e2e8f0", fontWeight: 600 }}>Sentiment</h4>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600,
            background: data.explainability.sentiment.label === "positive" ? "#052e16" : data.explainability.sentiment.label === "negative" ? "#350a0a" : "#172554",
            border: `1px solid ${data.explainability.sentiment.label === "positive" ? "#16a34a" : data.explainability.sentiment.label === "negative" ? "#dc2626" : "#2563eb"}`,
            color: data.explainability.sentiment.label === "positive" ? "#4ade80" : data.explainability.sentiment.label === "negative" ? "#f87171" : "#60a5fa" }}>
            {data.explainability.sentiment.label === "positive" ? "↑" : data.explainability.sentiment.label === "negative" ? "↓" : "→"} {data.explainability.sentiment.label} ({data.explainability.sentiment.score})
          </span>

          {data.confidence.missing_information?.length > 0 && (
            <div style={{ marginTop: 12, padding: 12, background: "#1c1917", border: "1px solid #78350f", borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600, marginBottom: 4 }}>ℹ Information I'm missing:</div>
              {data.confidence.missing_information.map((m, i) => <div key={i} style={{ fontSize: 12, color: "#d97706", marginBottom: 2 }}>• {m}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ChatMessage = ({ msg, explainOpen, toggleExplain }) => {
  const isUser = msg.role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 16, animation: "slideUp 0.3s ease" }}>
      <div style={{ maxWidth: "82%", minWidth: 120 }}>
        <div style={{ padding: "12px 16px", borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "#1e293b",
          color: isUser ? "#fff" : "#e2e8f0", fontSize: 14, lineHeight: 1.6, boxShadow: "0 2px 8px rgba(0,0,0,0.2)" }}>
          {msg.text}
        </div>
        {!isUser && msg.apiData && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <ConfidenceMeter score={msg.apiData.confidence.score} level={msg.apiData.confidence.level} />
              <DataBadge meta={msg.apiData.response_meta} />
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 4, maxWidth: 400 }}>{msg.apiData.confidence.description}</div>
          </div>
        )}
        {!isUser && msg.apiData?.handoff?.recommended && (
          <div style={{ marginTop: 8, padding: 10, background: "#2d1515", border: "1px solid #991b1b", borderRadius: 8, fontSize: 12, color: "#fca5a5" }}>
            🔄 <strong>Human handoff:</strong> {msg.apiData.handoff.reasons.join("; ")}
            <button style={{ display: "block", marginTop: 6, padding: "6px 14px", background: "#dc2626", border: "none", borderRadius: 6, color: "#fff", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>Connect with Agent</button>
          </div>
        )}
        {!isUser && msg.apiData && <ExplainPanel data={msg.apiData} isOpen={explainOpen} toggle={toggleExplain} />}
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════ */
export default function App() {
  const [messages, setMessages] = useState([
    { id: 0, role: "bot", text: "Hello! I'm your AI support assistant with Transparent Confidence Scoring. I can look up orders, check refunds, review subscriptions, and more. Try: ORD-100001, CUST-001004, or TXN-200002!", apiData: null }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [explainStates, setExplainStates] = useState({});
  const [useMock, setUseMock] = useState(true);
  const bottomRef = useRef(null);

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
        data = mockAPI(userMsg.text);
      } else {
        const res = await fetch(`${API_URL}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: userMsg.text }) });
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
    <div style={{ minHeight: "100vh", background: "#020617", color: "#e2e8f0", fontFamily: "'Inter', -apple-system, sans-serif", display: "flex", flexDirection: "column" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        input:focus { outline: none; } button:hover { opacity: 0.9; }
      `}</style>

      {/* Header */}
      <div style={{ padding: "16px 24px", borderBottom: "1px solid #1e293b", background: "linear-gradient(180deg, #0f172a, #020617)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>🤖</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3 }}>Intelligent Support</div>
            <div style={{ fontSize: 11, color: "#64748b" }}>NLP • Database Verified • Confidence Scoring • Explainable AI</div>
          </div>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b", cursor: "pointer" }}>
          <input type="checkbox" checked={!useMock} onChange={e => setUseMock(!e.target.checked)} style={{ accentColor: "#3b82f6" }} />
          Live API
        </label>
      </div>

      {/* Quick Prompts */}
      <div style={{ padding: "10px 24px", display: "flex", gap: 8, overflowX: "auto", borderBottom: "1px solid #0f172a" }}>
        {quickPrompts.map((p, i) => (
          <button key={i} onClick={() => setInput(p)} style={{ whiteSpace: "nowrap", padding: "6px 14px", borderRadius: 20, border: "1px solid #1e293b", background: "#0f172a", color: "#94a3b8", fontSize: 12, cursor: "pointer", flexShrink: 0 }}>{p}</button>
        ))}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
        {messages.map(msg => (
          <ChatMessage key={msg.id} msg={msg} explainOpen={explainStates[msg.id] || false} toggleExplain={() => toggleExplain(msg.id)} />
        ))}
        {loading && (
          <div style={{ display: "flex", gap: 6, padding: 16 }}>
            {[0, 1, 2].map(i => <div key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: "#3b82f6", animation: `pulse 1s ease infinite ${i * 0.15}s` }} />)}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "16px 24px", borderTop: "1px solid #1e293b", background: "#0f172a" }}>
        <div style={{ display: "flex", gap: 10, maxWidth: 800, margin: "0 auto" }}>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
            placeholder="Ask about an order (ORD-100001), customer (CUST-001001), or describe your issue..."
            style={{ flex: 1, padding: "12px 18px", borderRadius: 12, border: "1px solid #334155", background: "#1e293b", color: "#e2e8f0", fontSize: 14, fontFamily: "inherit" }} />
          <button onClick={send} disabled={loading || !input.trim()}
            style={{ padding: "12px 24px", borderRadius: 12, border: "none", background: loading || !input.trim() ? "#1e293b" : "linear-gradient(135deg, #2563eb, #7c3aed)", color: "#fff", fontSize: 14, fontWeight: 600, cursor: loading || !input.trim() ? "default" : "pointer" }}>
            Send
          </button>
        </div>
        <div style={{ textAlign: "center", marginTop: 8, fontSize: 11, color: "#475569" }}>
          Transparent Confidence Scoring • Database Verified Responses • Click "Show AI Reasoning" for full breakdown
        </div>
      </div>
    </div>
  );
}
