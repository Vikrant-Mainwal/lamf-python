import re
from dataclasses import dataclass


AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:k|l|lakh|lacs?|thousand)?",
    re.IGNORECASE,
)


@dataclass
class AdvisoryPlan:
    target_amount: float
    feasible: bool
    total_eligible: float
    shortfall: float
    recommended_funds: list[dict]   # top funds to pledge
    utilisation_pct: float
    margin_buffer_pct: float
    summary_lines: list[str]        # pre-formatted bullet strings


def _parse_amount(message: str) -> float | None:
    """Extract rupee amount from user message."""
    m = AMOUNT_RE.search(message.lower())
    if not m:
        return None

    raw   = m.group(1).replace(",", "")
    value = float(raw)

    suffix = (m.group(0) or "").lower()
    if "lakh" in suffix or "lac" in suffix or suffix.strip().endswith("l"):
        value *= 100_000
    elif "k" in suffix or "thousand" in suffix:
        value *= 1_000

    return value


def _rank_funds(funds: list[dict]) -> list[dict]:
    """Sort funds by max_loan descending, ELSS excluded (can't pledge)."""
    eligible = [f for f in funds if not f.get("is_elss", False)]
    return sorted(eligible, key=lambda f: f.get("max_loan", 0), reverse=True)


def build_plan(message: str, portfolio: dict) -> AdvisoryPlan | None:
    target = _parse_amount(message)
    if target is None:
        return None

    funds         = portfolio.get("funds", [])
    ltv_data      = portfolio.get("ltv", {})
    total_eligible= ltv_data.get("total_eligible_loan", 0)
    margin_buffer = ltv_data.get("portfolio_margin_call_drop_pct", 0)

    feasible      = total_eligible >= target
    shortfall     = max(0, target - total_eligible)
    utilisation   = round((target / total_eligible * 100) if total_eligible else 0, 1)

    ranked        = _rank_funds(funds)
    recommended   = []
    running_loan  = 0.0

    for fund in ranked:
        if running_loan >= target:
            break
        recommended.append(fund)
        running_loan += fund.get("max_loan", 0)

    plan = AdvisoryPlan(
        target_amount      = target,
        feasible           = feasible,
        total_eligible     = total_eligible,
        shortfall          = shortfall,
        recommended_funds  = recommended,
        utilisation_pct    = utilisation,
        margin_buffer_pct  = margin_buffer,
        summary_lines      = [],
    )

    plan.summary_lines = _format_summary(plan)
    return plan


def _format_summary(plan: AdvisoryPlan) -> list[str]:
    lines = [
        f"Target loan: ₹{plan.target_amount:,.0f}",
        f"Total eligible: ₹{plan.total_eligible:,.0f}",
    ]

    if plan.feasible:
        lines.append(f" Feasible — you have enough borrowing capacity")
    else:
        lines.append(f" Shortfall of ₹{plan.shortfall:,.0f} — portfolio may need top-up")

    if plan.recommended_funds:
        names = ", ".join(
            f["scheme"].split(" - ")[0] for f in plan.recommended_funds[:2]
        )
        lines.append(f"Pledge first: {names}")

    lines.append(f"Portfolio utilisation: {plan.utilisation_pct}%")

    if plan.margin_buffer_pct < 15:
        lines.append(f" Margin buffer is tight ({plan.margin_buffer_pct}%) — market risk is elevated")
    else:
        lines.append(f"Margin buffer: {plan.margin_buffer_pct}% — you're in a safe zone")

    return lines