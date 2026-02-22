"""
═══════════════════════════════════════════════════════════════════
  Intelligent Customer Support System
  NLP + Chatbots + Explainable AI + Transparent Confidence Scoring
  
  Key Feature: Genuine responses generated from real database data,
  NOT pre-written canned responses.
═══════════════════════════════════════════════════════════════════
"""

import os
import re
import json
import uuid
import logging
from datetime import datetime, date
from decimal import Decimal
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from db_service import (
    init_db, close_db,
    get_customer_by_id, get_customer_by_email,
    get_order_by_id, get_orders_by_customer,
    get_transaction_by_id, get_transactions_by_customer,
    get_subscription_by_id, get_subscription_by_customer,
    check_refund_eligibility
)

# ─── App ──────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

db_connected = False

@app.before_request
def ensure_db():
    global db_connected
    if not db_connected:
        db_connected = init_db()

# ─── JSON serializer for dates/decimals ───────────────────────
class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

app.json_encoder = CustomEncoder


# ═══════════════════════════════════════════════════════════════
# SENTIMENT LEXICONS
# ═══════════════════════════════════════════════════════════════

POSITIVE_WORDS = {
    "good","great","excellent","amazing","wonderful","fantastic","love","happy",
    "pleased","satisfied","awesome","perfect","thanks","thank","helpful",
    "appreciate","nice","best","easy","quick","fast","smooth","resolved","fixed"
}
NEGATIVE_WORDS = {
    "bad","terrible","awful","horrible","hate","angry","frustrated","annoyed",
    "disappointed","upset","worst","slow","broken","useless","ridiculous",
    "unacceptable","furious","disgusted","pathetic","incompetent","scam",
    "stupid","trash","garbage","ruined","never","impossible"
}
INTENSIFIERS = {"very","extremely","absolutely","totally","completely","really","incredibly","so","quite","utterly"}
NEGATORS = {"not","no","never","neither","nor","don't","doesn't","didn't","won't","can't","couldn't","shouldn't","wouldn't","isn't","aren't","wasn't","weren't"}


# ═══════════════════════════════════════════════════════════════
# NLP PIPELINE
# ═══════════════════════════════════════════════════════════════

def preprocess(text: str) -> dict:
    cleaned = text.lower().strip()
    cleaned_alpha = re.sub(r'[^\w\s\'-]', ' ', cleaned)
    tokens = cleaned_alpha.split()
    return {"original": text, "cleaned": cleaned, "tokens": tokens, "token_count": len(tokens)}


def analyze_sentiment(proc: dict) -> dict:
    tokens = proc["tokens"]
    pos_score = neg_score = 0
    pos_matches, neg_matches, explanations = [], [], []

    for i, tok in enumerate(tokens):
        negated = any(tokens[j] in NEGATORS for j in range(max(0, i-2), i))
        intensified = any(tokens[j] in INTENSIFIERS for j in range(max(0, i-1), i))
        mult = 1.5 if intensified else 1.0

        if tok in POSITIVE_WORDS:
            if negated:
                neg_score += 0.5 * mult; neg_matches.append(f"not {tok}")
                explanations.append(f"Negated positive: 'not {tok}'")
            else:
                pos_score += 1.0 * mult; pos_matches.append(tok)
                explanations.append(f"Positive: '{tok}'" + (" (intensified)" if intensified else ""))
        elif tok in NEGATIVE_WORDS:
            if negated:
                pos_score += 0.3 * mult; pos_matches.append(f"not {tok}")
                explanations.append(f"Negated negative: 'not {tok}' (mild positive)")
            else:
                neg_score += 1.0 * mult; neg_matches.append(tok)
                explanations.append(f"Negative: '{tok}'" + (" (intensified)" if intensified else ""))

    total = pos_score + neg_score
    if total == 0:
        score, label = 0.0, "neutral"
        explanations.append("No strong sentiment indicators.")
    else:
        score = (pos_score - neg_score) / total
        label = "positive" if score > 0.2 else ("negative" if score < -0.2 else "neutral")

    return {
        "label": label, "score": round(score, 3),
        "intensity": round(max(pos_score, neg_score) / max(len(tokens), 1), 3),
        "positive_matches": pos_matches, "negative_matches": neg_matches,
        "explanations": explanations
    }


# ─── Intent Classification ───────────────────────────────────

