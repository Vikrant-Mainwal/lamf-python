import re
from dataclasses import dataclass


STOP_WORDS = {
    "fund", "growth", "direct", "plan", "option", "regular",
    "series", "scheme", "the", "a", "of", "and",
}

# Known short aliases that users type (Hinglish / casual)
ALIASES: dict[str, str] = {
    "mirae":   "mirae asset",
    "parag":   "parag parikh",
    "ppfas":   "parag parikh",
    "axis mf": "axis",
    "sbi mf":  "sbi",
    "hdfc mf": "hdfc",
}


@dataclass
class FundMatch:
    fund: dict
    score: int
    confidence: str   # "high" | "medium" | "low"


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    tokens = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()
    return [t for t in tokens if t not in STOP_WORDS]


def _apply_aliases(text: str) -> str:
    lower = text.lower()
    for alias, expanded in ALIASES.items():
        if alias in lower:
            lower = lower.replace(alias, expanded)
    return lower


def find_best_fund(message: str, funds: list[dict]) -> FundMatch | None:
    """
    Score each fund against the message.
    Returns the best match only if confidence is 'medium' or better.
    """
    msg_expanded = _apply_aliases(message)
    msg_tokens   = set(_tokenize(msg_expanded))

    if not msg_tokens:
        return None

    best: FundMatch | None = None

    for fund in funds:
        name        = fund.get("scheme", "")
        name_tokens = set(_tokenize(name))

        overlap = msg_tokens & name_tokens
        score   = len(overlap)

        # Bonus: multi-word phrase match beats single token
        name_lower = name.lower()
        for token in msg_tokens:
            if len(token) > 4 and token in name_lower:
                score += 1

        if score == 0:
            continue

        confidence = "high" if score >= 3 else "medium" if score >= 2 else "low"

        if best is None or score > best.score:
            best = FundMatch(fund=fund, score=score, confidence=confidence)

    if best and best.confidence in ("high", "medium"):
        return best

    return None