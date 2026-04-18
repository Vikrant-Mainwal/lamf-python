import math
import urllib.request
import json
from datetime import datetime

# Base LTV by category (SEBI-aligned + risk buffer)
BASE_LTV = {
    "liquid":       0.90,
    "debt":         0.80,
    "hybrid":       0.70,
    "large_cap":    0.65,
    "large_mid_cap":0.62,
    "flexi_cap":    0.60,
    "mid_small_cap":0.50,
    "sectoral":     0.40,
    "elss":         0.00,   # not pledgeable
}

def calculate_eligible_loan(funds: list) -> dict:
    result_funds = []
    total_loan = 0.0
    pledgeable_value = 0.0

    nav_cache = {}

    for fund in funds:
        if not fund.get("is_pledgeable", False):
            result_funds.append({
                **fund,
                "ltv": 0.0,
                "max_loan": 0.0,
                "ltv_reason": "Not pledgeable (ELSS/locked)"
            })
            continue

        category = fund.get("category", "flexi_cap")
        scheme_code = fund.get("scheme_code")

        # Cached NAV fetch
        if scheme_code:
            if scheme_code in nav_cache:
                fund["nav"] = nav_cache[scheme_code]
            else:
                latest_nav = fetch_latest_nav(scheme_code)
                if latest_nav:
                    nav_cache[scheme_code] = latest_nav
                    fund["nav"] = latest_nav

        base_ltv = BASE_LTV.get(category, 0.55)

        ltv, reasons = _apply_adjustments(base_ltv, fund)

        max_loan = round(fund["current_value"] * ltv, 2)

        total_loan += max_loan
        pledgeable_value += fund["current_value"]

        margin_drop = _margin_call_drop(
            fund["nav"],
            fund["units"],
            max_loan,
            ltv
        )

        result_funds.append({
            **fund,
            "ltv": round(ltv, 2),
            "max_loan": max_loan,
            "ltv_reason": " | ".join(reasons) if reasons else "Standard LTV applied",
            "margin_call_nav": round(fund["nav"] * (1 - margin_drop / 100), 2) if margin_drop else None,
            "margin_call_drop_pct": round(margin_drop, 2) if margin_drop else None,
        })

    pledgeable_funds = [f for f in result_funds if f.get("max_loan", 0) > 0]
    portfolio_margin = _portfolio_margin_drop(pledgeable_funds)

    return {
        "funds": result_funds,
        "total_eligible_loan": round(total_loan, 2),
        "total_portfolio_value": round(sum(f["current_value"] for f in funds), 2),
        "pledgeable_value": round(pledgeable_value, 2),
        "portfolio_ltv": round(total_loan / pledgeable_value, 2) if pledgeable_value > 0 else 0,
        "portfolio_margin_call_drop_pct": portfolio_margin,
        "calculated_at": datetime.utcnow().isoformat(),
    }

def _apply_adjustments(base_ltv: float, fund: dict) -> tuple:
    """Apply risk adjustments to base LTV. Returns (final_ltv, [reason strings])."""
        
    ltv     = base_ltv
    reasons = []

    if fund.get("portfolio_size", 1) == 1:
        ltv -= 0.05
        reasons.append("Single fund concentration risk -5%")
    
    # 1. High NAV volatility proxy: if XIRR is very high (>25%), fund is volatile
    xirr = fund.get("xirr", 0)
    if xirr > 25:
        ltv -= 0.05
        reasons.append(f"High return volatility (XIRR {xirr}%) -5%")

    # 2. Small holding value → less liquidity in pledge
    value = fund.get("current_value", 0)
    if value < 10000:
        ltv -= 0.05
        reasons.append("Small holding (<₹10,000) -5%")

    # 3. Sectoral funds get extra haircut
    if fund.get("category") == "sectoral":
        ltv -= 0.05
        reasons.append("Sectoral fund extra haircut -5%")

    # 4. Floor: never go below 0 or above base
    ltv = max(0.0, min(ltv, base_ltv))

    if not reasons:
        reasons.append(f"Base LTV for {fund.get('category', 'unknown')} fund")

    return ltv, reasons


def _margin_call_drop(nav: float, units: float, loan_amount: float, ltv: float) -> float:
    if nav <= 0 or units <= 0 or loan_amount <= 0 or ltv <= 0:
        return 0.0

    current_value = nav * units
    trigger_value = loan_amount / ltv   # correct formula

    if trigger_value >= current_value:
        return 0.0

    drop = (current_value - trigger_value) / current_value * 100
    return round(drop, 2)

def _portfolio_margin_drop(pledgeable_funds: list) -> float:
    """Weighted average margin call drop across all pledged funds."""
    if not pledgeable_funds:
        return 0.0
    total_value = sum(f["current_value"] for f in pledgeable_funds)
    if total_value == 0:
        return 0.0
    weighted = sum(
        f["current_value"] * (f.get("margin_call_drop_pct") or 0)
        for f in pledgeable_funds
    )
    return round(weighted / total_value, 2)

def fetch_latest_nav(scheme_code: str):
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        response = urllib.request.urlopen(url, timeout=5)
        data = json.loads(response.read())

        latest = data["data"][0]
        return float(latest["nav"])

    except Exception as e:
        print(f"NAV fetch failed for {scheme_code}: {e}")
        return None