INTENT_KEYWORDS = {
    "billing":   ["bill","charge","invoice","payment","price","cost","fee","subscription","plan","refund","money","overcharged","pricing"],
    "technical": ["bug","error","crash","slow","broken","fix","issue","problem","not working","glitch","loading","fail","login","password","reset","down"],
    "account":   ["account","profile","settings","email","name","delete","close","update","change","personal","data","privacy","deactivate"],
    "shipping":  ["ship","deliver","track","order","package","arrive","return","exchange","lost","damaged","address","where is","dispatch"],
    "order_status": ["order","status","where","tracking","shipped","delivered","processing","cancelled","when","eta","estimated"],
    "refund":    ["refund","money back","return money","reimburse","credit","chargeback"],
    "subscription": ["subscription","plan","upgrade","downgrade","cancel subscription","renew","billing cycle","monthly","annual"],
    "greeting":  ["hello","hi","help","hey","good morning","good afternoon","good evening"],
    "thanks":    ["thanks","thank you","appreciate","great help","wonderful"],
    "farewell":  ["bye","goodbye","see you","that's all","done","nothing else"]
}

def classify_intent(proc: dict) -> dict:
    tokens = set(proc["tokens"])
    text = proc["cleaned"]
    scores = {}
    match_details = {}

    for category, keywords in INTENT_KEYWORDS.items():
        matched = []
        for kw in keywords:
            if ' ' in kw:
                if kw in text: matched.append(kw)
            elif kw in tokens:
                matched.append(kw)
            else:
                for t in tokens:
                    if (t.startswith(kw) or kw.startswith(t)) and abs(len(t)-len(kw)) <= 3:
                        matched.append(kw); break

        if matched:
            coverage = len(matched) / len(keywords)
            bonus = min(len(matched) * 0.1, 0.3)
            scores[category] = round(min(coverage + bonus, 1.0), 3)
            match_details[category] = matched

    if not scores:
        return {"primary_intent": "unknown", "confidence": 0.0, "all_intents": [],
                "matched_keywords": {}, "explanations": ["No keywords matched any category."]}

    sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    explanations = [f"'{cat}': matched [{', '.join(match_details[cat])}] → {s:.0%}" for cat, s in sorted_intents]

    return {
        "primary_intent": sorted_intents[0][0],
        "confidence": sorted_intents[0][1],
        "all_intents": [{"intent": i, "score": s} for i, s in sorted_intents],
        "matched_keywords": match_details,
        "explanations": explanations
    }


# ─── ID Extraction ────────────────────────────────────────────

def extract_ids(text: str) -> dict:
    """Pull order/customer/transaction/subscription IDs from free text."""
    ids = {}
    patterns = {
        "order_id":        r'(ORD-\d{5,7})',
        "customer_id":     r'(CUST-\d{5,7})',
        "transaction_id":  r'(TXN-\d{5,7})',
        "subscription_id": r'(SUB-\d{5,7})'
    }
    upper = text.upper()
    for key, pat in patterns.items():
        m = re.search(pat, upper)
        if m:
            ids[key] = m.group(1)
    return ids


# ─── Database Context Gathering ───────────────────────────────

def gather_db_context(ids: dict, intent: str) -> dict:
    """Look up all referenced entities from the database."""
    ctx = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}

    if "order_id" in ids:
        ctx["lookups_performed"].append(f"Looked up order {ids['order_id']}")
        order = get_order_by_id(ids["order_id"])
        if order:
            ctx["entities"]["order"] = order
            ctx["found"] = True
        else:
            ctx["errors"].append(f"Order {ids['order_id']} was not found in our system.")

    if "customer_id" in ids:
        ctx["lookups_performed"].append(f"Looked up customer {ids['customer_id']}")
        cust = get_customer_by_id(ids["customer_id"])
        if cust:
            ctx["entities"]["customer"] = cust
            ctx["found"] = True
            # Also grab their recent orders & subscription
            orders = get_orders_by_customer(ids["customer_id"])
            if orders:
                ctx["entities"]["customer_orders"] = orders
            sub = get_subscription_by_customer(ids["customer_id"])
            if sub:
                ctx["entities"]["subscription"] = sub
        else:
            ctx["errors"].append(f"Customer {ids['customer_id']} was not found.")

    if "transaction_id" in ids:
        ctx["lookups_performed"].append(f"Looked up transaction {ids['transaction_id']}")
        txn = get_transaction_by_id(ids["transaction_id"])
        if txn:
            ctx["entities"]["transaction"] = txn
            ctx["found"] = True
        else:
            ctx["errors"].append(f"Transaction {ids['transaction_id']} was not found.")

    if "subscription_id" in ids:
        ctx["lookups_performed"].append(f"Looked up subscription {ids['subscription_id']}")
        sub = get_subscription_by_id(ids["subscription_id"])
        if sub:
            ctx["entities"]["subscription"] = sub
            ctx["found"] = True
        else:
            ctx["errors"].append(f"Subscription {ids['subscription_id']} was not found.")

    # If we have an order and intent is refund, check eligibility
    if "order" in ctx["entities"] and intent in ("refund", "billing"):
        refund_info = check_refund_eligibility(ids.get("order_id", ""))
        if refund_info:
            ctx["entities"]["refund_check"] = refund_info

    return ctx


