import re
from dataclasses import dataclass

MAX_RESPONSE_CHARS = 900


@dataclass
class FormattedResponse:
    text: str
    source: str   # "deterministic" | "advisory" | "llm" | "fallback"
    intent: str


# Hallucination guard

def _extract_rupee_values(text: str) -> list[float]:
    return [
        float(m.replace(",", ""))
        for m in re.findall(r"₹([\d,]+)", text)
    ]


def guard_llm_response(llm_text: str, portfolio: dict) -> str:
    real_values = {
        portfolio["ltv"].get("total_eligible_loan", 0),
        portfolio["summary"].get("total_portfolio_value", 0),
        portfolio["summary"].get("pledgeable_portfolio_value", 0),
        *[f.get("max_loan", 0) for f in portfolio.get("funds", [])],
        *[f.get("current_value", 0) for f in portfolio.get("funds", [])],
    }
    mentioned  = _extract_rupee_values(llm_text)
    suspicious = [v for v in mentioned if v > 0 and v not in real_values]
    if suspicious:
        llm_text += "\n\n'Tip': Verify exact amounts in your portfolio dashboard."
    return llm_text


# Formatters

def format_greeting(portfolio: dict) -> FormattedResponse:
    name  = portfolio.get("investor", {}).get("name", "there")
    first = name.split()[0] if name else "there"
    loan  = portfolio["ltv"].get("total_eligible_loan", 0)

    # Warm, short — not a dashboard dump
    text = (
        f"Hey {first}! 👋 You can borrow up to ₹{loan:,.0f} against your "
        f"mutual funds. Ask me anything — loan process, which funds to pledge, "
        f"risk, or how much you need."
    )
    return FormattedResponse(text=text, source="deterministic", intent="greeting")


def format_loan_query(portfolio: dict) -> FormattedResponse:
    """Only called when user explicitly wants their loan numbers."""
    ltv   = portfolio.get("ltv", {})
    summ  = portfolio.get("summary", {})

    loan   = ltv.get("total_eligible_loan", 0)
    pledge = summ.get("pledgeable_portfolio_value", 0)
    total  = summ.get("total_portfolio_value", 0)
    margin = ltv.get("portfolio_margin_call_drop_pct", 0)
    usage  = int((loan / pledge * 100) if pledge else 0)

    text = (
        f"Here's your loan snapshot:\n\n"
        f"• Max loan: ₹{loan:,.0f}\n"
        f"• Pledgeable funds: ₹{pledge:,.0f}\n"
        f"• Total portfolio: ₹{total:,.0f}\n"
        f"• Margin call triggers if portfolio drops {margin}%\n\n"
        f"You're at {usage}% of your borrowing limit. "
        f"Want help deciding which funds to pledge?"
    )
    return FormattedResponse(text=text, source="deterministic", intent="loan_query")


def format_fund(fund: dict, portfolio: dict) -> FormattedResponse:
    name  = fund.get("scheme", "This fund").split(" - ")[0]
    value = fund.get("current_value", 0)
    loan  = fund.get("max_loan", 0)
    ltv   = fund.get("ltv", 0) * 100

    # Give context, not just raw numbers
    ltv_note = (
        "debt fund (safer, higher LTV)" if ltv >= 75
        else "equity fund (higher return potential, slightly more risk)"
    )

    text = (
        f"{name} is a {ltv_note}.\n\n"
        f"• Current value: ₹{value:,.0f}\n"
        f"• You can borrow: ₹{loan:,.0f} ({ltv:.0f}% LTV)\n\n"
        f"Want to use this fund for a loan, or compare it with others?"
    )
    return FormattedResponse(text=text, source="deterministic", intent="fund_query")


def format_advisory(plan, portfolio: dict) -> FormattedResponse:
    """Deterministic plan — keep concise, invite follow-up."""
    lines = "\n".join(f"• {line}" for line in plan.summary_lines)
    text  = (
        f"For ₹{plan.target_amount:,.0f}, here's the plan:\n\n"
        f"{lines}\n\n"
        f"Want me to explain the margin call risk or interest cost?"
    )
    return FormattedResponse(text=text, source="advisory", intent="advisory")


def format_off_topic() -> FormattedResponse:
    """
    Last resort only — LLM should have tried first.
    Keep it friendly, not dismissive.
    """
    text = (
        "That's a bit outside my lane! I'm best at:\n\n"
        "• How much loan you can get\n"
        "• Which funds to pledge\n"
        "• Loan process & steps\n"
        "• Margin call risk\n\n"
        "What would you like to know? 😊"
    )
    return FormattedResponse(text=text, source="deterministic", intent="off_topic")


def format_llm(llm_text: str, portfolio: dict, intent: str) -> FormattedResponse:
    guarded = guard_llm_response(llm_text, portfolio)
    # Trim if too long — break at last newline to avoid mid-sentence cuts
    if len(guarded) > MAX_RESPONSE_CHARS:
        guarded = guarded[:MAX_RESPONSE_CHARS].rsplit("\n", 1)[0] + "\n…"
    return FormattedResponse(text=guarded, source="llm", intent=intent)


def format_fallback(portfolio: dict) -> FormattedResponse:
    loan  = portfolio.get("ltv", {}).get("total_eligible_loan", 0)
    total = portfolio.get("summary", {}).get("total_portfolio_value", 0)
    text  = (
        f"Quick summary while I recover:\n\n"
        f"• Max loan: ₹{loan:,.0f}\n"
        f"• Portfolio: ₹{total:,.0f}\n\n"
        f"Try asking again — I'm here! 😊"
    )
    return FormattedResponse(text=text, source="fallback", intent="unknown")