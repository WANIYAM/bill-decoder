import sys
import json
from extract import call_model
from level1 import extract_level1_safe, parse_json
from history import extract_history, normalize_history
from stats import compute_stats

FALLBACK = ("This could not be answered reliably from the bill. "
            "The required information is not clearly shown on the bill image.")

SAMPLE_QUESTIONS = [
    ("Q1", "Is this a net-metered (solar) connection or a standard connection? How did you tell?"),
    ("Q2", "Which month in the last 12 months had the highest units consumed?"),
    ("Q3", "How much fuel adjustment am I being charged (shown as FPA or FCA on the bill), and for which month?"),
    ("Q4", "If I don't pay on time, what late payment surcharges will be added?"),
    ("Q5", "Am I consuming more units than in the same month last year?"),
    ("Q6", "What are my average monthly units consumed, and how does this month compare?"),
    ("Q7", "How many more units do I consume in summer (June-August) than in winter (December-February)?"),
    ("Q8", "Looking at the payments for the 12 months shown on the bill, have I been paying every bill?"),
    ("Q9", "Have my units consumed gone up or down over the last 3 months?"),
    ("Q10", "Based on the 12 months trend, how many units should I expect to consume next month?"),
    ("Q11", "If I wanted to spread my electricity cost evenly across the year, how much should I set aside each month?"),
    ("Q12", "If I consume the same units as last month, what would my bill be roughly?"),
]

PROMPT = """You are a helpful assistant explaining a Pakistani electricity bill (K-Electric, LESCO or IESCO) to the customer in plain English.

You are given the bill image, plus FACTS extracted from it. The FACTS contain: level1 (extracted fields), history (usage and billing history, extras) and stats (numbers already calculated by code).

RULES:
- Answer ONLY from the bill and the FACTS. Never use outside tariff, rate or policy information. If the bill does not show something needed, say clearly that it is not shown on the bill. Do not guess.
- Use numbers from FACTS.stats and FACTS.level1 exactly as given. Do not recalculate them. If a question needs a figure that is not in the FACTS, work it out carefully from FACTS values and state how you did it.
- Be specific: include the actual amounts in PKR, the months, and the units. Use "PKR 1,234.56" formatting.
- When asked about a total (taxes, charges, or bill amount), also list its component lines with their amounts when they are available in FACTS.
- The current bill amount is the electricity charges subtotal plus the taxes subtotal, minus any subsidy shown. Arrears, previous dues, credits, and adjustments are carried forward separately and are NOT part of the current bill amount. Never describe them as adjusting the current bill.
- If FACTS.history.extras.late_payment_tiers contains several late-payment amounts, mention every tier and its amount.
- For late-payment questions, give the extra amount for EACH tier from FACTS.stats.late_payment_tiers_extra (and the due-date amount for comparison). For Opening Balance, treat it as an earlier balance already settled by the payment/adjustment line, not as money currently owed, unless FACTS clearly show otherwise.
- Never invent or infer a line amount. If listed lines do not add up to a total, quote only the printed total and the lines you have.
- If the amount payable is 0 or negative, say plainly that nothing is due because a credit, net-metering benefit or previous balance covers the bill, and give the figures.
- A negative payable amount is a credit in the customer's favour, not an amount owed.
- Net-metering question: say whether the bill looks net-metered or standard and WHY, citing concrete evidence from FACTS (history.extras.net_metering_evidence, register_rows, any net-metering benefit or credit lines). If there is no such evidence, say it appears to be a standard connection and state what you checked.
- Fuel adjustment question: give the amount (FACTS.history.extras.fpa_amount and the fpa lines in level1.charges) and the month from FACTS.history.extras.fpa_label. If the month is not shown, say so.
- Late payment question: give every printed surcharge amount and each tier's total from FACTS.history.extras.lp_surcharges, FACTS.history.extras.late_payment_tiers and FACTS.stats.late_payment_tiers_extra.
- Questions about the same month last year, seasons, the last 3 months, payments, next month, setting money aside, or a bill at last month's units: use the matching FACTS.stats keys (same_month_last_year, summer_vs_winter, last_3_months, payment_check, ESTIMATE_next_month_units, annual_cost_helpers, ESTIMATE_bill_if_same_units_as_last_month). Label every projection as an estimate and explain the method. For payments, only claim what the months listed on the bill show, and say how many months are listed.
- If a needed value is null or missing in FACTS, say it is not shown on the bill rather than guessing.
- Anything that is an estimate or projection must be labelled "estimate" and you must explain how it was calculated.
- If a question has more than one reasonable meaning (for example including or excluding the current month, or before or after subsidy), state the meaning you used or answer both.
- Credits shown as negative numbers mean the customer is owed money or has a balance in their favour. Explain this plainly for net-metering bills.
- Never mention names, addresses, CNIC, account, reference, consumer or meter numbers.
- Write every answer in English, 2 to 5 sentences. Be direct and do not repeat the question.

Return ONLY a JSON object (no markdown) mapping each question id to its answer string, for example {"Q1": "answer", "Q2": "answer"}. Include EVERY question id.

FACTS:
%s

QUESTIONS:
%s
"""


