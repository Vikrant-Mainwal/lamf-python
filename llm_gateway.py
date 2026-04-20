import os
from urllib import response
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


# System prompt factory
def _build_system_prompt(portfolio: dict) -> str:
    investor = portfolio.get("investor", {}).get("name", "User")
    summ     = portfolio.get("summary", {})
    ltv      = portfolio.get("ltv", {})

    return f"""You are a warm, smart assistant for Loans Against Mutual Funds (LAMF).

INVESTOR PORTFOLIO (only use these numbers, never guess):
- Name: {investor}
- Portfolio value: ₹{summ.get("total_portfolio_value", 0):,.0f}
- Pledgeable value: ₹{summ.get("pledgeable_portfolio_value", 0):,.0f}
- Max loan eligible: ₹{ltv.get("total_eligible_loan", 0):,.0f}
- Margin call buffer: {ltv.get("portfolio_margin_call_drop_pct", 0)}%

YOUR JOB:
- Understand what the user MEANS, not just what they typed
- Handle typos, Hinglish, broken English, slang — figure it out
- If a question is even loosely about loans, funds, investing, or money — answer it helpfully
- Only redirect if it's truly unrelated (sports, cooking, movies, etc.)

HOW TO REPLY:
- 2–3 sentences, conversational, like a smart friend explaining it
- No bullet points unless listing actual steps (3+)
- No "Key insight / Risk / Action" format — just talk naturally
- Don't repeat portfolio numbers unless the user asked about them

LAMF KNOWLEDGE:
- Equity funds: 60–70% LTV, higher risk of margin calls
- Debt funds: 80% LTV, safer
- ELSS funds: cannot be pledged (lock-in)
- Interest: ~9.99%–12% p.a.
- Margin call triggers if portfolio drops beyond the buffer %
- Process: select funds → pledge online → get loan in account (usually same day)

LOAN PROCESS (explain this when asked):
1. User selects which mutual funds to pledge
2. Funds are pledged online via CAMS/KFintech (no selling needed)
3. Loan is approved and amount credited to bank account (same day usually)
4. User pays interest only on amount used (like an overdraft)
5. Repay anytime — funds get unpledged automatically

IMPORTANT: When explaining process, be conversational. Don't dump portfolio 
numbers unless the user asked for them specifically.
"""
# Public API
def call_llm(
    message: str,
    portfolio: dict,
    history: list[dict],
    intent: str = "unknown",
) -> str:
    try:
        # Build system prompt
        system_prompt = _build_system_prompt(portfolio)
        intent_line = f"\nUser intent: {intent}\nRespond accordingly.\n"

        messages = [{"role": "system", "content": system_prompt + intent_line}]

        # Add history
        for turn in history[-8:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({
                    "role": turn["role"],
                    "content": turn["content"]
                })

        # Add current message
        messages.append({"role": "user", "content": message})

        # Call LLM
        completion = _get_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.5,
            max_completion_tokens=200,
        )

        # Safe extraction
        response = (
            completion.choices[0].message.content.strip()
            if completion.choices and completion.choices[0].message.content
            else ""
        )

        if not response:
            response = "I couldn't generate a detailed answer, but here's a quick insight based on your portfolio."

    except Exception as e:
        print("LLM ERROR:", e)
        response = "I'm facing a temporary issue, but here's a quick insight based on your portfolio."

    # Debug logs (outside except so always prints)
    # print("\n===== LLM RESPONSE =====")
    # print(response)
    # print("========================\n")

    return response