# ═══════════════════════════════════════════════════════════════
# GENUINE RESPONSE GENERATOR
# ═══════════════════════════════════════════════════════════════
# Instead of canned responses, this builds UNIQUE responses from
# the actual data found in the database + the user's message context.

def build_genuine_response(intent: dict, sentiment: dict, proc: dict, db_ctx: dict, ids: dict) -> dict:
    """
    Generate a response dynamically based on:
      - What the user actually asked
      - What data we found in the database
      - The detected sentiment (for empathy)
    
    Returns response text, metadata, and what data was used.
    """
    primary = intent["primary_intent"]
    text = proc["cleaned"]
    data_used = []
    data_verified = False

    # ── Empathy prefix for frustrated users ──
    empathy = ""
    if sentiment["label"] == "negative" and sentiment["intensity"] > 0.2:
        empathy = "I understand this is frustrating, and I sincerely apologize for the inconvenience. "

    # ── DB errors (ID provided but not found) ──
    if db_ctx["errors"]:
        error_msg = " ".join(db_ctx["errors"])
        return {
            "text": f"{empathy}{error_msg} Could you double-check the ID and try again? "
                    f"If you don't have the ID, I can look up your information by customer ID or email.",
            "data_verified": False,
            "data_used": [],
            "source": "id_not_found"
        }

    # ══════════════════════════════════════════════════════════
    # RESPONSES BUILT FROM REAL DATABASE DATA
    # ══════════════════════════════════════════════════════════

    order = db_ctx["entities"].get("order")
    customer = db_ctx["entities"].get("customer")
    transaction = db_ctx["entities"].get("transaction")
    subscription = db_ctx["entities"].get("subscription")
    customer_orders = db_ctx["entities"].get("customer_orders")
    refund_check = db_ctx["entities"].get("refund_check")

    # ── ORDER-BASED RESPONSES ──
    if order:
        name = order.get("first_name", "there")
        items_str = ", ".join(i["product_name"] for i in order.get("items", []))
        data_used.append(f"order:{order['order_id']}")
        data_verified = True

        # Refund request for a specific order
        if primary in ("refund", "billing") and any(w in text for w in ["refund", "money back", "reimburse", "return"]):
            if refund_check:
                if refund_check["eligible"]:
                    return {
                        "text": f"{empathy}Hi {name}! I've checked order {order['order_id']} and it is eligible for a full refund of ${order['total']}. "
                                f"The refund will be processed to your {order['transaction']['payment_method'] if order.get('transaction') else 'original payment method'} "
                                f"within 5-7 business days. "
                                f"Items: {items_str}. "
                                f"Would you like me to proceed with the refund?",
                        "data_verified": True, "data_used": data_used, "source": "db_refund_eligible"
                    }
                else:
                    return {
                        "text": f"{empathy}Hi {name}, I've looked into order {order['order_id']}. "
                                f"Unfortunately, {refund_check['reason']} "
                                f"The order total was ${order['total']} for: {items_str}. "
                                f"Would you like me to connect you with a specialist to discuss alternative options?",
                        "data_verified": True, "data_used": data_used, "source": "db_refund_ineligible"
                    }

        # Order tracking / status check
        if order["status"] == "delivered":
            delivery = order.get("delivered_date") or order.get("actual_delivery") or "recently"
            return {
                "text": f"{empathy}Hi {name}! Your order {order['order_id']} was successfully delivered on {delivery}. "
                        f"Items: {items_str}. Order total: ${order['total']}. "
                        f"Is there anything specific about this order I can help you with?",
                "data_verified": True, "data_used": data_used, "source": "db_order_delivered"
            }

        elif order["status"] in ("shipped", "in_transit", "out_for_delivery"):
            tracking = f" Tracking: {order['tracking_number']} via {order['carrier']}." if order.get("tracking_number") else ""
            eta = f" Estimated delivery: {order['estimated_delivery']}." if order.get("estimated_delivery") else ""
            note = f" Note: {order['notes']}" if order.get("notes") else ""
            return {
                "text": f"{empathy}Hi {name}! Your order {order['order_id']} is currently {order['status'].replace('_',' ')}.{tracking}{eta}{note} "
                        f"Items: {items_str}. Total: ${order['total']}.",
                "data_verified": True, "data_used": data_used, "source": "db_order_in_transit"
            }

        elif order["status"] == "processing":
            return {
                "text": f"{empathy}Hi {name}! Your order {order['order_id']} is currently being processed and will ship soon. "
                        f"Items: {items_str}. Total: ${order['total']}. "
                        f"You'll receive a shipping confirmation with tracking details once it ships.",
                "data_verified": True, "data_used": data_used, "source": "db_order_processing"
            }

        elif order["status"] == "cancelled":
            return {
                "text": f"{empathy}Hi {name}, order {order['order_id']} was cancelled. "
                        f"{'Reason: ' + order['notes'] + '. ' if order.get('notes') else ''}"
                        f"Items: {items_str}. Original total: ${order['total']}. "
                        f"If a charge was made, the refund should already be processed. Would you like me to verify?",
                "data_verified": True, "data_used": data_used, "source": "db_order_cancelled"
            }

        elif order["status"] == "returned":
            return {
                "text": f"{empathy}Hi {name}, order {order['order_id']} has been returned. "
                        f"Items: {items_str}. Total: ${order['total']}. "
                        f"Please allow 5-7 business days for the refund to reflect on your statement. "
                        f"Can I help with anything else?",
                "data_verified": True, "data_used": data_used, "source": "db_order_returned"
            }

        else:
            return {
                "text": f"{empathy}Hi {name}! I found your order {order['order_id']}. "
                        f"Status: {order['status'].upper()} | Total: ${order['total']} | Items: {items_str}. "
                        f"How can I help you with this order?",
                "data_verified": True, "data_used": data_used, "source": "db_order_generic"
            }

    # ── TRANSACTION-BASED RESPONSES ──
    if transaction and not order:
        name = transaction.get("first_name", "there")
        data_used.append(f"transaction:{transaction['transaction_id']}")
        data_verified = True

        refund_note = ""
        if transaction.get("refund_eligible"):
            refund_note = f" This transaction is eligible for a refund (deadline: {transaction.get('refund_deadline')})."
        elif transaction["status"] == "refunded":
            refund_note = " This transaction has already been refunded."

        return {
            "text": f"{empathy}Hi {name}! I found transaction {transaction['transaction_id']}. "
                    f"Type: {transaction['type']} | Status: {transaction['status']} | "
                    f"Amount: ${transaction['amount']} | Payment: {transaction.get('payment_method', 'N/A')} | "
                    f"Date: {transaction['transaction_date']}.{refund_note} "
                    f"What would you like to know about this transaction?",
            "data_verified": True, "data_used": data_used, "source": "db_transaction"
        }

    # ── CUSTOMER-BASED RESPONSES ──
    if customer:
        name = customer.get("first_name", "there")
        data_used.append(f"customer:{customer['customer_id']}")
        data_verified = True

        parts = [f"{empathy}Hi {name}! I've pulled up your account ({customer['customer_id']})."]

        if customer_orders:
            recent = customer_orders[:3]
            order_summary = "; ".join(
                f"{o['order_id']} ({o['status']}, ${o['total']})" for o in recent
            )
            parts.append(f"Your recent orders: {order_summary}.")

        if subscription:
            parts.append(
                f"Subscription: {subscription['plan_name'].upper()} plan (${subscription['plan_price']}/{subscription['billing_cycle']}) — "
                f"Status: {subscription['status']}, "
                f"{'auto-renews' if subscription.get('auto_renew') else 'does not auto-renew'} on {subscription.get('current_period_end')}."
            )

        parts.append("How can I help you today?")

        return {
            "text": " ".join(parts),
            "data_verified": True, "data_used": data_used, "source": "db_customer_overview"
        }

    # ── SUBSCRIPTION-BASED RESPONSES ──
    if subscription:
        name = subscription.get("first_name", "there")
        data_used.append(f"subscription:{subscription['subscription_id']}")
        data_verified = True

        return {
            "text": f"{empathy}Hi {name}! Your subscription {subscription['subscription_id']}: "
                    f"{subscription['plan_name'].upper()} plan at ${subscription['plan_price']}/{subscription['billing_cycle']}. "
                    f"Status: {subscription['status']}. Current period: {subscription.get('current_period_start')} to {subscription.get('current_period_end')}. "
                    f"{'Auto-renewal is ON.' if subscription.get('auto_renew') else 'Auto-renewal is OFF.'} "
                    f"What would you like to do with your subscription?",
            "data_verified": True, "data_used": data_used, "source": "db_subscription"
        }

    # ══════════════════════════════════════════════════════════
    # NO DB DATA — Generate contextual response from intent
    # ══════════════════════════════════════════════════════════

    if primary == "greeting":
        return {
            "text": "Hello! I'm your AI support assistant with transparent confidence scoring. "
                    "I can look up your orders, check refund eligibility, review subscriptions, and more. "
                    "Just share your order ID (e.g. ORD-100001) or customer ID and I'll pull up your details!",
            "data_verified": False, "data_used": [], "source": "greeting"
        }

    if primary == "thanks":
        return {"text": "You're welcome! If you have any other questions, feel free to ask. Have a great day!",
                "data_verified": False, "data_used": [], "source": "thanks"}

    if primary == "farewell":
        return {"text": "Goodbye! Don't hesitate to reach out if you need anything in the future. Take care!",
                "data_verified": False, "data_used": [], "source": "farewell"}

    # ── Intent-specific but no ID provided ──
    if primary in ("order_status", "shipping"):
        return {
            "text": f"{empathy}I'd be happy to help you track your order! "
                    f"Could you provide your order ID (e.g. ORD-100001) or customer ID (e.g. CUST-001001)? "
                    f"With that, I can look up the exact status, tracking information, and delivery estimate for you.",
            "data_verified": False, "data_used": [], "source": "needs_order_id"
        }

    if primary in ("refund", "billing"):
        return {
            "text": f"{empathy}I can help you with that! To look into your billing or process a refund, "
                    f"I'll need either your order ID (e.g. ORD-100002) or transaction ID (e.g. TXN-200001). "
                    f"Once I have that, I'll check your refund eligibility and payment details right away.",
            "data_verified": False, "data_used": [], "source": "needs_billing_id"
        }

    if primary == "subscription":
        return {
            "text": f"{empathy}I can help manage your subscription! "
                    f"Please share your customer ID (e.g. CUST-001001) or subscription ID (e.g. SUB-001001) "
                    f"and I'll pull up your plan details, billing cycle, and renewal status.",
            "data_verified": False, "data_used": [], "source": "needs_sub_id"
        }

    if primary == "technical":
        return {
            "text": f"{empathy}I'm sorry you're experiencing a technical issue. To help troubleshoot, "
                    f"could you describe: (1) What you were trying to do, (2) What happened instead, "
                    f"and (3) Any error messages you saw? If you have a customer ID, I can also check your account status.",
            "data_verified": False, "data_used": [], "source": "technical_help"
        }

    if primary == "account":
        return {
            "text": f"{empathy}I can help with your account! Please share your customer ID (e.g. CUST-001001) "
                    f"and I'll pull up your profile, subscription, and recent activity. "
                    f"What specific changes or questions do you have about your account?",
            "data_verified": False, "data_used": [], "source": "account_help"
        }

    # ── Fallback ──
    return {
        "text": f"{empathy}I'm not fully sure I understand your request. I can help with: "
                f"order tracking, refunds, billing, subscriptions, account management, and technical issues. "
                f"If you share an order ID (ORD-XXXXXX), customer ID (CUST-XXXXXX), or describe your issue in more detail, "
                f"I'll do my best to assist!",
        "data_verified": False, "data_used": [], "source": "fallback"
    }