def build_facts(l1, hist, stats):
    return json.dumps({"level1": l1, "history": hist, "stats": stats},
                      ensure_ascii=False, indent=1)


def pick_answers(data):
    """Accepts several reply shapes and returns {qid: answer_text}."""
    if isinstance(data, dict) and len(data) == 1:
        only = next(iter(data.values()))
        if isinstance(only, (dict, list)):
            data = only                      # unwrap {"answers": {...}}
    out = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                qid = item.get("id") or item.get("question_id") or item.get("qid")
                ans = item.get("answer")
                if qid and isinstance(ans, str):
                    out[str(qid).strip()] = ans
    elif isinstance(data, dict):
        for k, v in data.items():
            qid = str(k).split(":")[0].strip()       # handles "Q1: How much..."
            if isinstance(v, str):
                out[qid] = v
            elif isinstance(v, dict) and isinstance(v.get("answer"), str):
                out[qid] = v["answer"]
    return out


def answer_questions(image_path, l1, hist, stats, questions, retries=3):
    """questions: list of (question_id, question_text). Returns {qid: answer}. Never empty."""
    import time
    qtext = "\n".join(f"{qid}: {q}" for qid, q in questions)
    prompt = PROMPT % (build_facts(l1, hist, stats), qtext)
    answers = {}
    for attempt in range(1, retries + 1):
        raw = ""
        try:
            raw = call_model(image_path, prompt, json_mode=True)
            found = pick_answers(parse_json(raw))
            for qid, _ in questions:
                a = found.get(qid)
                if isinstance(a, str) and a.strip():
                    answers[qid] = a.strip()
            if len(answers) == len(questions):
                break
            print(f"[warn] level2 attempt {attempt}/{retries}: only "
                  f"{len(answers)}/{len(questions)} answers parsed", file=sys.stderr)
        except Exception as e:
            print(f"[warn] level2 {image_path} attempt {attempt}/{retries}: {e}",
                  file=sys.stderr)
        if raw:
            print(f"[debug] reply start: {raw[:200]!r}\n[debug] reply end: {raw[-200:]!r}",
                  file=sys.stderr)
        if attempt < retries:
            time.sleep(2 ** attempt)
    for qid, _ in questions:          # guarantee no empty cell
        answers.setdefault(qid, FALLBACK)
    return answers


def process_bill(image_path, questions):
    l1 = extract_level1_safe(image_path)
    try:
        hist = extract_history(image_path)
    except Exception as e:
        print(f"[warn] history failed for {image_path}: {e}", file=sys.stderr)
        hist = normalize_history(None)
    try:
        stats = compute_stats(l1, hist)
    except Exception as e:
        print(f"[warn] stats failed for {image_path}: {e}", file=sys.stderr)
        stats = {}
    return l1, hist, answer_questions(image_path, l1, hist, stats, questions)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python level2.py path/to/bill.png")
    _, _, answers = process_bill(sys.argv[1], SAMPLE_QUESTIONS)
    for qid, q in SAMPLE_QUESTIONS:
        print(f"\n{qid}: {q}\n-> {answers[qid]}")