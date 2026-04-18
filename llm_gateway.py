import os
from groq import Groq

_client: Groq | None = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise EnvironmentError("GROQ_API_KEY not set")
        _client = Groq(api_key=key)
    return _client


# ── System prompt factory ─────────────────────────────────────────────────────

def _build_system_prompt(portfolio: dict) -> str:
    investor = portfolio.get("investor", {}).get("name", "User")
    summ     = portfolio.get("summary", {})
    ltv      = portfolio.get("ltv", {})

    # Only inject verified numbers – model cannot invent amounts
    return f"""You are a concise fintech assistant for Loans Against Mutual Funds (LAMF).

VERIFIED PORTFOLIO DATA (do NOT invent other amounts):
- Investor: {investor}
- Portfolio value: ₹{summ.get("total_portfolio_value", 0):,.0f}
- Pledgeable value: ₹{summ.get("pledgeable_portfolio_value", 0):,.0f}
- Eligible loan: ₹{ltv.get("total_eligible_loan", 0):,.0f}
- Margin call buffer: {ltv.get("portfolio_margin_call_drop_pct", 0)}%

RULES:
1. Answer in ≤6 lines. Use bullet points.
2. Only use ₹ amounts from the data above. Never invent figures.
3. Handle Hinglish and typos gracefully.
4. If the question is unrelated to loans/funds, redirect politely.
5. Tone: friendly, like Groww or Zerodha app.

KNOWLEDGE:
- Equity funds: ~60-70% LTV | Debt funds: ~80% LTV
- ELSS funds cannot be pledged
- Interest rates: ~10–12% p.a.
- Margin call triggers if portfolio drops by the buffer % above
"""


# ── Public API ─────────────────────────────────────────────────────────────────

def call_llm(
    message: str,
    portfolio: dict,
    history: list[dict],
    intent: str = "unknown",
) -> str:
    """
    Call the LLM with trimmed context.
    Returns raw text (caller should pass through formatter).
    """
    messages = [{"role": "system", "content": _build_system_prompt(portfolio)}]

    # Trim history to last 8 turns (4 user + 4 assistant)
    for turn in history[-8:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": message})

    completion = _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.4,          # lower = more factual
        max_completion_tokens=400, # hard cap
    )

    return completion.choices[0].message.content.strip()