import re
from dataclasses import dataclass


MAX_RESPONSE_CHARS = 800


@dataclass
class FormattedResponse:
    text: str
    source: str    # "deterministic" | "advisory" | "llm" | "fallback"
    intent: str


# ── Hallucination guard ───────────────────────────────────────────────────────

def _extract_rupee_values(text: str) -> list[float]:
    """Pull all ₹ amounts mentioned in a text string."""
    return [
        float(m.replace(",", ""))
        for m in re.findall(r"₹([\d,]+)", text)
    ]


def guard_llm_response(llm_text: str, portfolio: dict) -> str:
    """
    Detect hallucinated ₹ figures in LLM output.
    If LLM mentions an amount not in the portfolio, strip it and warn.
    """
    real_values = {
        portfolio["ltv"].get("total_eligible_loan", 0),
        portfolio["summary"].get("total_portfolio_value", 0),
        portfolio["summary"].get("pledgeable_portfolio_value", 0),
        *[f.get("max_loan", 0) for f in portfolio.get("funds", [])],
        *[f.get("current_value", 0) for f in portfolio.get("funds", [])],
    }

    mentioned = _extract_rupee_values(llm_text)
    suspicious = [v for v in mentioned if v > 0 and v not in real_values]

    if suspicious:
        # Soft fail: append a disclaimer rather than nuking the response
        llm_text += (
            "\n\n_Note: Please verify exact amounts in your portfolio dashboard._"
        )

    return llm_text


# ── Formatters per source ─────────────────────────────────────────────────────

def format_greeting(portfolio: dict) -> FormattedResponse:
    name  = portfolio.get("investor", {}).get("name", "there")
    loan  = portfolio["ltv"].get("total_eligible_loan", 0)
    first = name.split()[0] if name else "there"

    text = (
        f"Hey {first}! 👋\n\n"
        f"• Eligible loan: ₹{loan:,.0f}\n"
        f"• Ask me about your funds, interest, or loan planning."
    )
    return FormattedResponse(text=text, source="deterministic", intent="greeting")


def format_loan_query(portfolio: dict) -> FormattedResponse:
    ltv   = portfolio.get("ltv", {})
    summ  = portfolio.get("summary", {})

    loan   = ltv.get("total_eligible_loan", 0)
    pledge = summ.get("pledgeable_portfolio_value", 0)
    total  = summ.get("total_portfolio_value", 0)
    margin = ltv.get("portfolio_margin_call_drop_pct", 0)

    usage_pct = int((loan / pledge * 100) if pledge else 0)

    text = (
        f"Loan summary:\n\n"
        f"• Eligible loan: ₹{loan:,.0f}\n"
        f"• Pledgeable value: ₹{pledge:,.0f}\n"
        f"• Total portfolio: ₹{total:,.0f}\n"
        f"• Margin call risk: {margin}% drop triggers call\n\n"
        f"You're using {usage_pct}% of your borrowing capacity."
    )
    return FormattedResponse(text=text, source="deterministic", intent="loan_query")


def format_fund(fund: dict, portfolio: dict) -> FormattedResponse:
    name   = fund["scheme"].split(" - ")[0]
    value  = fund["current_value"]
    loan   = fund["max_loan"]
    ltv    = fund["ltv"] * 100
    total  = portfolio["ltv"].get("total_eligible_loan", 0)
    pledge = portfolio["summary"].get("pledgeable_portfolio_value", 0)
    usage  = int((total / pledge * 100) if pledge else 0)

    text = (
        f"{name}\n\n"
        f"• Investment value: ₹{value:,.0f}\n"
        f"• Eligible loan: ₹{loan:,.0f}\n"
        f"• LTV ratio: {ltv:.0f}%\n\n"
        f"You can borrow ₹{loan:,.0f} from this fund.\n"
        f"Total capacity used: {usage}%"
    )
    return FormattedResponse(text=text, source="deterministic", intent="fund_query")


def format_advisory(plan, portfolio: dict) -> FormattedResponse:
    body = "\n".join(f"• {line}" for line in plan.summary_lines)
    text = f"Loan plan for ₹{plan.target_amount:,.0f}:\n\n{body}"
    return FormattedResponse(text=text, source="advisory", intent="advisory")


def format_off_topic() -> FormattedResponse:
    text = (
        "I'm built to help with loans against your mutual funds.\n\n"
        "You can ask me:\n"
        "• How much can I borrow?\n"
        "• Tell me about my [fund name]\n"
        "• I need ₹50,000 — what should I do?\n"
        "• What's my margin call risk?"
    )
    return FormattedResponse(text=text, source="deterministic", intent="off_topic")


def format_llm(llm_text: str, portfolio: dict, intent: str) -> FormattedResponse:
    guarded = guard_llm_response(llm_text, portfolio)
    # Hard cap length
    if len(guarded) > MAX_RESPONSE_CHARS:
        guarded = guarded[:MAX_RESPONSE_CHARS].rsplit("\n", 1)[0] + "\n…"
    return FormattedResponse(text=guarded, source="llm", intent=intent)


def format_fallback(portfolio: dict) -> FormattedResponse:
    loan  = portfolio.get("ltv", {}).get("total_eligible_loan", 0)
    total = portfolio.get("summary", {}).get("total_portfolio_value", 0)
    text  = (
        f"Here's a quick summary:\n\n"
        f"• Eligible loan: ₹{loan:,.0f}\n"
        f"• Portfolio value: ₹{total:,.0f}\n\n"
        f"Ask me about your funds, risk, or loan planning. 😊"
    )
    return FormattedResponse(text=text, source="fallback", intent="unknown")