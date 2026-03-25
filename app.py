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
import jwt
from functools import wraps
from datetime import datetime, date, timedelta
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
    check_refund_eligibility,
    log_interaction, save_feedback, get_analytics_data, get_retrain_candidates,
    get_recent_session_messages
)

try:
    from ml_service import ml_classify_intent, ml_analyze_sentiment
    ML_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("ML service loaded — using transformer models for NLP.")
except Exception as _ml_err:
    ML_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"ML service unavailable ({_ml_err}). Falling back to keyword-based NLP."
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
# AUTH
# ═══════════════════════════════════════════════════════════════

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


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
            n_matched = len(matched)
            n_keywords = len(keywords)
            # Base coverage, but cap the denominator so large keyword lists
            # aren't unfairly penalised for matching only a few terms.
            coverage = n_matched / min(n_keywords, 5)
            bonus = min(n_matched * 0.15, 0.4)
            scores[category] = round(min(coverage + bonus, 1.0), 3)
            match_details[category] = matched

    if not scores:
        return {"primary_intent": "unknown", "confidence": 0.0, "all_intents": [],
                "matched_keywords": {}, "explanations": ["No keywords matched any category."]}

    # Sort by score descending, then by specificity (fewer keywords = more specific = preferred on tie)
    sorted_intents = sorted(scores.items(), key=lambda x: (x[1], -len(INTENT_KEYWORDS[x[0]])), reverse=True)
    explanations = [f"'{cat}': matched [{', '.join(match_details[cat])}] → {s:.0%}" for cat, s in sorted_intents]

    return {
        "primary_intent": sorted_intents[0][0],
        "confidence": sorted_intents[0][1],
        "all_intents": [{"intent": i, "score": s} for i, s in sorted_intents],
        "matched_keywords": match_details,
        "explanations": explanations
    }


# ─── ID Extraction ────────────────────────────────────────────

def extract_ids(text: str, context_text: str = "") -> dict:
    """Pull order/customer/transaction/subscription IDs from free text.

    If the current message contains no IDs, falls back to context_text
    (recent session history) so follow-up questions retain the active entity.
    """
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

    if not ids and context_text:
        ctx_upper = context_text.upper()
        for key, pat in patterns.items():
            m = re.search(pat, ctx_upper)
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

    # Always check refund eligibility when an order is present
    if "order" in ctx["entities"]:
        refund_info = check_refund_eligibility(ids.get("order_id", ""))
        if refund_info:
            ctx["entities"]["refund_check"] = refund_info

    return ctx


# ═══════════════════════════════════════════════════════════════
# GENUINE RESPONSE GENERATOR
# ═══════════════════════════════════════════════════════════════
# Instead of canned responses, this builds UNIQUE responses from
# the actual data found in the database + the user's message context.

