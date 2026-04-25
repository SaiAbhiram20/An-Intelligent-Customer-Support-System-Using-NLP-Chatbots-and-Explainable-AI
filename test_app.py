"""
Test Suite — Intelligent Customer Support System v2.0
Tests NLP pipeline, DB lookups, genuine response generation, confidence scoring
"""
import pytest, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import app, preprocess, analyze_sentiment, classify_intent, extract_ids, build_genuine_response, compute_confidence


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestPreprocessing:
    def test_tokenizes(self):
        r = preprocess("Hello, how are you?")
        assert "hello" in r["tokens"]
        assert r["token_count"] > 0

    def test_preserves_ids(self):
        r = preprocess("Check order ORD-100001 please")
        assert "ord-100001" in r["cleaned"]


class TestSentiment:
    def test_positive(self):
        r = analyze_sentiment(preprocess("This is great and amazing!"))
        assert r["label"] == "positive" and r["score"] > 0

    def test_negative(self):
        r = analyze_sentiment(preprocess("This is terrible and awful"))
        assert r["label"] == "negative" and r["score"] < 0

    def test_neutral(self):
        r = analyze_sentiment(preprocess("I want to check my order"))
        assert r["label"] == "neutral"

    def test_negation(self):
        r = analyze_sentiment(preprocess("This is not good"))
        assert "not good" in r["negative_matches"]

    def test_intensifier(self):
        r = analyze_sentiment(preprocess("This is extremely terrible"))
        assert r["label"] == "negative" and r["intensity"] > 0


class TestIntentClassification:
    def test_billing(self):
        assert classify_intent(preprocess("I want a refund for my payment"))["primary_intent"] == "billing"

    def test_refund(self):
        assert classify_intent(preprocess("I need a refund please"))["primary_intent"] == "refund"

    def test_technical(self):
        r = classify_intent(preprocess("The app crashes with errors"))
        assert r["primary_intent"] == "technical"

    def test_shipping(self):
        assert classify_intent(preprocess("Where is my package"))["primary_intent"] == "shipping"

    def test_order_status(self):
        assert classify_intent(preprocess("What is the status of my order"))["primary_intent"] == "order_status"

    def test_subscription(self):
        assert classify_intent(preprocess("I want to upgrade my plan"))["primary_intent"] == "subscription"

    def test_account(self):
        assert classify_intent(preprocess("Delete my account and data"))["primary_intent"] == "account"

    def test_unknown(self):
        r = classify_intent(preprocess("xyzzy quantum flux"))
        assert r["primary_intent"] == "unknown" and r["confidence"] == 0.0

    def test_greeting(self):
        assert classify_intent(preprocess("Hello, I need help"))["primary_intent"] == "greeting"

    def test_multiple_ranked(self):
        r = classify_intent(preprocess("My billing account has an error"))
        assert len(r["all_intents"]) > 1


class TestIDExtraction:
    def test_order_id(self):
        assert extract_ids("Check order ORD-100001") == {"order_id": "ORD-100001"}

    def test_customer_id(self):
        assert extract_ids("Look up CUST-001002") == {"customer_id": "CUST-001002"}

    def test_transaction_id(self):
        assert extract_ids("Transaction TXN-200003") == {"transaction_id": "TXN-200003"}

    def test_subscription_id(self):
        assert extract_ids("My sub SUB-001001") == {"subscription_id": "SUB-001001"}

    def test_multiple_ids(self):
        ids = extract_ids("Order ORD-100001 for customer CUST-001001")
        assert "order_id" in ids and "customer_id" in ids

    def test_no_ids(self):
        assert extract_ids("I need help with something") == {}

    def test_case_insensitive(self):
        assert extract_ids("order ord-100001") == {"order_id": "ORD-100001"}

    def test_context_fallback_most_recent(self):
        """When multiple IDs exist in history, the most recent one wins."""
        context = "User asked about ORD-100001. Then user asked about ORD-100002."
        ids = extract_ids("Where is it?", context)
        assert ids.get("order_id") == "ORD-100002"

    def test_context_fallback_oldest_not_returned(self):
        """An older ID in history must NOT override a newer one."""
        context = "ORD-100001 ORD-100003"
        ids = extract_ids("follow up", context)
        assert ids.get("order_id") == "ORD-100003"
        assert ids.get("order_id") != "ORD-100001"

    def test_partial_merge_keeps_current_message_id(self):
        """If the current message has an order ID, history should not overwrite it."""
        context = "User mentioned ORD-100001 earlier."
        ids = extract_ids("What about ORD-100002?", context)
        assert ids.get("order_id") == "ORD-100002"

    def test_partial_merge_fills_missing_id_from_history(self):
        """Current message has an order ID; customer ID should be pulled from history."""
        context = "Customer CUST-001001 was verified."
        ids = extract_ids("Refund for ORD-100002", context)
        assert ids.get("order_id") == "ORD-100002"
        assert ids.get("customer_id") == "CUST-001001"


