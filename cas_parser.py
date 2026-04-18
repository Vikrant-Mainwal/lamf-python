import pdfplumber
import re
import io


def parse_cas_pdf(file_bytes: bytes) -> dict:
    try:
        # Open PDF from bytes (like Buffer in Node)
        pdf_file = io.BytesIO(file_bytes)

        raw_text = extract_text(pdf_file)

        if not raw_text:
            return {"status": "error", "message": "Could not extract text from PDF"}

        # Extract each section
        investor = extract_investor_info(raw_text)
        funds = extract_funds(raw_text)
        summary = calculate_summary(funds)

        return {
            "status": "success",
            "investor": investor,
            "funds": funds,
            "summary": summary,
            "raw_text_preview": raw_text[:500],  # useful for debugging
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def extract_text(pdf_file) -> str:
    """Extract all text from PDF pages"""
    full_text = ""

    with pdfplumber.open(pdf_file) as pdf:
        print(f"Total pages: {len(pdf.pages)}")

        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                full_text += f"\n--- PAGE {i+1} ---\n"
                full_text += page_text

    return full_text


def extract_investor_info(text: str) -> dict:
    """Extract investor name and PAN from CAS"""

    investor = {"name": None, "pan": None, "email": None, "mobile": None}

    # PAN pattern: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
    pan_match = re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text)
    if pan_match:
        investor["pan"] = pan_match.group()

    # Email pattern
    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text
    )
    if email_match:
        investor["email"] = email_match.group()

    # Mobile: 10 digit number starting with 6-9
    mobile_match = re.search(r"\b[6-9][0-9]{9}\b", text)
    if mobile_match:
        investor["mobile"] = mobile_match.group()

    # Name: usually appears after "Name:" or "Investor:" in CAS
    name_match = re.search(r"Name\s*:\s*([A-Z\s]+?)\s+PAN\s*:", text)
    if name_match:
        investor["name"] = name_match.group(1).strip()

    return investor


def extract_funds(text: str) -> list:
    """
    Extract all mutual fund holdings.
    CAS format typically looks like:

    Folio No: 1234567890 / 0
    HDFC Flexi Cap Fund - Growth
    ...
    Units: 1,245.678    NAV: 58.42    Value: 72,800.45
    """

    funds = []

    # Split text into sections by "Folio No"
    # Each folio section contains one AMC's funds
    folio_sections = re.split(r"Folio No\s*:\s*", text, flags=re.IGNORECASE)

    for section in folio_sections[1:]:  # skip first empty split
        folio_data = extract_folio_data(section)
        if folio_data:
            funds.extend(folio_data)

    return funds


def extract_folio_data(section: str) -> list:
    """Extract fund details from a single folio section"""

    funds = []

    # Extract folio number (first line of section)
    folio_match = re.match(r"([0-9/\s]+)", section)
    folio_number = folio_match.group(1).strip() if folio_match else "Unknown"

    # Extract AMC name
    amc_match = re.search(r'AMC\s*:\s*([^\n]+)', section)
    amc_name = amc_match.group(1).strip() if amc_match else "Unknown AMC"

    # Find all scheme entries in this folio
    scheme_pattern = re.finditer(
        r"([A-Za-z0-9\s\-\&]+(?:Fund|Plan|Option)[^\n]*)\n"
        r".*?Units\s+([\d,\.]+)"
        r".*?NAV\s*\(INR\)\s*([\d,\.]+)"
        r".*?Current Value\s*\(INR\)\s*([\d,\.]+)",
        section,
        re.DOTALL | re.IGNORECASE,
    )

    for match in scheme_pattern:
        raw_scheme = match.group(1).strip()

        scheme_name = raw_scheme.split("\n")[-1].strip()

        # remove extra spaces
        scheme_name = re.sub(r'\s+', ' ', scheme_name)

        units = clean_number(match.group(2))
        nav = clean_number(match.group(3))
        value = clean_number(match.group(4))

        fund = {
            "folio_number": folio_number,
            "amc": amc_name.strip(),  # ensure clean AMC
            "scheme": scheme_name,
            "units": units,
            "nav": nav,
            "current_value": value,
            "category": classify_fund(scheme_name),
            "is_pledgeable": is_pledgeable(scheme_name),
        }

        funds.append(fund)

    return funds


def classify_fund(scheme_name: str) -> str:
    name = scheme_name.lower()

    if any(word in name for word in ["liquid", "overnight", "money market"]):
        return "liquid"

    elif any(word in name for word in ["elss", "tax saver", "tax saving", "long term equity"]):
        return "elss"

    elif any(word in name for word in ["large & mid", "large and mid"]):
        return "large_mid_cap"  

    elif any(word in name for word in ["large cap", "bluechip", "top 100", "top 200"]):
        return "large_cap"

    elif any(word in name for word in ["mid cap", "small cap"]):
        return "mid_small_cap"

    elif any(word in name for word in ["hybrid", "balanced", "aggressive", "dynamic asset"]):
        return "hybrid"

    elif any(word in name for word in ["debt", "bond", "gilt", "income"]):
        return "debt"

    else:
        return "flexi_cap"

def is_pledgeable(scheme_name: str) -> bool:
    """ELSS funds have 3-year lock-in — cannot be pledged"""
    name = scheme_name.lower()
    locked_keywords = ["elss", "tax saver", "tax saving", "long term equity"]
    return not any(word in name for word in locked_keywords)


def clean_number(value: str) -> float:
    """Convert '1,245.678' → 1245.678"""
    try:
        return float(value.replace(",", "").strip())
    except:
        return 0.0


def calculate_summary(funds: list) -> dict:
    """Calculate portfolio totals"""

    pledgeable_funds = [f for f in funds if f["is_pledgeable"]]

    total_value = sum(f["current_value"] for f in funds)
    pledgeable_value = sum(f["current_value"] for f in pledgeable_funds)

    return {
        "total_funds": len(funds),
        "pledgeable_funds": len(pledgeable_funds),
        "total_portfolio_value": round(total_value, 2),
        "pledgeable_portfolio_value": round(pledgeable_value, 2),
        "non_pledgeable_value": round(total_value - pledgeable_value, 2),
    }
