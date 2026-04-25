import os
import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

logger.info("Initializing ML Service & loading Hugging Face models...")

CUSTOM_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "custom-intent")
INTENT_LABELS = [
    "order_status", "refund", "shipping", "technical",
    "subscription", "account", "billing", "greeting", "unknown"
]

try:
    # 1. Intent Classifier — prefer fine-tuned model, fall back to zero-shot base
    if os.path.isfile(os.path.join(CUSTOM_MODEL_DIR, "model.safetensors")):
        logger.info("Loading fine-tuned intent classifier from %s", CUSTOM_MODEL_DIR)
        intent_classifier = pipeline(
            "text-classification",
            model=CUSTOM_MODEL_DIR,
            top_k=None
        )
        USE_FINETUNED = True
    else:
        logger.info("No fine-tuned model found — using zero-shot base model")
        intent_classifier = pipeline(
            "zero-shot-classification",
            model="valhalla/distilbart-mnli-12-1"
        )
        USE_FINETUNED = False

    # 2. Sentiment Analyzer
    sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest"
    )

    logger.info("✅ ML Models loaded successfully!")
except Exception as e:
    logger.error(f"Failed to load ML models: {e}")
    intent_classifier = None
    sentiment_analyzer = None
    USE_FINETUNED = False

def ml_classify_intent(text: str) -> dict:
    if not intent_classifier:
        return {"primary_intent": "unknown", "confidence": 0.0, "all_candidates": [], "matched_keywords": {}}

    if USE_FINETUNED:
        # text-classification returns list of {label, score} sorted by score desc
        res = intent_classifier(text)[0]
        res_sorted = sorted(res, key=lambda x: x["score"], reverse=True)
        # Map LABEL_N back to intent name
        top = res_sorted[0]
        idx = int(top["label"].split("_")[1])
        primary_intent = INTENT_LABELS[idx] if idx < len(INTENT_LABELS) else "unknown"
        confidence = top["score"]
        candidates = [
            {"intent": INTENT_LABELS[int(r["label"].split("_")[1])], "score": r["score"]}
            for r in res_sorted if int(r["label"].split("_")[1]) < len(INTENT_LABELS)
        ]
    else:
        # Zero-shot classification
        res = intent_classifier(text, candidate_labels=INTENT_LABELS, multi_label=False)
        primary_intent = res["labels"][0]
        confidence = res["scores"][0]
        candidates = [{"intent": l, "score": s} for l, s in zip(res["labels"], res["scores"])]

    if confidence < 0.2:
        primary_intent = "unknown"

    return {
        "primary_intent": primary_intent,
        "confidence": confidence,
        "all_candidates": candidates,
        "matched_keywords": {}
    }

_SENTIMENT_LABEL_MAP = {
    "label_0": "negative",
    "label_1": "neutral",
    "label_2": "positive",
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
}

def ml_analyze_sentiment(text: str) -> dict:
    if not sentiment_analyzer:
        return {"label": "neutral", "score": 0.5, "explanation": "ML unavailable"}

    res = sentiment_analyzer(text)[0]
    mapped_label = _SENTIMENT_LABEL_MAP.get(res["label"].lower(), "neutral")

    return {
        "label": mapped_label,
        "score": round(res["score"], 2),
        "explanation": f"ML model detected {mapped_label} sentiment with {res['score']:.1%} confidence.",
    }