# ═══════════════════════════════════════════════════════════════
# CONFIDENCE SCORING
# ═══════════════════════════════════════════════════════════════

def compute_confidence(intent: dict, sentiment: dict, proc: dict, db_ctx: dict) -> dict:
    """
    Transparent confidence score (0-100) with full breakdown.
    
    Factors:
      1. Intent Match Strength   (30%)
      2. Intent Clarity          (20%)
      3. Query Specificity       (15%)
      4. Sentiment Alignment     (10%)
      5. Data Verification       (25%)  ← NEW: boosts confidence when DB data confirms the response
    """
    factors = []

    # 1. Intent Match Strength (30%)
    intent_score = intent["confidence"]
    f1 = intent_score * 0.30
    matched_kws = intent["matched_keywords"].get(intent["primary_intent"], [])
    factors.append({
        "name": "Intent Match Strength", "weight": "30%",
        "raw_score": round(intent_score * 100, 1),
        "weighted_score": round(f1 * 100, 1),
        "explanation": f"Matched {len(matched_kws)} keyword(s) in '{intent['primary_intent']}' category"
    })

    # 2. Intent Clarity (20%)
    all_i = intent.get("all_intents", [])
    clarity = (all_i[0]["score"] - all_i[1]["score"]) if len(all_i) >= 2 else (all_i[0]["score"] if all_i else 0)
    clarity = min(clarity * 2, 1.0)
    f2 = clarity * 0.20
    factors.append({
        "name": "Intent Clarity", "weight": "20%",
        "raw_score": round(clarity * 100, 1),
        "weighted_score": round(f2 * 100, 1),
        "explanation": "Clear separation between top categories" if clarity > 0.5 else "Multiple categories matched similarly (ambiguous)"
    })

    # 3. Query Specificity (15%)
    tc = proc["token_count"]
    spec = 0.3 if tc <= 2 else (0.6 if tc <= 5 else (0.9 if tc <= 15 else 1.0))
    f3 = spec * 0.15
    spec_note = {0.3: "Very short query", 0.6: "Moderate detail", 0.9: "Good detail", 1.0: "Rich context"}
    factors.append({
        "name": "Query Specificity", "weight": "15%",
        "raw_score": round(spec * 100, 1),
        "weighted_score": round(f3 * 100, 1),
        "explanation": f"{spec_note.get(spec, '')} ({tc} tokens)"
    })

    # 4. Sentiment Alignment (10%)
    primary = intent["primary_intent"]
    sl = sentiment["label"]
    if primary in ("technical","shipping","refund") and sl == "negative":
        alignment = 0.9; a_note = "Negative sentiment aligns with support request"
    elif primary in ("greeting","thanks","farewell") and sl in ("positive","neutral"):
        alignment = 0.9; a_note = "Positive/neutral sentiment fits this interaction"
    elif sl == "neutral":
        alignment = 0.7; a_note = "Neutral sentiment — no conflicting signals"
    else:
        alignment = 0.5; a_note = "Sentiment does not strongly align with intent"
    f4 = alignment * 0.10
    factors.append({
        "name": "Sentiment Alignment", "weight": "10%",
        "raw_score": round(alignment * 100, 1),
        "weighted_score": round(f4 * 100, 1),
        "explanation": a_note
    })

    # 5. Data Verification (25%) — THE KEY DIFFERENTIATOR
    if db_ctx["found"]:
        dv = 1.0; dv_note = f"Response verified against database ({', '.join(db_ctx['lookups_performed'])})"
    elif db_ctx["errors"]:
        dv = 0.3; dv_note = f"ID provided but not found: {'; '.join(db_ctx['errors'])}"
    else:
        dv = 0.0; dv_note = "No database verification — no IDs provided in message"
    f5 = dv * 0.25
    factors.append({
        "name": "Data Verification", "weight": "25%",
        "raw_score": round(dv * 100, 1),
        "weighted_score": round(f5 * 100, 1),
        "explanation": dv_note
    })

    total = round((f1 + f2 + f3 + f4 + f5) * 100, 1)

    if total >= 75:
        level, desc = "high", "I'm highly confident in this response — it's backed by verified data from our system."
    elif total >= 50:
        level, desc = "medium", "I'm moderately confident. The response should be helpful, but providing an order/customer ID would let me give a more precise answer."
    elif total >= 30:
        level, desc = "low", "I have limited confidence. I'd recommend providing more details or an ID so I can verify information in our system."
    else:
        level, desc = "very_low", "I'm not confident I understand your request well enough. Let me connect you with a human agent."

    # Missing info suggestions
    missing = []
    if tc <= 3:
        missing.append("More details about your specific situation")
    if not db_ctx["found"] and not db_ctx["errors"]:
        if primary in ("order_status","shipping","refund","billing"):
            missing.append("Your order ID (e.g. ORD-100001) or transaction ID (e.g. TXN-200001)")
        if primary in ("account","subscription"):
            missing.append("Your customer ID (e.g. CUST-001001)")
    if primary == "technical":
        missing.append("Specific error messages or steps to reproduce the issue")

    return {
        "score": total, "level": level, "description": desc,
        "factors": factors, "missing_information": missing,
        "human_handoff_recommended": total < 35 or (sentiment["label"] == "negative" and sentiment["intensity"] > 0.6)
    }


