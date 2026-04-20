from dataclasses import dataclass
from enum import Enum
import re

class Intent(str, Enum):
    GREETING     = "greeting"
    LOAN_QUERY   = "loan_query"
    FUND_QUERY   = "fund_query"
    ADVISORY     = "advisory"
    RISK_QUERY   = "risk_query"
    OFF_TOPIC    = "off_topic"


# ── Keyword signal maps
SIGNALS: dict[Intent, list[str]] = {
    Intent.GREETING: [
        "hi", "hello", "hey", "namaste", "hii", "helo", "sup",
        "good morning", "good evening", "howdy", "yo", "hiya",
    ],
    Intent.LOAN_QUERY: [
        "loan", "borrow", "eligible", "interest", "emi", "repay",
        "lamf", "pledge", "pledging", "max loan", "borrowing",
        "process", "how to get", "loan against", "apply", "kitna",
        "milega", "kaise", "steps", "procedure", "kya hai",
        "what is", "explain", "tell me about loan", "loan kaise",
    ],
    Intent.FUND_QUERY: [
        "fund", "scheme", "sip", "nav", "units", "holdings",
        "portfolio", "mutual fund", "mirae", "sbi", "hdfc",
        "icici", "axis", "kotak", "nippon", "parag", "which fund",
        "best fund", "top fund", "konsa fund",
    ],
    Intent.ADVISORY: [
        "need", "chahiye", "planning", "want", "should i", "advise",
        "suggest", "what should", "help me", "how can i", "recommend",
        "₹", "rs ", "rupees", "lakh", "thousand", "crore",
        "best way", "better", "which one", "kya karu", "guide",
    ],
    Intent.RISK_QUERY: [
        "risk", "margin call", "market fall", "drop", "safe",
        "danger", "volatile", "crash", "loss", "nuksaan", "gilta",
        "what if market", "portfolio falls",
    ],
    Intent.OFF_TOPIC: [],
}


THRESHOLD = 1          # minimum score to assign an intent
ADVISORY_AMOUNT_RE = re.compile(r"(₹|rs\.?|inr)\s*\d", re.IGNORECASE)


@dataclass
class ClassifiedIntent:
    intent: Intent
    confidence: float          # 0-1, useful for logging
    raw_scores: dict[str, int] # for debugging


def _fuzzy_score(msg_tokens: list[str], keywords: list[str]) -> int:
    score = 0
    for kw in keywords:
        kw_parts = kw.split()
        if all(part in msg_tokens for part in kw_parts):
            score += len(kw_parts) + 1   # multi-word = stronger signal
        elif any(part in msg_tokens for part in kw_parts):
            score += 1
    return score


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9₹ ]", "", text.lower()).strip()

def classify(message: str) -> ClassifiedIntent:
    msg = normalize(message)
    msg_tokens = msg.split()

    scores: dict[Intent, int] = {intent: 0 for intent in Intent}

    for intent, keywords in SIGNALS.items():
        scores[intent] = _fuzzy_score(msg_tokens, keywords)

    # Boosters
    if ADVISORY_AMOUNT_RE.search(message):
        scores[Intent.ADVISORY] += 3

    if len(msg_tokens) <= 3 and scores[Intent.GREETING] > 0:
        scores[Intent.GREETING] += 2

    best_intent = max(scores, key=lambda i: scores[i])
    best_score  = scores[best_intent]

    # LOW CONFIDENCE → don't hard-refuse, let LLM decide
    if best_score < THRESHOLD:
        best_intent = Intent.ADVISORY   # ← route to LLM advisory, not OFF_TOPIC
        best_score  = 0

    total = sum(scores.values()) or 1
    confidence = min(best_score / total, 1.0)

    return ClassifiedIntent(
        intent=best_intent,
        confidence=round(confidence, 3),
        raw_scores={i.value: s for i, s in scores.items()},
    )