import logging
from intent_classifier import classify, Intent
from fund_matcher       import find_best_fund
from advisory_engine    import build_plan
from llm_gateway        import call_llm
from response_formatter import (
    FormattedResponse,
    format_greeting,
    format_loan_query,
    format_fund,
    format_advisory,
    format_off_topic,
    format_llm,
    format_fallback,
)

log = logging.getLogger(__name__)


# Intent handlers
# Each handler: (msg, portfolio, history) -> FormattedResponse

def _handle_greeting(msg, portfolio, history):
    return format_greeting(portfolio)


def _handle_loan_query(msg, portfolio, history):
    return format_loan_query(portfolio)


def _handle_fund_query(msg, portfolio, history):
    funds = portfolio.get("funds", [])
    match = find_best_fund(msg, funds)

    if match:
        return format_fund(match.fund, portfolio)

    # Fund mentioned but couldn't match → ask LLM to clarify
    llm_text = call_llm(msg, portfolio, history, intent="fund_query")
    return format_llm(llm_text, portfolio, "fund_query")


def _handle_advisory(msg, portfolio, history):
    plan = build_plan(msg, portfolio)

    if plan:
        resp = format_advisory(plan, portfolio)

        # Add LLM wrap for natural advice after deterministic plan
        llm_ctx = (
            f"User asked: {msg}\n"
            f"Plan summary: {'; '.join(plan.summary_lines)}\n"
            "Give 1-2 lines of natural, friendly follow-up advice. "
            "Do NOT repeat the numbers above."
        )
        try:
            llm_suffix = call_llm(llm_ctx, portfolio, history, intent="advisory")
            resp.text += f"\n\n{llm_suffix}"
        except Exception as e:
            log.warning("LLM suffix failed for advisory: %s", e)

        return resp

    # Couldn't parse amount → full LLM
    llm_text = call_llm(msg, portfolio, history, intent="advisory")
    return format_llm(llm_text, portfolio, "advisory")


def _handle_risk_query(msg, portfolio, history):
    llm_text = call_llm(msg, portfolio, history, intent="risk_query")
    return format_llm(llm_text, portfolio, "risk_query")


def _handle_off_topic(msg, portfolio, history):
    return format_off_topic()


# Dispatch table (replaces if-else chain) 

HANDLERS = {
    Intent.GREETING   : _handle_greeting,
    Intent.LOAN_QUERY : _handle_loan_query,
    Intent.FUND_QUERY : _handle_fund_query,
    Intent.ADVISORY   : _handle_advisory,
    Intent.RISK_QUERY : _handle_risk_query,
    Intent.OFF_TOPIC  : _handle_off_topic,
}


# Public entry point 

def get_chat_response(
    message: str,
    portfolio: dict,
    history: list[dict],
) -> str:
    log.info("Incoming: %.80s", message)

    try:
        #  1. Classify intent
        classified = classify(message)
        intent = classified.intent

        log.info(
            "Initial Intent: %s (confidence=%.2f)",
            intent,
            classified.confidence,
        )

        # 2. FUND OVERRIDE
        funds = portfolio.get("funds", [])
        fund_match = find_best_fund(message, funds)

        if fund_match and fund_match.confidence in ("high", "medium"):
            log.info("Fund detected → overriding intent to FUND_QUERY")
            intent = Intent.FUND_QUERY

        # 3. Route to handler
        handler = HANDLERS.get(intent, _handle_off_topic)

        result: FormattedResponse = handler(message, portfolio, history)

        log.info(
            "Final Intent: %s | Source: %s",
            result.intent,
            result.source,
        )

        return result.text

    except Exception as exc:
        log.exception("chat_engine error: %s", exc)
        return format_fallback(portfolio).text