import sys
import json
import re
import time
from extract import call_model
from postprocess import normalize_level1

PROMPT = """You are extracting data from a Pakistani electricity bill image (K-Electric, LESCO or IESCO).
Names, addresses and ID numbers are covered by grey boxes. The bill may be tilted or partly in Urdu.

Return ONLY one JSON object (no markdown, no explanation) with exactly these fields:

{
  "provider": "KE | LESCO | IESCO",
  "tariff": "string",
  "sanctioned_load_kw": number,
  "bill_month": "YYYY-MM",
  "reading_date": "YYYY-MM-DD",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "previous_reading": number,
  "current_reading": number,
  "units_consumed": number,
  "charges": [{"type": "energy|fixed|fpa|quarterly_adjustment|surcharge|meter_rent|subsidy|other", "amount": number}],
  "total_charges": number,
  "taxes": [{"type": "gst|electricity_duty|income_tax|municipal_tax|other_tax", "amount": number}],
  "total_taxes": number,
  "current_bill": number,
  "arrears": number,
  "payable_within_due_date": number,
  "payable_after_due_date": number
}

RULES:
- Copy values exactly as printed. Never recalculate, round or correct amounts.
- Amounts are plain numbers in PKR: remove "Rs." and commas. Use numbers, not strings.
- Any monetary amount printed with a "CR" suffix is negative: "54770CR" becomes -54770. Apply this to every monetary field, including charge and tax line items, total_charges, total_taxes, current_bill, arrears, payable_within_due_date, and payable_after_due_date. Do not drop the "CR" sign because of the field name. Subsidies are negative.
- Dates: YYYY-MM-DD. bill_month: YYYY-MM (MAR 2026 becomes 2026-03).
- Use null for anything not printed, blank, covered by a grey box or unreadable. Never guess. Use [] for an empty list.
- NEVER output names, addresses, CNIC, account, reference, consumer or meter numbers.
- Ignore handwritten notes, pen marks and stamps. Use printed values only.

FIELD GUIDE:
- provider: KE for K-Electric (the file name says KESC but you return KE), LESCO, or IESCO.
- tariff: copy the tariff code character by character exactly as printed, including any trailing letters, brackets or suffixes (for example A-1b(03)T, not A-1b(03)). Never shorten or tidy it.
- sanctioned_load_kw: labelled Sanc Load, S.Load or San Load.
- due_date: the last date to pay without a late payment surcharge.
- previous_reading / current_reading: the printed meter readings. If several register rows are printed (peak/off-peak, etc.), use the FIRST row.
- units_consumed: units billed for the current month, as printed.
- For K-Electric, units_consumed is the figure printed in the "Current Month ... units" box (for example 901), even if several meter registers are listed.
- charges: one entry per line in the electricity charges section (energy, fixed, FPA/FCA, quarterly adjustment, surcharges, meter rent, subsidy). Skip blank lines and lines printed as 0. Keep separate entries if the same type appears more than once. Do NOT include taxes here. If the bill only prints a single total for electricity charges with no breakdown, return [] and put that amount in total_charges.
  Type mapping: "Variable Upto ... Units" / Cost of Electricity / Energy Charges = energy; Fixed Charges = fixed; FPA or FCA = fpa; QTA or Uniform Quarterly Adjustment = quarterly_adjustment; Additional Surcharge (PHL) or F.C Surcharge = surcharge; Meter/Service Rent = meter_rent; government subsidy or relief = subsidy (negative); anything else = other.
- total_charges: the printed subtotal of the charges section (for example "Electricity Charges" or "Total Electricity Charges"). It is NOT the current bill. null if not printed.
- taxes: one entry per line in the taxes/government section. Classify by section, not by name. Sales tax or GST (including GST on FPA) = gst; Electricity Duty / ED = electricity_duty; income tax = income_tax; MUCT (KMC) or municipal/local charges under taxes = municipal_tax; anything else (extra tax, further tax, TV fee) = other_tax. If only one combined tax amount is printed, return [] and put it in total_taxes.
- total_taxes: the printed taxes subtotal (for example "Taxes and Duties"). null if not printed.
- taxes: list EVERY line printed in the taxes section (Electricity Duty, Sales Tax/GST, MUCT and so on). The lines must add up to the taxes subtotal; if they do not, you missed a line.
- current_bill: the printed amount for this month's bill (for example "Electricity Charges for current month" or "Current Bill").
- arrears: previous dues carried forward. Keep the printed sign. It may be printed with extra marks such as "39411 / 2": return 39411. Return null only if the field is truly blank.
- payable_within_due_date: amount payable by the due date.
- payable_after_due_date: amount payable after the due date. If several late-payment amounts are shown, use the HIGHEST. If the bill says NOT TO BE PAID, or the amount due is a credit (CR), return null.

BREAKDOWN-TABLE BILLS (IESCO and LESCO "Bill Charges Breakdown"):
These bills print a compact summary table instead of itemized charge lines. The table has rows such as Total Electricity Charges, Subsidies, Net Electricity Charges, Taxes, Current Bill, Arrears, Installment, Adjustments, W.E Credit, Lock Open Credit, Total FPA, Grand Total.
When you see this format, apply these mappings INSTEAD of the general charges/taxes rules above:
- "Total Electricity Charges" → ONE charges entry: {"type": "energy", "amount": <value>}.
- "Subsidies" → ONE charges entry: {"type": "subsidy", "amount": -<value>}. SKIP if the value is blank, empty, or 0.
- "Total FPA" (or just "FPA") → ONE charges entry: {"type": "fpa", "amount": <value>}. SKIP if the value is blank, empty, or 0. Note: this row may appear lower in the table (not adjacent to the other charges rows).
- "Net Electricity Charges" → total_charges (this is the subtotal after subsidies).
- "Taxes" → this is a single combined tax amount. Set taxes = [] (empty list) and total_taxes = that amount. Do NOT invent individual tax line items (no gst, electricity_duty, etc.) — the bill does not break them out.
- "Current Bill" → current_bill.
- "Arrears" → arrears. If printed as 0, keep 0. If the cell is blank or empty, use null.
Do NOT create charges entries for Net Electricity Charges, Taxes, Current Bill, Arrears, Installment, Adjustments, W.E Credit, Lock Open Credit, or Grand Total — these are NOT charges.
"""


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model reply")
    return json.loads(text[start:end + 1])