class TestGenuineResponse:
    """Test that responses are built from data, not canned."""

    def test_greeting_response(self):
        intent = {"primary_intent": "greeting", "confidence": 0.5, "all_intents": [{"intent": "greeting", "score": 0.5}], "matched_keywords": {"greeting": ["hello"]}, "explanations": []}
        sentiment = {"label": "neutral", "score": 0, "intensity": 0, "positive_matches": [], "negative_matches": [], "explanations": []}
        proc = preprocess("Hello")
        db_ctx = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        r = build_genuine_response(intent, sentiment, proc, db_ctx, {})
        assert "support assistant" in r["text"].lower()
        assert r["source"] == "greeting"

    def test_asks_for_order_id(self):
        intent = {"primary_intent": "order_status", "confidence": 0.4, "all_intents": [{"intent": "order_status", "score": 0.4}], "matched_keywords": {"order_status": ["order"]}, "explanations": []}
        sentiment = {"label": "neutral", "score": 0, "intensity": 0, "positive_matches": [], "negative_matches": [], "explanations": []}
        proc = preprocess("Where is my order")
        db_ctx = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        r = build_genuine_response(intent, sentiment, proc, db_ctx, {})
        assert "order id" in r["text"].lower()
        assert r["data_verified"] == False

    def test_empathy_on_frustration(self):
        intent = {"primary_intent": "shipping", "confidence": 0.3, "all_intents": [{"intent": "shipping", "score": 0.3}], "matched_keywords": {"shipping": ["package"]}, "explanations": []}
        sentiment = {"label": "negative", "score": -0.7, "intensity": 0.5, "positive_matches": [], "negative_matches": ["frustrated"], "explanations": []}
        proc = preprocess("I'm frustrated my package is lost")
        db_ctx = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        r = build_genuine_response(intent, sentiment, proc, db_ctx, {})
        assert "frustrating" in r["text"].lower() or "apologize" in r["text"].lower()

    def test_id_not_found(self):
        intent = {"primary_intent": "order_status", "confidence": 0.4, "all_intents": [], "matched_keywords": {}, "explanations": []}
        sentiment = {"label": "neutral", "score": 0, "intensity": 0, "positive_matches": [], "negative_matches": [], "explanations": []}
        proc = preprocess("Check ORD-999999")
        db_ctx = {"found": False, "entities": {}, "lookups_performed": ["Looked up order ORD-999999"], "errors": ["Order ORD-999999 was not found in our system."]}
        r = build_genuine_response(intent, sentiment, proc, db_ctx, {"order_id": "ORD-999999"})
        assert "not found" in r["text"].lower()
        assert r["source"] == "id_not_found"


class TestConfidenceScoring:
    def _make_intent(self, name, score):
        return {"primary_intent": name, "confidence": score, "all_intents": [{"intent": name, "score": score}], "matched_keywords": {name: ["test"]}, "explanations": []}

    def _make_sentiment(self, label="neutral"):
        return {"label": label, "score": 0, "intensity": 0, "positive_matches": [], "negative_matches": [], "explanations": []}

    def test_has_5_factors(self):
        c = compute_confidence(self._make_intent("billing", 0.5), self._make_sentiment(), preprocess("refund payment"), {"found": False, "entities": {}, "lookups_performed": [], "errors": []})
        assert len(c["factors"]) == 5
        names = [f["name"] for f in c["factors"]]
        assert "Data Verification" in names

    def test_db_verified_boosts_score(self):
        intent = self._make_intent("billing", 0.5)
        sent = self._make_sentiment()
        proc = preprocess("Check order ORD-100001 refund")
        c_no_db = compute_confidence(intent, sent, proc, {"found": False, "entities": {}, "lookups_performed": [], "errors": []})
        c_with_db = compute_confidence(intent, sent, proc, {"found": True, "entities": {"order": {}}, "lookups_performed": ["Looked up order"], "errors": []})
        assert c_with_db["score"] > c_no_db["score"]

    def test_low_confidence_triggers_handoff(self):
        c = compute_confidence(self._make_intent("unknown", 0.0), self._make_sentiment(), preprocess("xyz"), {"found": False, "entities": {}, "lookups_performed": [], "errors": []})
        assert c["human_handoff_recommended"] == True

    def test_missing_info_suggestions(self):
        c = compute_confidence(self._make_intent("order_status", 0.4), self._make_sentiment(), preprocess("order status"), {"found": False, "entities": {}, "lookups_performed": [], "errors": []})
        assert any("order id" in m.lower() for m in c["missing_information"])

    def test_specificity_is_smooth(self):
        """3-token query should score strictly between 1-token and 10-token."""
        intent = self._make_intent("order_status", 0.5)
        sent = self._make_sentiment()
        db = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        c1  = compute_confidence(intent, sent, preprocess("help"), db)
        c3  = compute_confidence(intent, sent, preprocess("where is order"), db)
        c10 = compute_confidence(intent, sent, preprocess("I need to know where my order is right now"), db)
        spec1  = next(f for f in c1["factors"]  if f["name"] == "Query Specificity")["raw_score"]
        spec3  = next(f for f in c3["factors"]  if f["name"] == "Query Specificity")["raw_score"]
        spec10 = next(f for f in c10["factors"] if f["name"] == "Query Specificity")["raw_score"]
        assert spec1 < spec3 < spec10

    def test_billing_negative_aligns(self):
        """Negative sentiment on billing intent should score 0.9 alignment (90.0 raw)."""
        intent = self._make_intent("billing", 0.6)
        sent = self._make_sentiment("negative")
        db = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        c = compute_confidence(intent, sent, preprocess("I was overcharged"), db)
        alignment_factor = next(f for f in c["factors"] if f["name"] == "Sentiment Alignment")
        assert alignment_factor["raw_score"] == 90.0

    def test_clarity_single_intent_is_full(self):
        """When only one intent fires, clarity should be 100.0."""
        intent = {"primary_intent": "refund", "confidence": 0.8,
                  "all_intents": [{"intent": "refund", "score": 0.8}],
                  "matched_keywords": {"refund": ["refund"]}, "explanations": []}
        sent = self._make_sentiment()
        db = {"found": False, "entities": {}, "lookups_performed": [], "errors": []}
        c = compute_confidence(intent, sent, preprocess("I need a refund"), db)
        clarity_factor = next(f for f in c["factors"] if f["name"] == "Intent Clarity")
        assert clarity_factor["raw_score"] == 100.0


