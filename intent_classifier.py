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
        "good morning", "good evening", "howdy",
    ],
    Intent.LOAN_QUERY: [
        "loan", "borrow", "kitna milega", "how much", "eligible",
        "interest", "intrest", "emi", "repay", "lend", "credit",
        "lamf", "pledge", "pledging", "max loan", "borrowing",
    ],
    Intent.FUND_QUERY: [
        "fund", "scheme", "sip", "nav", "units", "holdings",
        "portfolio", "protfolio", "mutual fund", "mirae", "sbi",
        "hdfc", "icici", "axis", "kotak", "nippon", "parag",
    ],
    Intent.ADVISORY: [
        "need", "chahiye", "planning", "want", "should i", "advise",
        "suggest", "what should", "kya karu", "help me", "how can i",
        "₹", "rs ", "rupees", "lakh", "thousand",
    ],
    Intent.RISK_QUERY: [
        "risk", "margin call", "market fall", "drop", "safe",
        "danger", "volatile", "crash", "gilta", "nuksaan",
    ],
    Intent.OFF_TOPIC: [],   # fallback – assigned if nothing else scores ≥ threshold
}

THRESHOLD = 1          # minimum score to assign an intent
ADVISORY_AMOUNT_RE = re.compile(r"(₹|rs\.?|inr)\s*\d", re.IGNORECASE)


@dataclass
class ClassifiedIntent:
    intent: Intent
    confidence: float          # 0-1, useful for logging
    raw_scores: dict[str, int] # for debugging


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9₹ ]", "", text.lower()).strip()


def classify(message: str) -> ClassifiedIntent:
    msg = normalize(message)

    scores: dict[Intent, int] = {intent: 0 for intent in Intent}

    for intent, keywords in SIGNALS.items():
        for kw in keywords:
            if kw in msg:
                scores[intent] += 2 if len(kw.split()) > 1 else 1

    # ── Boosters
    # If message contains a rupee amount AND advisory signals → strong advisory
    if ADVISORY_AMOUNT_RE.search(message):
        scores[Intent.ADVISORY] += 3

    # Greetings are short – if msg is ≤ 3 words and has greeting signal, boost
    if len(msg.split()) <= 3 and scores[Intent.GREETING] > 0:
        scores[Intent.GREETING] += 2

    # ── Pick winner
    best_intent = max(scores, key=lambda i: scores[i])
    best_score  = scores[best_intent]

    if best_score < THRESHOLD:
        best_intent = Intent.OFF_TOPIC
        best_score  = 0

    total = sum(scores.values()) or 1
    confidence = min(best_score / total, 1.0)

    return ClassifiedIntent(
        intent=best_intent,
        confidence=round(confidence, 3),
        raw_scores={i.value: s for i, s in scores.items()},
    )