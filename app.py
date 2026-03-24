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
import hmac
import logging
import jwt
from functools import wraps
from datetime import datetime, date, timedelta
from decimal import Decimal
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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

try:
    import llm_service
    # Verify the API key is present at startup so we fail fast rather than
    # silently falling back on every request.
    if not os.getenv("NVIDIA_API_KEY"):
        raise ValueError("NVIDIA_API_KEY not configured")
    LLM_AVAILABLE = True
    logging.getLogger(__name__).info("LLM service loaded — NVIDIA NIM Llama 3.1 405B will handle response generation.")
except Exception as _llm_err:
    LLM_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"LLM service unavailable ({_llm_err}). Falling back to template responses."
    )

# ─── App ──────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://localhost:5000"])
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)
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
            payload = jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        if payload.get("role") == "user":
            return jsonify({"error": "Forbidden"}), 403
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
        # Look back up to 3 tokens for a negator, stopping at punctuation boundaries
        lookback = []
        for j in range(max(0, i - 3), i):
            if tokens[j] in {",", ".", "!", "?", ";", ":"}:
                break
            lookback.append(j)
        negated = any(tokens[j] in NEGATORS for j in lookback)
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
        # Cap denominator at 3.0 so long sentences don't dilute strong sentiment signals
        "intensity": round(min(max(pos_score, neg_score) / 3.0, 1.0), 3),
        "positive_matches": pos_matches, "negative_matches": neg_matches,
        "explanations": explanations
    }


# ─── Lightweight Suffix Stemmer ──────────────────────────────