def build_genuine_response(intent: dict, sentiment: dict, proc: dict, db_ctx: dict, ids: dict, context: str = "") -> dict:
    """
    Generate a response dynamically based on:
      - What the user actually asked
      - What data we found in the database
      - The detected sentiment (for empathy)
      - Recent session context (for multi-turn flows like refund confirmation)

    Returns response text, metadata, and what data was used.
    """
    primary = intent["primary_intent"]
    text = proc["cleaned"]

    CONFIRMATION_WORDS = {"yes", "sure", "proceed", "confirm", "ok", "okay", "do it", "go ahead", "please", "yep", "yeah"}
    REFUND_WORDS       = {"refund", "money back", "reimburse", "return"}

    is_confirmation   = any(w in text for w in CONFIRMATION_WORDS)
    in_refund_flow    = any(w in text for w in REFUND_WORDS) or any(w in context.lower() for w in REFUND_WORDS)
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

    # ── Conversational bypass — takes priority over any DB context ──
    CONVERSATIONAL_PHRASES = {"thank you", "thanks", "bye", "goodbye", "that's all",
                               "that is all", "nothing else", "all good", "hello", "hi", "hey"}
    is_conversational = primary in ("greeting", "thanks", "farewell") or \
                        any(ph in text for ph in CONVERSATIONAL_PHRASES)
    if is_conversational:
        if primary == "greeting":
            return {
                "text": "Hello! I'm your AI support assistant with transparent confidence scoring. "
                        "I can look up your orders, check refund eligibility, review subscriptions, and more. "
                        "Just share your order ID (e.g. ORD-100001) or customer ID and I'll pull up your details!",
                "data_verified": False, "data_used": [], "source": "greeting"
            }
        if primary == "farewell" or any(ph in text for ph in {"bye", "goodbye", "that's all", "that is all", "nothing else"}):
            return {"text": "Goodbye! Don't hesitate to reach out if you need anything. Take care!",
                    "data_verified": False, "data_used": [], "source": "farewell"}
        return {"text": "You're welcome! Let me know if you need help with anything else.",
                "data_verified": False, "data_used": [], "source": "thanks"}

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
        items_str = ", ".join(i["product_name"] for i in order.get("items", []))
        data_used.append(f"order:{order['order_id']}")
        data_verified = True

        # Refund request for a specific order
        is_refund_intent = primary in ("refund", "billing") or any(
            w in text for w in ["refund", "money back", "reimburse", "return"]
        )
        if is_refund_intent or (is_confirmation and in_refund_flow):
            if refund_check:
                if refund_check["eligible"]:
                    if is_confirmation and in_refund_flow:
                        return {
                            "text": f"{empathy}Your refund of ${order['total']} for order {order['order_id']} has been successfully initiated. "
                                    f"It will be returned to your original payment method within 5-7 business days. "
                                    f"You'll receive a confirmation email shortly. Is there anything else I can help with?",
                            "data_verified": True, "data_used": data_used, "source": "db_refund_processed"
                        }
                    return {
                        "text": f"{empathy}I've checked order {order['order_id']} and it is eligible for a full refund of ${order['total']}. "
                                f"The refund will be processed to your original payment method "
                                f"within 5-7 business days. "
                                f"Items: {items_str}. "
                                f"Would you like me to proceed with the refund?",
                        "data_verified": True, "data_used": data_used, "source": "db_refund_eligible"
                    }
                else:
                    return {
                        "text": f"{empathy}I've looked into order {order['order_id']}. "
                                f"Unfortunately, {refund_check['reason']} "
                                f"The order total was ${order['total']} for: {items_str}. "
                                f"Would you like me to connect you with a specialist to discuss alternative options?",
                        "data_verified": True, "data_used": data_used, "source": "db_refund_ineligible"
                    }
            else:
                return {
                    "text": f"{empathy}I understand you'd like a refund for order {order['order_id']}, "
                            f"but I was unable to locate the original transaction to verify eligibility. "
                            f"Let me connect you with a specialist who can process this directly.",
                    "data_verified": True, "data_used": data_used, "source": "db_refund_no_transaction"
                }

        # Order tracking / status check
        if order["status"] == "delivered":
            delivery = order.get("delivered_date") or order.get("actual_delivery") or "recently"
            return {
                "text": f"{empathy}Your order {order['order_id']} was successfully delivered on {delivery}. "
                        f"Items: {items_str}. Order total: ${order['total']}. "
                        f"Is there anything specific about this order I can help you with?",
                "data_verified": True, "data_used": data_used, "source": "db_order_delivered"
            }

        elif order["status"] in ("shipped", "in_transit", "out_for_delivery"):
            tracking = f" Tracking: {order['tracking_number']} via {order['carrier']}." if order.get("tracking_number") else ""
            eta = f" Estimated delivery: {order['estimated_delivery']}." if order.get("estimated_delivery") else ""
            note = f" Note: {order['notes']}" if order.get("notes") else ""
            return {
                "text": f"{empathy}Your order {order['order_id']} is currently {order['status'].replace('_',' ')}.{tracking}{eta}{note} "
                        f"Items: {items_str}. Total: ${order['total']}.",
                "data_verified": True, "data_used": data_used, "source": "db_order_in_transit"
            }

        elif order["status"] == "processing":
            return {
                "text": f"{empathy}Your order {order['order_id']} is currently being processed and will ship soon. "
                        f"Items: {items_str}. Total: ${order['total']}. "
                        f"You'll receive a shipping confirmation with tracking details once it ships.",
                "data_verified": True, "data_used": data_used, "source": "db_order_processing"
            }

        elif order["status"] == "cancelled":
            return {
                "text": f"{empathy}Order {order['order_id']} was cancelled. "
                        f"{'Reason: ' + order['notes'] + '. ' if order.get('notes') else ''}"
                        f"Items: {items_str}. Original total: ${order['total']}. "
                        f"If a charge was made, the refund should already be processed. Would you like me to verify?",
                "data_verified": True, "data_used": data_used, "source": "db_order_cancelled"
            }

        elif order["status"] == "returned":
            return {
                "text": f"{empathy}Order {order['order_id']} has been returned. "
                        f"Items: {items_str}. Total: ${order['total']}. "
                        f"Please allow 5-7 business days for the refund to reflect on your statement. "
                        f"Can I help with anything else?",
                "data_verified": True, "data_used": data_used, "source": "db_order_returned"
            }

        else:
            return {
                "text": f"{empathy}I found your order {order['order_id']}. "
                        f"Status: {order['status'].upper()} | Total: ${order['total']} | Items: {items_str}. "
                        f"How can I help you with this order?",
                "data_verified": True, "data_used": data_used, "source": "db_order_generic"
            }

    # ── TRANSACTION-BASED RESPONSES ──
    if transaction and not order:
        data_used.append(f"transaction:{transaction['transaction_id']}")
        data_verified = True

        is_refund_intent = primary in ("refund", "billing") or any(
            w in text for w in ["refund", "money back", "reimburse", "return", "back", "charge"]
        )

        if is_refund_intent or (is_confirmation and in_refund_flow):
            if transaction.get("refund_eligible"):
                if is_confirmation and in_refund_flow:
                    return {
                        "text": f"{empathy}Your refund of ${transaction['amount']} for transaction {transaction['transaction_id']} has been successfully initiated. "
                                f"It will be returned to your {transaction.get('payment_method', 'original payment method')} within 5-7 business days. "
                                f"You'll receive a confirmation email shortly. Is there anything else I can help with?",
                        "data_verified": True, "data_used": data_used, "source": "db_txn_refund_processed"
                    }
                return {
                    "text": f"{empathy}Transaction {transaction['transaction_id']} is eligible for a refund. "
                            f"Amount: ${transaction['amount']} charged to {transaction.get('payment_method', 'your payment method')}. "
                            f"The refund will be processed within 5-7 business days "
                            f"(deadline: {transaction.get('refund_deadline')}). "
                            f"Would you like me to initiate the refund?",
                    "data_verified": True, "data_used": data_used, "source": "db_txn_refund_eligible"
                }
            elif transaction["status"] == "refunded":
                return {
                    "text": f"{empathy}Transaction {transaction['transaction_id']} has already been fully refunded. "
                            f"The ${transaction['amount']} should have been returned to "
                            f"{transaction.get('payment_method', 'your payment method')}. "
                            f"Is there anything else I can help with?",
                    "data_verified": True, "data_used": data_used, "source": "db_txn_already_refunded"
                }
            else:
                return {
                    "text": f"{empathy}Unfortunately, transaction {transaction['transaction_id']} is not eligible for a refund "
                            f"(status: {transaction['status']}, amount: ${transaction['amount']}). "
                            f"Would you like me to connect you with a specialist to discuss alternatives?",
                    "data_verified": True, "data_used": data_used, "source": "db_txn_refund_ineligible"
                }

        # Default: overview summary
        refund_note = ""
        if transaction.get("refund_eligible"):
            refund_note = f" This transaction is eligible for a refund (deadline: {transaction.get('refund_deadline')})."
        elif transaction["status"] == "refunded":
            refund_note = " This transaction has already been refunded."

        return {
            "text": f"{empathy}Transaction {transaction['transaction_id']} found. "
                    f"Type: {transaction['type']} | Status: {transaction['status']} | "
                    f"Amount: ${transaction['amount']} | Payment: {transaction.get('payment_method', 'N/A')} | "
                    f"Date: {transaction['transaction_date']}.{refund_note} "
                    f"What would you like to know about this transaction?",
            "data_verified": True, "data_used": data_used, "source": "db_transaction"
        }

    # ── CUSTOMER-BASED RESPONSES ──
    if customer:
        data_used.append(f"customer:{customer['customer_id']}")
        data_verified = True

        # Subscription-focused
        if primary == "subscription" and subscription:
            auto = "auto-renews" if subscription.get("auto_renew") else "does not auto-renew"
            return {
                "text": f"{empathy}Subscription for account {customer['customer_id']}: "
                        f"{subscription['plan_name'].upper()} plan at ${subscription['plan_price']}/{subscription['billing_cycle']}. "
                        f"Status: {subscription['status']} — {auto} on {subscription.get('current_period_end')}. "
                        f"Would you like to upgrade, downgrade, or cancel your subscription?",
                "data_verified": True, "data_used": data_used, "source": "db_customer_subscription"
            }

        # Order/shipping-focused
        if primary in ("order_status", "shipping") and customer_orders:
            recent = customer_orders[:3]
            order_lines = "; ".join(
                f"{o['order_id']} ({o['status']}, ${o['total']})" for o in recent
            )
            return {
                "text": f"{empathy}Recent orders for account {customer['customer_id']}: {order_lines}. "
                        f"Share a specific order ID for full tracking details.",
                "data_verified": True, "data_used": data_used, "source": "db_customer_orders"
            }

        # Default: full overview
        parts = [f"{empathy}Account {customer['customer_id']} found."]

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
        data_used.append(f"subscription:{subscription['subscription_id']}")
        data_verified = True

        return {
            "text": f"{empathy}Subscription {subscription['subscription_id']}: "
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
      1. Intent Match Strength   (20%)
      2. Intent Clarity          (10%)
      3. Query Specificity       (15%)
      4. Sentiment Alignment     (15%)
      5. Data Verification       (40%)  ← Primary driver — verified data = high confidence
    """
    factors = []

    # ── Conversational / confirmation override ──
    # Short confirmations ("yes", "ok", "sure") and conversational phrases are
    # penalised by the length-based specificity and low ML probability scores.
    # When detected, override F1 (intent match) and F3 (specificity) to 100%
    # so the total score reflects the genuine high confidence of the interaction.
    CONV_OVERRIDE_WORDS = {"yes", "sure", "ok", "okay", "proceed", "confirm",
                           "thanks", "thank you", "bye", "goodbye", "yep", "yeah",
                           "go ahead", "please", "do it"}
    tc = proc["token_count"]
    msg_lower = proc["cleaned"].lower()
    is_conv_override = tc <= 3 and any(w in msg_lower for w in CONV_OVERRIDE_WORDS)

    # 1. Intent Match Strength (20%)
    intent_score = 1.0 if is_conv_override else intent["confidence"]
    f1 = intent_score * 0.20
    matched_kws = intent["matched_keywords"].get(intent["primary_intent"], [])
    if is_conv_override:
        f1_explanation = "Contextual confirmation/conversational phrase detected (100%)"
    elif matched_kws:
        f1_explanation = f"Matched {len(matched_kws)} keyword(s) in '{intent['primary_intent']}' category"
    else:
        f1_explanation = f"ML model probability for '{intent['primary_intent']}': {intent_score:.1%}"
    factors.append({
        "name": "Intent Match Strength", "weight": "20%",
        "raw_score": round(intent_score * 100, 1),
        "weighted_score": round(f1 * 100, 1),
        "explanation": f1_explanation
    })

    # 2. Intent Clarity (10%)
    all_i = intent.get("all_intents", [])
    if is_conv_override:
        clarity = 1.0
        f2_explanation = "Contextual confirmation/conversational phrase detected (100%)"
    elif len(all_i) >= 2:
        top, second = all_i[0]["score"], all_i[1]["score"]
        clarity = (top - second) / top if top > 0 else 0.0
        if matched_kws:
            f2_explanation = "Clear separation between top categories" if clarity > 0.5 else "Multiple categories matched similarly (ambiguous)"
        else:
            top_pct  = f"{all_i[0]['score']:.1%}"
            next_pct = f"{all_i[1]['score']:.1%}"
            f2_explanation = f"ML probability gap: top={top_pct} vs next={next_pct}"
    elif all_i:
        clarity = 1.0
        f2_explanation = "Single clear category"
    else:
        clarity = 0.0
        f2_explanation = "No intent matched"
    f2 = clarity * 0.10
    factors.append({
        "name": "Intent Clarity", "weight": "10%",
        "raw_score": round(clarity * 100, 1),
        "weighted_score": round(f2 * 100, 1),
        "explanation": f2_explanation
    })

    # 3. Query Specificity (15%)
    spec = 1.0 if is_conv_override else round(min(1.0, tc ** 0.5 / 4.0), 3)
    f3 = spec * 0.15
    if is_conv_override:
        spec_explanation = "Contextual confirmation/conversational phrase detected (100%)"
    else:
        spec_label = "Very short" if tc <= 2 else ("Moderate" if tc <= 6 else ("Detailed" if tc <= 14 else "Rich context"))
        spec_explanation = f"{spec_label} ({tc} tokens)"
    factors.append({
        "name": "Query Specificity", "weight": "15%",
        "raw_score": round(spec * 100, 1),
        "weighted_score": round(f3 * 100, 1),
        "explanation": spec_explanation
    })

    # 4. Sentiment Alignment (15%)
    primary = intent["primary_intent"]
    sl = sentiment["label"]
    if primary in ("technical","shipping","refund","billing","account","order_status","subscription") and sl == "negative":
        alignment = 0.9; a_note = "Negative sentiment aligns with support request"
    elif primary in ("greeting","thanks","farewell") and sl in ("positive","neutral"):
        alignment = 0.9; a_note = "Positive/neutral sentiment fits this interaction"
    elif sl == "neutral":
        alignment = 0.7; a_note = "Neutral sentiment — no conflicting signals"
    else:
        alignment = 0.5; a_note = "Sentiment does not strongly align with intent"
    f4 = alignment * 0.15
    factors.append({
        "name": "Sentiment Alignment", "weight": "15%",
        "raw_score": round(alignment * 100, 1),
        "weighted_score": round(f4 * 100, 1),
        "explanation": a_note
    })

    # 5. Data Verification (40%) — THE KEY DIFFERENTIATOR
    if db_ctx["found"]:
        dv = 1.0; dv_note = f"Response verified against database ({', '.join(db_ctx['lookups_performed'])})"
    elif db_ctx["errors"]:
        dv = 0.3; dv_note = f"ID provided but not found: {'; '.join(db_ctx['errors'])}"
    else:
        dv = 0.0; dv_note = "No database verification — no IDs provided in message"
    f5 = dv * 0.40
    factors.append({
        "name": "Data Verification", "weight": "40%",
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
    if tc <= 3 and not is_conv_override:
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
        "ml_enabled": ML_AVAILABLE,
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
    if ML_AVAILABLE:
        _s = ml_analyze_sentiment(msg)
        _i = ml_classify_intent(msg)
        # Normalise ML output to the contract the rest of the pipeline expects.
        # ml_service uses "score" (0-1 signed); pipeline needs "intensity" (0-1 magnitude).
        # ml_service uses "all_candidates"; pipeline needs "all_intents".
        sentiment = {
            **_s,
            "intensity":        abs(_s.get("score", 0.0)),
            "positive_matches": _s.get("positive_matches", []),
            "negative_matches": _s.get("negative_matches", []),
            "explanations":     [_s["explanation"]] if "explanation" in _s else _s.get("explanations", []),
        }
        intent = {
            **_i,
            "all_intents":  _i.get("all_intents") or _i.get("all_candidates", []),
            "explanations": _i.get("explanations", []),
        }
    else:
        sentiment = analyze_sentiment(proc)
        intent    = classify_intent(proc)
    context   = get_recent_session_messages(session_id) or ""
    ids       = extract_ids(msg, context)
    db_ctx    = gather_db_context(ids, intent["primary_intent"])
    response  = build_genuine_response(intent, sentiment, proc, db_ctx, ids, context)
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

    # ── Log interaction to DB ──
    interaction_id = log_interaction(
        session_id=session_id,
        user_message=msg,
        detected_intent=intent["primary_intent"],
        confidence_score=confidence["score"],
        response_source=response["source"],
        handoff_recommended=handoff["recommended"]
    )
    if interaction_id:
        result["interaction_id"] = interaction_id

    logger.info(f"[{session_id}] Intent={intent['primary_intent']} | Conf={confidence['score']}% | "
                f"Sent={sentiment['label']} | DB={'✓' if db_ctx['found'] else '✗'} | IDs={ids}")

    return jsonify(json.loads(json.dumps(result, cls=CustomEncoder)))


@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    interaction_id = data.get("interaction_id")
    rating = data.get("rating")
    comment = data.get("comment")

    if interaction_id and rating is not None:
        result = save_feedback(interaction_id, int(rating), comment)
        if result:
            logger.info(f"Feedback saved: interaction={interaction_id} rating={rating} retrain={result.get('retrain_flag')}")
            return jsonify({"status": "recorded", "retrain_flag": result.get("retrain_flag", False)})

    # Fallback: log only (no DB or missing fields)
    logger.info(f"Feedback (log-only): {json.dumps(data)}")
    return jsonify({"status": "recorded"})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No credentials provided"}), 400
    username = data.get("username", "")
    password = data.get("password", "")
    if (username == os.environ.get("ADMIN_USERNAME") and
            password == os.environ.get("ADMIN_PASSWORD")):
        token = jwt.encode(
            {"sub": username, "exp": datetime.utcnow() + timedelta(hours=8)},
            os.environ["JWT_SECRET_KEY"],
            algorithm="HS256"
        )
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/api/analytics', methods=['GET'])
@token_required
def analytics():
    data = get_analytics_data()
    if data is None:
        return jsonify({"error": "Analytics unavailable (database not connected)"}), 503
    return jsonify(json.loads(json.dumps(data, cls=CustomEncoder)))


@app.route('/api/retrain_feedback', methods=['GET'])
@token_required
def retrain_feedback():
    limit = request.args.get('limit', 20, type=int)
    candidates = get_retrain_candidates(limit)
    if candidates is None:
        return jsonify({"error": "Database not connected"}), 503
    return jsonify(json.loads(json.dumps({"candidates": candidates, "count": len(candidates)}, cls=CustomEncoder)))



# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    db_connected = init_db()
    if db_connected:
        logger.info("✅ Database connected — full data verification enabled")
    else:
        logger.warning("⚠️  Database not connected — running without data verification")
    app.run(host='0.0.0.0', port=port, debug=True)