class TestAPI:
    def test_health(self, client):
        r = client.get('/api/health')
        assert r.status_code == 200
        d = json.loads(r.data)
        assert d["status"] == "healthy"

    def test_chat(self, client):
        r = client.post('/api/chat', data=json.dumps({"message": "Hello"}), content_type='application/json')
        assert r.status_code == 200
        d = json.loads(r.data)
        assert "response" in d
        assert "confidence" in d
        assert "explainability" in d
        assert "handoff" in d
        assert len(d["confidence"]["factors"]) == 5

    def test_chat_no_message(self, client):
        r = client.post('/api/chat', data=json.dumps({}), content_type='application/json')
        assert r.status_code == 400

    def test_chat_with_order_id(self, client):
        r = client.post('/api/chat', data=json.dumps({"message": "Status of ORD-100001"}), content_type='application/json')
        d = json.loads(r.data)
        assert d["explainability"]["database"]["ids_extracted"].get("order_id") == "ORD-100001"

    def test_feedback(self, client):
        r = client.post('/api/feedback', data=json.dumps({"rating": 5}), content_type='application/json')
        assert r.status_code == 200


class TestUserAuth:
    def test_user_login_valid(self, client, monkeypatch):
        monkeypatch.setenv("USER_USERNAME", "testuser")
        monkeypatch.setenv("USER_PASSWORD", "testpass")
        monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
        res = client.post("/api/user-login",
                          json={"username": "testuser", "password": "testpass"})
        assert res.status_code == 200
        assert "token" in res.get_json()

    def test_user_login_invalid(self, client, monkeypatch):
        monkeypatch.setenv("USER_USERNAME", "testuser")
        monkeypatch.setenv("USER_PASSWORD", "testpass")
        monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
        res = client.post("/api/user-login",
                          json={"username": "testuser", "password": "wrong"})
        assert res.status_code == 401
        assert res.get_json()["error"] == "Invalid credentials"

    def test_user_login_no_body(self, client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
        res = client.post("/api/user-login", data="notjson",
                          content_type="text/plain")
        assert res.status_code == 400


class TestSentimentEvolution:
    """Rolling session sentiment surfaces a trajectory across messages."""

    def _post(self, client, msg, sid):
        res = client.post("/api/chat", json={"message": msg, "session_id": sid})
        assert res.status_code == 200
        return res.get_json()["explainability"]["sentiment"]

    def test_rolling_score_rises_after_neutral_then_positive(self, client):
        sid = "evo-pos"
        s1 = self._post(client, "where is my order", sid)  # neutral
        s2 = self._post(client, "this is great and amazing", sid)  # positive
        assert s2["rolling_score"] > s1["rolling_score"]
        assert s2["trend"] == "improving"

    def test_delta_negative_on_mood_swing(self, client):
        sid = "evo-swing"
        self._post(client, "this is great and amazing", sid)
        s2 = self._post(client, "this is terrible and awful", sid)
        assert s2["delta"] < 0
        assert s2["trend"] == "worsening"

    def test_rolling_score_drifts_toward_new_signal(self, client):
        sid = "evo-moves"
        self._post(client, "where is my order", sid)            # neutral, ema ≈ 0
        s2 = self._post(client, "this is great", sid)            # positive
        s3 = self._post(client, "this is great", sid)            # positive again
        # EMA keeps drifting toward 1.0 across consecutive positives after a neutral start.
        assert s3["rolling_score"] > s2["rolling_score"] or s3["rolling_score"] == s2["rolling_score"] == 1.0
        assert len(s3["history"]) == 3

    def test_history_grows_with_session(self, client):
        sid = "evo-hist"
        for msg in ["hello", "thanks", "goodbye"]:
            last = self._post(client, msg, sid)
        assert len(last["history"]) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
