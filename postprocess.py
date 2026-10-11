import re
from datetime import datetime

NULL_STRINGS = {"", "null", "none", "n/a", "na", "not visible", "-", "--"}

CHARGE_TYPES = {"energy", "fixed", "fpa", "quarterly_adjustment",
                "surcharge", "meter_rent", "subsidy", "other"}
TAX_TYPES = {"gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"}

DATE_FORMATS = ["%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
                "%d %B %Y", "%d %B %y", "%d/%m/%Y", "%d/%m/%y",
                "%d-%m-%Y", "%d-%m-%y"]
MONTH_FORMATS = ["%Y-%m", "%b-%y", "%b %Y", "%b %y", "%B %Y", "%b-%Y",
                 "%B-%Y", "%m/%Y"]


def _tidy(x):
    """3.0 -> 3, keep real decimals as they are."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def to_number(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return _tidy(v)
    s = str(v).strip()
    if s.lower() in NULL_STRINGS:
        return None
    credit = bool(re.search(r"CR\s*$", s, re.I)) or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"(?i)rs\.?|pkr", "", s)
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    if credit and n > 0:
        n = -n
    return _tidy(n)


def to_date(v):
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in NULL_STRINGS:
        return None
    s = re.sub(r"(?i)(\d)(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"[,\s]+", " ", s).strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def to_month(v):
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in NULL_STRINGS:
        return None
    s = re.sub(r"[,\s]+", " ", s).strip()
    for f in MONTH_FORMATS:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m")
        except ValueError:
            pass
    d = to_date(s)
    return d[:7] if d else None


def to_provider(v):
    s = str(v or "").upper().replace("-", "").replace(" ", "")
    if "IESCO" in s:
        return "IESCO"
    if "LESCO" in s:
        return "LESCO"
    if s in ("KE", "KESC", "KELECTRIC") or "KELECTRIC" in s:
        return "KE"
    return None


def to_text(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in NULL_STRINGS else s


def clean_lines(items, allowed, default):
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        amt = to_number(it.get("amount"))
        if amt is None or amt == 0:      # skip blank / zero lines
            continue
        t = str(it.get("type", "")).strip().lower()
        if t not in allowed:
            t = default
        if t == "subsidy" and amt > 0:   # subsidies are always deductions
            amt = -amt
        out.append({"type": t, "amount": amt})
    return out


def normalize_level1(d):
    d = d if isinstance(d, dict) else {}
    result = {
        "provider": to_provider(d.get("provider")),
        "tariff": to_text(d.get("tariff")),
        "sanctioned_load_kw": to_number(d.get("sanctioned_load_kw")),
        "bill_month": to_month(d.get("bill_month")),
        "reading_date": to_date(d.get("reading_date")),
        "issue_date": to_date(d.get("issue_date")),
        "due_date": to_date(d.get("due_date")),
        "previous_reading": to_number(d.get("previous_reading")),
        "current_reading": to_number(d.get("current_reading")),
        "units_consumed": to_number(d.get("units_consumed")),
        "charges": clean_lines(d.get("charges"), CHARGE_TYPES, "other"),
        "total_charges": to_number(d.get("total_charges")),
        "taxes": clean_lines(d.get("taxes"), TAX_TYPES, "other_tax"),
        "total_taxes": to_number(d.get("total_taxes")),
        "current_bill": to_number(d.get("current_bill")),
        "arrears": to_number(d.get("arrears")),
        "payable_within_due_date": to_number(d.get("payable_within_due_date")),
        "payable_after_due_date": to_number(d.get("payable_after_due_date")),
    }

    pw, cb, ar = (result["payable_within_due_date"], result["current_bill"],
                  result["arrears"])
    if pw is not None and cb is not None and ar is not None:
        net = cb + ar
        if net < -1 and pw > 0 and abs(pw + net) <= 2:
            result["payable_within_due_date"] = -pw

    # A credit balance means nothing is payable after the due date either.
    pw, pa = result["payable_within_due_date"], result["payable_after_due_date"]
    if pw is not None and pw < 0 and pa is not None and pa > 0:
        result["payable_after_due_date"] = None

    return result