def extract_level1(image_path):
    raw = call_model(image_path, PROMPT, json_mode=True)
    try:
        return normalize_level1(parse_json(raw))
    except Exception:
        print("RAW MODEL REPLY:\n", raw, file=sys.stderr)
        raise


def consistency_problems(l1):
    """Cheap arithmetic checks that catch dropped lines and missing fields."""
    p = []
    t, tt = l1.get("taxes") or [], l1.get("total_taxes")
    if t and tt is not None and abs(sum(x["amount"] for x in t) - tt) > 1:
        p.append("tax lines do not add up to total_taxes")
    c, tc = l1.get("charges") or [], l1.get("total_charges")
    if l1.get("provider") == "KE" and c and tc is not None \
            and abs(sum(x["amount"] for x in c) - tc) > 1:
        p.append("charge lines do not add up to total_charges")
    cb, ar, pw = l1.get("current_bill"), l1.get("arrears"), l1.get("payable_within_due_date")
    if ar is None and cb is not None and pw is not None and abs(pw - cb) > 1:
        p.append("arrears missing but payable differs from current bill")
    return p


def extract_level1_safe(image_path, retries=3):
    """Never crashes. Retries on errors AND on failed arithmetic checks; keeps the best result."""
    best, best_n, last_err = None, None, None
    for attempt in range(1, retries + 1):
        try:
            l1 = extract_level1(image_path)
            problems = consistency_problems(l1)
            if best is None or len(problems) < best_n:
                best, best_n = l1, len(problems)
            if not problems:
                return l1
            print(f"[warn] {image_path} attempt {attempt}/{retries}: {'; '.join(problems)}",
                  file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"[warn] {image_path} attempt {attempt}/{retries} failed: {e}",
                  file=sys.stderr)
        if attempt < retries:
            time.sleep(2 ** attempt)
    if best is not None:
        return best
    print(f"[error] giving up on {image_path}: {last_err}", file=sys.stderr)
    return normalize_level1(None)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python level1.py path/to/bill.png [output.json]")
    try:
        result = json.dumps(extract_level1_safe(sys.argv[1]), indent=2)
        if len(sys.argv) == 3:
            with open(sys.argv[2], "w", encoding="utf-8") as f:
                f.write(result)
            print(f"Saved to {sys.argv[2]}")
        else:
            print(result)
    except Exception as e:
        sys.exit(f"Error: {e}")