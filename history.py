import sys
import json
from extract import call_model
from level1 import parse_json
from postprocess import to_number, to_month, to_date, to_text

PROMPT = """You are reading a Pakistani electricity bill image (K-Electric, LESCO or IESCO).
Names, addresses and ID numbers are covered by grey boxes. Never output personal identifiers.

Return ONLY one JSON object (no markdown) with exactly these fields:

{
  "usage_history": [{"month": "YYYY-MM", "units": number}],
  "billing_history": [{"month": "YYYY-MM", "billed_amount": number, "payment": number, "pay_date": "YYYY-MM-DD"}],
  "extras": {
    "net_metering_benefit": number,
    "outstanding_balance": number,
    "late_payment_tiers": [{"label": "string", "amount": number}],
    "energy_percent": number,
    "tax_percent": number,
    "register_rows": [{"label": "string", "previous": number, "current": number, "units": number}],
    "notes": ["string"],
    "fpa_label": "string",
    "fpa_amount": number,
    "lp_surcharges": [{"label": "string", "amount": number}],
    "net_metering_evidence": ["string"]
  }
}

RULES:
- Copy values exactly as printed. Never calculate or guess. Use null for anything unreadable or not printed, [] for empty lists.
- Credits ("CR" suffix or a minus sign) are negative numbers. Numbers have no commas or currency labels.
- usage_history: the monthly usage history (K-Electric "13 Month Usage History" bar chart, or the "Bill History" table units column on LESCO/IESCO). One entry per month, with the printed units. K-Electric bars are labelled with the year above the first and last groups; the LAST bar is the current bill month and months run oldest to newest.
- billing_history: the billing/payment history table (K-Electric "Billing & Payment History", or the "Bill History" bill and payment columns). Skip rows that are blank.
- net_metering_benefit: K-Electric "Net Metering Benefit" amount if printed, else null.
- outstanding_balance: ONLY if a line literally labelled "Outstanding Balance" or "Outstanding Amount" is printed. Do NOT use Opening Balance, Remaining Dues, Previous Dues or Arrears for it. Otherwise null.
- late_payment_tiers: every late-payment amount or surcharge tier printed (for example "Till 22-Apr - 24-Apr": 3574, "After 24-Apr": 3716). Include the label as printed.
- energy_percent / tax_percent: the printed energy vs taxes percentage split (K-Electric shows e.g. 83.39% and 16.61%), else null.
- register_rows: if the meter has several register rows (peak, off-peak, import, export), one entry per row with label, previous reading, current reading and units. Otherwise [].
- notes: up to 3 short English notes of anything printed that explains the bill (for example "NOT TO BE PAID", message board text), or [].
- fpa_label: the printed label of the fuel adjustment line that names its month, exactly as printed (for example "FCA :Jul-26" or "FPA FEB-26 @ 1.4235"). If the month appears only in an Urdu message, state it in English (for example "FPA for July 2026 units, from the message board"). Otherwise null.
- fpa_amount: the printed FPA/FCA amount ("FCA" line on K-Electric, "Total FPA" on LESCO/IESCO). Otherwise null.
- lp_surcharges: every late-payment surcharge amount printed, with its label (for example "L.P Surcharge" 336 and 671, or "Late Payment Surcharge (5%)" 317.96 and "(10%)" 635.92).
- net_metering_evidence: up to 3 short English notes of anything printed that indicates net metering or solar (text such as "NET METERING CONNECTION", import/export registers, a Net Metering Benefit line, negative bills). Use [] if there is nothing.
- LESCO and IESCO "Bill History" is a table of two blocks side by side (older months on the left, newer on the right), and one older LESCO layout lists months vertically. Read ALL rows into usage_history and billing_history. In billing_history, payment is 0 if a 0 is printed and null if blank.
- Ignore handwritten notes, stamps and pen annotations. Use printed values only.
"""


def normalize_history(d):
    d = d if isinstance(d, dict) else {}
    usage = []
    for r in d.get("usage_history") or []:
        if not isinstance(r, dict):
            continue
        m, u = to_month(r.get("month")), to_number(r.get("units"))
        if m and u is not None:
            usage.append({"month": m, "units": u})
    usage.sort(key=lambda r: r["month"])

    billing = []
    for r in d.get("billing_history") or []:
        if not isinstance(r, dict):
            continue
        m = to_month(r.get("month"))
        if not m:
            continue
        billing.append({
            "month": m,
            "billed_amount": to_number(r.get("billed_amount")),
            "payment": to_number(r.get("payment")),
            "pay_date": to_date(r.get("pay_date")),
        })
    billing.sort(key=lambda r: r["month"])

    e = d.get("extras") if isinstance(d.get("extras"), dict) else {}
    tiers = []
    for t in e.get("late_payment_tiers") or []:
        if isinstance(t, dict) and to_number(t.get("amount")) is not None:
            tiers.append({"label": to_text(t.get("label")),
                          "amount": to_number(t.get("amount"))})
    regs = []
    for r in e.get("register_rows") or []:
        if isinstance(r, dict):
            regs.append({"label": to_text(r.get("label")),
                         "previous": to_number(r.get("previous")),
                         "current": to_number(r.get("current")),
                         "units": to_number(r.get("units"))})
    notes = [str(n).strip() for n in (e.get("notes") or []) if str(n).strip()][:3]
    lps = []
    for t in e.get("lp_surcharges") or []:
        if isinstance(t, dict) and to_number(t.get("amount")) is not None:
            lps.append({"label": to_text(t.get("label")), "amount": to_number(t.get("amount"))})
    nm = [str(n).strip() for n in (e.get("net_metering_evidence") or []) if str(n).strip()][:3]

    return {
        "usage_history": usage,
        "billing_history": billing,
        "extras": {
            "net_metering_benefit": to_number(e.get("net_metering_benefit")),
            "outstanding_balance": to_number(e.get("outstanding_balance")),
            "late_payment_tiers": tiers,
            "energy_percent": to_number(e.get("energy_percent")),
            "tax_percent": to_number(e.get("tax_percent")),
            "register_rows": regs,
            "notes": notes,
            "fpa_label": to_text(e.get("fpa_label")),
            "fpa_amount": to_number(e.get("fpa_amount")),
            "lp_surcharges": lps,
            "net_metering_evidence": nm,
        },
    }


def extract_history(image_path):
    raw = call_model(image_path, PROMPT, json_mode=True)
    try:
        return normalize_history(parse_json(raw))
    except Exception:
        print("RAW MODEL REPLY:\n", raw, file=sys.stderr)
        raise


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python history.py path/to/bill.png [output.json]")
    try:
        result = json.dumps(extract_history(sys.argv[1]), indent=2)
        if len(sys.argv) == 3:
            with open(sys.argv[2], "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Saved to {sys.argv[2]}")
        else:
            print(result)
    except Exception as e:
        sys.exit(f"Error: {e}")