# ═══════════════════════════════════════════════════════════════
# HUMAN HANDOFF
# ═══════════════════════════════════════════════════════════════

def evaluate_handoff(confidence: dict, sentiment: dict) -> dict:
    reasons = []
    if confidence["score"] < 35:
        reasons.append("Low confidence in understanding your request")
    if sentiment["label"] == "negative" and sentiment["intensity"] > 0.6:
        reasons.append("Detected high frustration — a human agent can provide better support")
    return {
        "recommended": len(reasons) > 0,
        "reasons": reasons,
        "message": "I'd like to connect you with a human agent who can better assist you. I'll transfer our conversation so you won't need to repeat yourself." if reasons else None,
        "agent_brief": {
            "confidence": confidence["score"],
            "intent": confidence.get("level"),
            "sentiment": sentiment["label"],
            "frustration": sentiment["intensity"]
        } if reasons else None
    }


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "database": "connected" if db_connected else "disconnected",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    if not data or not data.get('message', '').strip():
        return jsonify({"error": "No message provided"}), 400

    msg = data['message'].strip()
    session_id = data.get('session_id', str(uuid.uuid4()))

    # ── NLP Pipeline ──
    proc      = preprocess(msg)
    sentiment = analyze_sentiment(proc)
    intent    = classify_intent(proc)
    ids       = extract_ids(msg)
    db_ctx    = gather_db_context(ids, intent["primary_intent"])
    response  = build_genuine_response(intent, sentiment, proc, db_ctx, ids)
    confidence = compute_confidence(intent, sentiment, proc, db_ctx)
    handoff   = evaluate_handoff(confidence, sentiment)

    result = {
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
        "user_message": msg,
        "response": response["text"],
        "response_meta": {
            "source": response["source"],
            "data_verified": response["data_verified"],
            "data_used": response["data_used"]
        },
        "confidence": {
            "score": confidence["score"],
            "level": confidence["level"],
            "description": confidence["description"],
            "factors": confidence["factors"],
            "missing_information": confidence["missing_information"]
        },
        "explainability": {
            "intent": {
                "detected": intent["primary_intent"],
                "all_candidates": intent["all_intents"],
                "matched_keywords": intent["matched_keywords"],
                "explanations": intent["explanations"]
            },
            "sentiment": {
                "label": sentiment["label"],
                "score": sentiment["score"],
                "intensity": sentiment["intensity"],
                "positive_signals": sentiment["positive_matches"],
                "negative_signals": sentiment["negative_matches"],
                "explanations": sentiment["explanations"]
            },
            "database": {
                "ids_extracted": ids,
                "lookups_performed": db_ctx["lookups_performed"],
                "data_found": db_ctx["found"],
                "errors": db_ctx["errors"]
            }
        },
        "handoff": handoff
    }

    logger.info(f"[{session_id}] Intent={intent['primary_intent']} | Conf={confidence['score']}% | "
                f"Sent={sentiment['label']} | DB={'✓' if db_ctx['found'] else '✗'} | IDs={ids}")

    return jsonify(json.loads(json.dumps(result, cls=CustomEncoder)))


@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    logger.info(f"Feedback: {json.dumps(data)}")
    return jsonify({"status": "recorded"})


# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    db_connected = init_db()
    if db_connected:
        logger.info("✅ Database connected — full data verification enabled")
    else:
        logger.warning("⚠️  Database not connected — running without data verification")
    app.run(host='0.0.0.0', port=port, debug=True)