def _stem(word: str) -> str:
    """Strip common English suffixes to normalise tokens for intent matching.
    Handles plurals, past tenses, gerunds, and agent forms without external deps.
    """
    for suffix in ("ations", "ation", "tions", "tion", "ing", "ers", "ed", "er", "ly", "ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


# ─── Intent Classification ───────────────────────────────────

INTENT_KEYWORDS = {
    "billing":         ["bill","charge","invoice","payment","price","cost","fee","subscription","plan","refund","money","overcharged","pricing"],
    "technical":       ["bug","error","crash","slow","broken","fix","issue","problem","not working","glitch","loading","fail","login","password","reset","down"],
    "account":         ["account","profile","settings","email","name","delete","close","update","change","personal","data","privacy","deactivate"],
    "shipping":        ["ship","deliver","track","order","package","arrive","return","exchange","lost","damaged","address","where is","dispatch"],
    "order_status":    ["order","status","where","tracking","shipped","delivered","processing","cancelled","when","eta","estimated"],
    "refund":          ["refund","money back","return money","reimburse","credit","chargeback"],
    "subscription":    ["subscription","plan","upgrade","downgrade","cancel subscription","renew","billing cycle","monthly","annual"],
    "greeting":        ["hello","hi","help","hey","good morning","good afternoon","good evening"],
    "thanks":          ["thanks","thank you","appreciate","great help","wonderful"],
    "farewell":        ["bye","goodbye","see you","that's all","done","nothing else"],
    # ── New scenario intents (blueprint Part 1) ──────────────────
    "damaged_product": ["broken","damaged","cracked","defective","smashed","scratched","shattered","arrived broken","dented","faulty","not working","arrived damaged"],
    "wrong_order":     ["wrong","incorrect","different","not what i ordered","wrong item","wrong product","mix up","mistake","got the wrong","sent wrong","received wrong"],
    "payment_failure": ["payment failed","card declined","declined","won't go through","not going through","payment error","checkout failed","cvv","billing address","payment method","try again","alternative payment"],
    "missing_package": ["stolen","theft","porch","missing","not here","not received","says delivered","marked delivered","marked as delivered","cannot find","can't find","never arrived","didn't arrive"],
    "product_inquiry": ["compatible","compatibility","specifications","specs","does it work","features","material","dimensions","in stock","availability","android","ios","bluetooth","warranty","size","weight","color"],
    "address_change":  ["wrong address","change address","update address","entered wrong","incorrect address","new address","different address","shipping address","correct address"],
    "duplicate_charge":["charged twice","double charged","duplicate charge","billed twice","charged again","two charges","extra charge","charged multiple","double billing","duplicate transaction"],
}

def classify_intent(proc: dict) -> dict:
    tokens = set(proc["tokens"])
    stemmed_tokens = {_stem(t) for t in tokens}
    text = proc["cleaned"]
    scores = {}
    match_details = {}

    for category, keywords in INTENT_KEYWORDS.items():
        matched = []
        for kw in keywords:
            if ' ' in kw:
                if kw in text:
                    matched.append(kw)
            elif kw in tokens:
                matched.append(kw)
            else:
                # Stemmed match: stem both the token and keyword, then compare
                kw_stem = _stem(kw)
                if kw_stem in stemmed_tokens:
                    matched.append(kw)
                else:
                    # Fallback prefix heuristic for very close forms
                    for t in tokens:
                        if (t.startswith(kw) or kw.startswith(t)) and abs(len(t) - len(kw)) <= 3:
                            matched.append(kw)
                            break

        if matched:
            n_matched = len(matched)
            n_keywords = len(keywords)
            coverage = n_matched / min(n_keywords, 5)
            bonus = min(n_matched * 0.15, 0.4)
            scores[category] = round(min(coverage + bonus, 1.0), 3)
            match_details[category] = matched

    if not scores:
        return {"primary_intent": "unknown", "confidence": 0.0, "all_intents": [],
                "matched_keywords": {}, "secondary_intent": None,
                "explanations": ["No keywords matched any category."]}

    # Sort by score descending, then by specificity (fewer keywords = more specific = preferred on tie)
    sorted_intents = sorted(scores.items(), key=lambda x: (x[1], -len(INTENT_KEYWORDS[x[0]])), reverse=True)
    explanations = [f"'{cat}': matched [{', '.join(match_details[cat])}] → {s:.0%}" for cat, s in sorted_intents]

    # Surface secondary_intent when top two scores are within 0.05 of each other (tie)
    secondary = None
    if len(sorted_intents) >= 2:
        top_score = sorted_intents[0][1]
        second_score = sorted_intents[1][1]
        if top_score - second_score <= 0.05:
            secondary = sorted_intents[1][0]

    return {
        "primary_intent": sorted_intents[0][0],
        "confidence": sorted_intents[0][1],
        "all_intents": [{"intent": i, "score": s} for i, s in sorted_intents],
        "matched_keywords": match_details,
        "secondary_intent": secondary,
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
        matches = re.findall(pat, upper)
        if matches:
            ids[key] = matches[-1]

    # Partial merge: fill in any ID types not found in the current message
    # from history, so switching context retains companion IDs (e.g. customer
    # ID found earlier is kept when a new order ID is mentioned).
    if context_text:
        ctx_upper = context_text.upper()
        for key, pat in patterns.items():
            if key not in ids:  # only fill gaps, never overwrite current message
                matches = re.findall(pat, ctx_upper)
                if matches:
                    ids[key] = matches[-1]

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
    # Only add empathy when frustration is meaningful (> 0.35) AND the intent is
    # support-focused — prevents awkward apologies on neutral/conversational messages.
    SUPPORT_INTENTS = {"billing", "technical", "account", "shipping", "order_status", "refund", "subscription",
                       "damaged_product", "wrong_order", "payment_failure", "missing_package", "product_inquiry",
                       "address_change", "duplicate_charge"}
    has_valid_entities = any(db_ctx["entities"].values())
    is_support_context = primary in SUPPORT_INTENTS or has_valid_entities
    empathy = ""
    if (sentiment["label"] == "negative"
            and sentiment["intensity"] > 0.35
            and is_support_context):
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
    CONVERSATIONAL_PHRASES_MULTI = {"thank you", "that's all", "that is all", "nothing else", "all good"}
    CONVERSATIONAL_PHRASES_SINGLE = {"thanks", "bye", "goodbye", "hello", "hi", "hey"}
    is_conversational = primary in ("greeting", "thanks", "farewell") or \
                        any(ph in text for ph in CONVERSATIONAL_PHRASES_MULTI) or \
                        any(ph in proc["tokens"] for ph in CONVERSATIONAL_PHRASES_SINGLE)
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

        # ── Damaged product ──
        is_damaged_intent = primary == "damaged_product" or any(
            w in text for w in ["broken", "damaged", "cracked", "defective", "smashed", "scratched", "shattered", "dented", "faulty"]
        )
        if is_damaged_intent:
            return {
                "text": f"{empathy}I'm incredibly sorry your order {order['order_id']} arrived in less-than-perfect condition — that's definitely not the experience we want for you. "
                        f"Items: {items_str}. "
                        f"To resolve this as quickly as possible, please upload a photo of the damage so our team can verify it. "
                        f"Once confirmed, I can arrange a replacement shipment or issue a full refund of ${order['total']} — whichever you prefer.",
                "data_verified": True, "data_used": data_used, "source": "db_damaged_product"
            }

        # ── Wrong order delivered ──
        is_wrong_order_intent = primary == "wrong_order" or any(
            w in text for w in ["wrong", "incorrect", "different", "not what i ordered", "mix up", "mistake", "sent wrong", "received wrong"]
        )
        if is_wrong_order_intent:
            return {
                "text": f"{empathy}I'm so sorry for the mix-up with order {order['order_id']} — that's not acceptable and I want to fix this right away. "
                        f"Items we have on record: {items_str} (${order['total']}). "
                        f"I'll generate a prepaid return label for the incorrect item and prioritise shipping your correct order immediately. "
                        f"Could you briefly describe the item you received versus what you ordered?",
                "data_verified": True, "data_used": data_used, "source": "db_wrong_order"
            }

        # ── Shipping address change ──
        is_address_change = primary == "address_change" or any(
            w in text for w in ["wrong address", "change address", "update address", "incorrect address", "new address", "different address"]
        )
        if is_address_change:
            if order["status"] == "processing":
                return {
                    "text": f"{empathy}Good news — order {order['order_id']} is still in processing, so we may be able to update the address. "
                            f"Please reply with the correct shipping address and I'll flag this for our warehouse team immediately. "
                            f"Items: {items_str} | Total: ${order['total']}.",
                    "data_verified": True, "data_used": data_used, "source": "db_address_change_possible"
                }
            else:
                return {
                    "text": f"{empathy}Unfortunately, order {order['order_id']} is already {order['status'].replace('_', ' ')} and the address can no longer be changed from our end. "
                            f"I'd recommend contacting the carrier directly with your tracking number"
                            + (f" ({order['tracking_number']} via {order['carrier']})" if order.get("tracking_number") else "")
                            + f" to request a redirect. Is there anything else I can help with?",
                    "data_verified": True, "data_used": data_used, "source": "db_address_change_too_late"
                }

        # ── Missing / stolen package (order shows delivered) ──
        is_missing_intent = primary == "missing_package" or any(
            w in text for w in ["not here", "not received", "stolen", "theft", "missing", "says delivered", "marked delivered", "can't find", "cannot find", "never arrived"]
        )
        if is_missing_intent and order["status"] == "delivered":
            delivery = order.get("delivered_date") or order.get("actual_delivery") or "recently"
            return {
                "text": f"{empathy}I'm sorry to hear your package is missing after being marked as delivered on {delivery} — that's very stressful. "
                        f"Order {order['order_id']} | Items: {items_str} | Total: ${order['total']}. "
                        f"Please first check with neighbours or any safe spots near your door. "
                        f"If it hasn't turned up within 24 hours, let me know and I'll help you file a carrier claim and look into a reshipment.",
                "data_verified": True, "data_used": data_used, "source": "db_missing_package"
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

        # ── Duplicate charge ──
        is_duplicate_charge = primary == "duplicate_charge" or transaction.get("is_duplicate") or any(
            w in text for w in ["charged twice", "double charged", "duplicate", "billed twice", "charged again", "two charges", "extra charge"]
        )
        if is_duplicate_charge:
            original = transaction.get("original_transaction", "a previous transaction")
            return {
                "text": f"{empathy}I can see that transaction {transaction['transaction_id']} "
                        f"for ${transaction['amount']} on {transaction.get('payment_method', 'your card')} "
                        f"appears to be a duplicate of {original}. "
                        f"I've flagged this for immediate review and will initiate a full refund of ${transaction['amount']} for the duplicate charge. "
                        f"You should see the reversal within 2-3 business days. We sincerely apologise for this error.",
                "data_verified": True, "data_used": data_used, "source": "db_duplicate_charge"
            }

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
            PLAN_TIERS  = ["free", "basic", "pro", "enterprise"]
            PLAN_PRICES = {"free": 0, "basic": 9.99, "pro": 29.99, "enterprise": 99.99}
            current_plan = subscription.get("plan_name", "").lower()
            current_idx  = PLAN_TIERS.index(current_plan) if current_plan in PLAN_TIERS else -1

            wants_upgrade   = any(w in text for w in ["upgrade", "higher", "better plan", "more features", "move up"])
            wants_downgrade = any(w in text for w in ["downgrade", "lower", "cheaper", "reduce", "smaller plan", "less expensive", "move down"])

            if wants_upgrade and current_idx >= 0 and current_idx < len(PLAN_TIERS) - 1:
                upgrade_options = PLAN_TIERS[current_idx + 1:]
                option_str = " or ".join(f"{p.upper()} (${PLAN_PRICES[p]}/mo)" for p in upgrade_options)
                return {
                    "text": f"{empathy}Your current plan is {current_plan.upper()} at ${subscription['plan_price']}/{subscription['billing_cycle']}. "
                            f"Available upgrades: {option_str}. "
                            f"Upgrading takes effect immediately and the price difference will be prorated for the remaining billing period. "
                            f"Which plan would you like to switch to?",
                    "data_verified": True, "data_used": data_used, "source": "db_subscription_upgrade_options"
                }

            if wants_downgrade and current_idx > 0:
                downgrade_options = list(reversed(PLAN_TIERS[:current_idx]))
                option_str = " or ".join(f"{p.upper()} (${PLAN_PRICES[p]}/mo)" for p in downgrade_options)
                return {
                    "text": f"{empathy}Your current plan is {current_plan.upper()} at ${subscription['plan_price']}/{subscription['billing_cycle']}. "
                            f"Available downgrades: {option_str}. "
                            f"Downgrading takes effect at the start of your next billing cycle — no interruption to your current service. "
                            f"Which plan would you prefer?",
                    "data_verified": True, "data_used": data_used, "source": "db_subscription_downgrade_options"
                }

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

    if primary == "damaged_product":
        return {
            "text": f"{empathy}I'm incredibly sorry to hear your product arrived damaged — that's not the experience we want for you. "
                    f"To resolve this as quickly as possible, please provide your order ID (e.g. ORD-100001) "
                    f"and a brief description or photo of the damage. "
                    f"Once verified, I can arrange a replacement or full refund — whichever you prefer.",
            "data_verified": False, "data_used": [], "source": "damaged_product_needs_id"
        }

    if primary == "wrong_order":
        return {
            "text": f"{empathy}I'm so sorry for the mix-up — receiving the wrong item is definitely not acceptable. "
                    f"Please provide your order ID (e.g. ORD-100001) and a quick description of what you received versus what you ordered. "
                    f"I'll generate a prepaid return label for the incorrect item and prioritise shipping your correct order immediately.",
            "data_verified": False, "data_used": [], "source": "wrong_order_needs_id"
        }

    if primary == "payment_failure":
        return {
            "text": f"{empathy}I'm sorry your payment didn't go through — that can be frustrating when you're trying to check out. "
                    f"A few common fixes: double-check your billing address and CVV match your card exactly, "
                    f"and ensure your bank hasn't placed a temporary hold. "
                    f"You could also try an alternative payment method such as PayPal or Apple Pay. "
                    f"If you see a specific error code, please share it here and I'll investigate further.",
            "data_verified": False, "data_used": [], "source": "payment_failure_tips"
        }

    if primary == "missing_package":
        return {
            "text": f"{empathy}I'm sorry to hear your package hasn't arrived — that's very stressful. "
                    f"First, please check with neighbours or any safe spots near your door. "
                    f"If it still hasn't turned up within 24 hours, provide your order ID (e.g. ORD-100001) "
                    f"and I'll help you file a carrier claim and arrange a reshipment.",
            "data_verified": False, "data_used": [], "source": "missing_package_needs_id"
        }

    if primary == "product_inquiry":
        return {
            "text": f"{empathy}I'd be happy to look up the product details for you! "
                    f"Could you provide the product name or SKU? "
                    f"I can then check compatibility, specifications, materials, and current stock availability.",
            "data_verified": False, "data_used": [], "source": "product_inquiry_needs_sku"
        }

    if primary == "address_change":
        return {
            "text": f"{empathy}I understand — it's easy to enter the wrong address at checkout. "
                    f"Please provide your order ID (e.g. ORD-100001) and your correct shipping address as soon as possible. "
                    f"If the order hasn't been dispatched yet, I can update it immediately.",
            "data_verified": False, "data_used": [], "source": "address_change_needs_id"
        }

    # ── Multi-intent fallback: two intents tied, address both ──
    secondary = intent.get("secondary_intent")
    if secondary and secondary != primary:
        _INTENT_PROMPTS = {
            "order_status":    "order tracking (share an order ID, e.g. ORD-100001)",
            "shipping":        "shipping & delivery (share an order ID, e.g. ORD-100001)",
            "refund":          "refunds (share an order or transaction ID)",
            "billing":         "billing & payments (share an order or transaction ID)",
            "subscription":    "subscriptions (share your customer ID, e.g. CUST-001001)",
            "account":         "account management (share your customer ID, e.g. CUST-001001)",
            "technical":       "technical issues (describe what's happening and any error messages)",
            "damaged_product": "a damaged item (share your order ID and describe the damage)",
            "wrong_order":     "a wrong item received (share your order ID and what you got vs. what you ordered)",
            "payment_failure": "a payment issue (share any error code you're seeing)",
            "missing_package": "a missing package (share your order ID after checking nearby)",
            "product_inquiry": "product details (share the product name or SKU)",
            "address_change":  "a shipping address correction (share your order ID and correct address)",
        }
        p_hint = _INTENT_PROMPTS.get(primary, primary)
        s_hint = _INTENT_PROMPTS.get(secondary, secondary)
        return {
            "text": f"{empathy}It looks like your message may relate to both {p_hint} and {s_hint}. "
                    f"Could you clarify which you need help with, or share the relevant ID so I can look into it right away?",
            "data_verified": False, "data_used": [], "source": "multi_intent_fallback"
        }

    # ── Generic fallback — structured clarifying questions ──
    if sentiment["label"] == "negative" or sentiment.get("intensity", 0) > 0.2:
        return {
            "text": f"{empathy}I'm sorry you're having trouble — I want to make sure I direct you correctly. "
                    f"Could you tell me which area your issue relates to? "
                    f"(1) An order or delivery, (2) a charge or refund, "
                    f"(3) your account or subscription, or (4) a technical problem. "
                    f"Alternatively, sharing an order ID (e.g. ORD-100001) or customer ID (e.g. CUST-001001) "
                    f"lets me pull up your details straight away.",
            "data_verified": False, "data_used": [], "source": "vague_complaint_clarify"
        }
    return {
        "text": f"{empathy}I'm here to help! I can assist with order tracking, refunds, billing, "
                f"subscriptions, and account issues. "
                f"Share an order ID (e.g. ORD-100001), customer ID (e.g. CUST-001001), "
                f"or describe your issue and I'll get right on it.",
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
    elif is_conv_override:
        # Short confirmations ("yes", "ok", "sure") carry implicit DB trust —
        # the previous turn was DB-verified; the current reply continues that context.
        dv = 0.7; dv_note = "Contextual confirmation — implied verification from conversation history"
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
        if primary in ("order_status", "shipping", "refund", "billing",
                       "damaged_product", "wrong_order", "missing_package", "address_change"):
            missing.append("Your order ID (e.g. ORD-100001) or transaction ID (e.g. TXN-200001)")
        if primary in ("account", "subscription"):
            missing.append("Your customer ID (e.g. CUST-001001)")
        if primary == "product_inquiry":
            missing.append("The product name or SKU you're asking about")
    if primary == "technical":
        missing.append("Specific error messages or steps to reproduce the issue")
    if primary == "damaged_product" and not db_ctx["found"]:
        missing.append("A photo or description of the damage")
    if primary == "wrong_order" and not db_ctx["found"]:
        missing.append("Description of the item received vs. what was ordered")
    if primary == "payment_failure":
        missing.append("Any error code shown at checkout")

    return {
        "score": total, "level": level, "description": desc,
        "factors": factors, "missing_information": missing,
        "human_handoff_recommended": total < 35 or (sentiment["label"] == "negative" and sentiment["intensity"] > 0.4)
    }


# ═══════════════════════════════════════════════════════════════
# HUMAN HANDOFF
# ═══════════════════════════════════════════════════════════════

_CONVERSATIONAL_INTENTS = {"greeting", "thanks", "farewell", "product_inquiry"}

# session_id -> {"labels": deque[str], "scores": deque[float], "ema": float}
from collections import deque
_session_sentiments: dict = {}
_EMA_ALPHA = 0.4

def _record_sentiment(session_id: str, label: str, score: float) -> dict:
    """Append label/score to session history, update EMA, return trajectory snapshot."""
    state = _session_sentiments.setdefault(session_id, {
        "labels": deque(maxlen=10),
        "scores": deque(maxlen=10),
        "ema": 0.0,
    })
    prev_ema = state["ema"] if state["scores"] else score
    state["labels"].append(label)
    state["scores"].append(score)
    state["ema"] = _EMA_ALPHA * score + (1 - _EMA_ALPHA) * prev_ema

    consecutive = 0
    for lbl in reversed(state["labels"]):
        if lbl == "negative":
            consecutive += 1
        else:
            break

    delta = score - prev_ema
    if delta > 0.1:
        trend = "improving"
    elif delta < -0.1:
        trend = "worsening"
    else:
        trend = "steady"

    return {
        "consecutive_negative": consecutive,
        "rolling_score": round(state["ema"], 3),
        "previous_score": round(prev_ema, 3),
        "delta": round(delta, 3),
        "history": [round(s, 3) for s in state["scores"]],
        "trend": trend,
    }

def evaluate_handoff(confidence: dict, sentiment: dict, intent: dict = None, session_id: str = None,
                     trajectory: dict = None) -> dict:
    reasons = []
    primary = (intent or {}).get("primary_intent", "unknown")
    if confidence["score"] < 35 and primary not in _CONVERSATIONAL_INTENTS:
        reasons.append("Low confidence in understanding your request")
    if sentiment["label"] == "negative" and sentiment["intensity"] > 0.4:
        reasons.append("Detected high frustration — a human agent can provide better support")
    if trajectory and trajectory.get("consecutive_negative", 0) >= 2 and not reasons:
        reasons.append("Persistent frustration across multiple messages — connecting you with a human agent")
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
@limiter.limit("30 per minute")
def chat():
    data = request.get_json()
    if not data or not data.get('message', '').strip():
        return jsonify({"error": "No message provided"}), 400

    msg = data['message'].strip()
    if len(msg) > 2000:
        return jsonify({"error": "Message too long. Please keep your message under 2,000 characters."}), 400

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
    context   = (get_recent_session_messages(session_id) or "")[-4000:]  # cap to last ~20 turns
    ids       = extract_ids(msg, context)
    db_ctx    = gather_db_context(ids, intent["primary_intent"])
    response  = build_genuine_response(intent, sentiment, proc, db_ctx, ids, context)

    # ── LLM response enhancement ──
    # Template response is always generated first (reliable fallback).
    # If NVIDIA NIM is available, replace the text with a more natural reply
    # while keeping all metadata (data_verified, data_used, source) intact.
    _SKIP_LLM_SOURCES = {"greeting", "farewell", "thanks"}
    if LLM_AVAILABLE and response["source"] not in _SKIP_LLM_SOURCES:
        try:
            llm_text = llm_service.generate_response(
                user_message=msg,
                intent=intent,
                sentiment=sentiment,
                db_ctx=db_ctx,
                template_text=response["text"],
                context=context,
            )
            response["text"] = llm_text
            response["source"] = response["source"] + "_llm"
        except Exception as _llm_ex:
            logger.warning(f"[{session_id}] LLM generation failed, using template: {_llm_ex}")

    confidence = compute_confidence(intent, sentiment, proc, db_ctx)
    trajectory = _record_sentiment(session_id, sentiment["label"], float(sentiment.get("score", 0.0)))
    handoff   = evaluate_handoff(confidence, sentiment, intent, session_id, trajectory)

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
                "rolling_score": trajectory["rolling_score"],
                "previous_score": trajectory["previous_score"],
                "delta": trajectory["delta"],
                "history": trajectory["history"],
                "trend": trajectory["trend"],
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
    expected_admin = os.environ.get("ADMIN_USERNAME")
    expected_pass = os.environ.get("ADMIN_PASSWORD")
    if not expected_admin or not expected_pass:
        return jsonify({"error": "Service misconfigured"}), 503
    if (hmac.compare_digest(username, expected_admin) and
            hmac.compare_digest(password, expected_pass)):
        token = jwt.encode(
            {"sub": username, "exp": datetime.utcnow() + timedelta(hours=8)},
            os.environ["JWT_SECRET_KEY"],
            algorithm="HS256"
        )
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/api/user-login', methods=['POST'])
def user_login():
    data = request.get_json(silent=True, force=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "No credentials provided"}), 400
    username = data.get("username", "")
    password = data.get("password", "")
    expected_user = os.environ.get("USER_USERNAME")
    expected_pass = os.environ.get("USER_PASSWORD")
    if not expected_user or not expected_pass:
        return jsonify({"error": "Service misconfigured"}), 503
    if (hmac.compare_digest(username, expected_user) and
            hmac.compare_digest(password, expected_pass)):
        token = jwt.encode(
            {"sub": username, "role": "user",
             "exp": datetime.utcnow() + timedelta(hours=8)},
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

