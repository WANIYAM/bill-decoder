import sys
import json
from collections import defaultdict


def r2(x):
    return None if x is None else round(x, 2)


def pct(part, whole):
    if part is None or not whole:
        return None
    return round(part / whole * 100, 2)


def months_above(usage, threshold):
    """Months whose units are strictly above the threshold."""
    return [u for u in usage if u["units"] > threshold]


def usage_stats(usage):
    if not usage:
        return None
    units = [u["units"] for u in usage]
    hi = max(usage, key=lambda u: u["units"])
    lo = min(usage, key=lambda u: u["units"])
    return {
        "months_counted": len(usage),
        "first_month": usage[0]["month"],
        "last_month": usage[-1]["month"],
        "total_units": r2(sum(units)),
        "average_units": r2(sum(units) / len(units)),
        "highest": hi,
        "lowest": lo,
        "count_above": {str(t): len(months_above(usage, t)) for t in (100, 150, 200, 250, 300, 500)},
        "months_above_200": [f'{u["month"]} ({u["units"]})' for u in months_above(usage, 200)],
    }


def _add_months(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _avg(xs):
    return round(sum(xs) / len(xs), 2) if xs else None


def _trend_next(points):
    n = len(points)
    if n < 4:
        return None
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(points) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, points)) / den
    return round(my + slope * (n - mx), 2), round(slope, 2)


def extra_stats(l1, hist, cpu):
    """Helpers for same-month-last-year, seasons, payments, trends and estimates."""
    bm = l1.get("bill_month")
    usage = hist.get("usage_history") or []
    if not bm or not usage:
        return {}
    cur = l1.get("units_consumed")
    by = {u["month"]: u["units"] for u in usage}
    prev = [u for u in usage if u["month"] < bm][-12:]
    out = {}

    key = _add_months(bm, -12)
    if cur is not None and key in by:
        d = cur - by[key]
        out["same_month_last_year"] = {"month": key, "units_then": by[key], "units_now": cur,
                                       "change_units": r2(d), "change_percent": pct(d, by[key])}
    else:
        out["same_month_last_year"] = None

    def season(months):
        rows = [u for u in prev if int(u["month"][5:7]) in months]
        return {"months": [f'{u["month"]} ({u["units"]})' for u in rows], "count": len(rows),
                "total": r2(sum(u["units"] for u in rows)), "average": _avg([u["units"] for u in rows])}
    s, w = season({6, 7, 8}), season({12, 1, 2})
    out["summer_vs_winter"] = {
        "summer_jun_aug": s, "winter_dec_feb": w,
        "average_difference_per_month": r2(s["average"] - w["average"])
        if s["average"] is not None and w["average"] is not None else None,
        "total_difference": r2(s["total"] - w["total"]) if s["count"] and w["count"] else None,
        "note": "computed over the previous 12 months shown on the bill; totals are comparable only if both seasons have the same number of months",
    }

    last3 = prev[-3:]
    if len(last3) == 3:
        a, b = last3[0]["units"], last3[-1]["units"]
        out["last_3_months"] = {
            "previous_three": last3,
            "direction_first_to_last": "up" if b > a else "down" if b < a else "flat",
            "change_units": r2(b - a),
            "current_month_units": cur,
            "current_vs_last_of_three": r2(cur - b) if cur is not None else None,
        }

    bh = hist.get("billing_history") or []
    rows = [b for b in bh if b.get("billed_amount") is not None]
    unpaid = [{"month": b["month"], "billed": b["billed_amount"], "paid": b.get("payment") or 0}
              for b in rows if b["billed_amount"] > 0 and (b.get("payment") or 0) < b["billed_amount"] - 2]
    out["payment_check"] = {
        "months_listed": len(rows), "months_not_fully_paid": unpaid,
        "all_listed_paid": bool(rows) and not unpaid,
        "note": "K-Electric bills list only 3 months of payments; LESCO/IESCO list up to 12",
    }

    pts = [u["units"] for u in prev] + ([cur] if cur is not None else [])
    est = {"next_month": _add_months(bm, 1),
           "same_month_last_year_units": by.get(_add_months(bm, -11)),
           "average_last_3_months": _avg(pts[-3:]),
           "average_last_12_months": _avg(pts[-12:])}
    t = _trend_next(pts[-13:])
    if t:
        est["linear_trend_projection"], est["trend_slope_units_per_month"] = t
    out["ESTIMATE_next_month_units"] = est

    if prev:
        lm = prev[-1]
        actual = next((b["billed_amount"] for b in rows if b["month"] == lm["month"]), None)
        out["ESTIMATE_bill_if_same_units_as_last_month"] = {
            "last_month": lm["month"], "last_month_units": lm["units"],
            "last_month_actual_bill": actual,
            "estimated_amount": r2(lm["units"] * cpu) if cpu else None,
            "method": "last month's units x this bill's average cost per unit (current bill / units); ignores slab changes",
        }

    billed = [b["billed_amount"] for b in rows]
    ann = {"bills_listed": len(billed), "sum_of_listed_bills": r2(sum(billed)) if billed else None}
    if len(billed) >= 12:
        ann["monthly_set_aside_from_12_bills"] = r2(sum(billed[-12:]) / 12)
    elif billed:
        ann["ESTIMATE_monthly_from_listed_bills_average"] = _avg(billed)
    if cpu and len(prev) >= 12:
        ann["ESTIMATE_monthly_from_12_months_units_x_current_rate"] = r2(
            sum(u["units"] for u in prev[-12:]) * cpu / 12)
    out["annual_cost_helpers"] = ann
    return out


def compute_stats(l1, hist):
    l1 = l1 or {}
    hist = hist or {}
    usage = hist.get("usage_history") or []
    bm = l1.get("bill_month")

    # If the history's last month is the current bill month, split it off.
    if usage and usage[-1]["month"] == bm:
        previous, current_hist = usage[:-1], usage[-1]
    else:
        previous, current_hist = usage, None

    cur_units = l1.get("units_consumed")
    if cur_units is None and current_hist:
        cur_units = current_hist["units"]

    out = {
        "current_units": cur_units,
        "usage_previous_months": usage_stats(previous),
        "usage_including_current": usage_stats(usage),
    }

    # Current month vs history
    if cur_units is not None and previous:
        last = previous[-1]
        avg_prev = sum(u["units"] for u in previous) / len(previous)
        out["vs_last_month"] = {
            "last_month": last["month"],
            "last_month_units": last["units"],
            "change_units": r2(cur_units - last["units"]),
            "change_percent": pct(cur_units - last["units"], last["units"]),
        }
        out["vs_previous_average"] = {
            "previous_average": r2(avg_prev),
            "change_units": r2(cur_units - avg_prev),
            "change_percent": pct(cur_units - avg_prev, avg_prev),
        }

    # Money
    cb = l1.get("current_bill")
    tt = l1.get("total_taxes")
    tc = l1.get("total_charges")
    out["tax_share_percent_of_current_bill"] = pct(tt, cb)
    out["charges_share_percent_of_current_bill"] = pct(tc, cb)
    out["printed_energy_percent"] = (hist.get("extras") or {}).get("energy_percent")
    out["printed_tax_percent"] = (hist.get("extras") or {}).get("tax_percent")
    out["cost_per_unit_current_bill"] = r2(cb / cur_units) if cb is not None and cur_units else None
    out["cost_per_unit_charges_only"] = r2(tc / cur_units) if tc is not None and cur_units else None

    by_type = defaultdict(float)
    for c in l1.get("charges") or []:
        by_type[c["type"]] += c["amount"]
    out["charges_by_type"] = {k: r2(v) for k, v in by_type.items()}
    out["charges_lines_sum"] = r2(sum(by_type.values())) if by_type else None
    out["taxes_lines"] = l1.get("taxes") or []

    # Late payment
    within = l1.get("payable_within_due_date")
    after = l1.get("payable_after_due_date")
    if within is not None and after is not None and within > 0:
        out["late_payment"] = {
            "extra_if_paid_late": r2(after - within),
            "extra_percent": pct(after - within, within),
        }
    else:
        out["late_payment"] = None

    # Billing history
    bh = hist.get("billing_history") or []
    billed = [b["billed_amount"] for b in bh if b.get("billed_amount") is not None]
    paid = [b["payment"] for b in bh if b.get("payment") is not None]
    out["billing_history_average_billed"] = r2(sum(billed) / len(billed)) if billed else None
    out["billing_history_average_paid"] = r2(sum(paid) / len(paid)) if paid else None

    # Labelled estimate: next bill if usage equals the average of previous months
    if out["cost_per_unit_current_bill"] and previous:
        avg_prev = sum(u["units"] for u in previous) / len(previous)
        out["ESTIMATE_bill_at_average_usage"] = {
            "units": r2(avg_prev),
            "estimated_amount": r2(avg_prev * out["cost_per_unit_current_bill"]),
            "method": "average units of previous months x current bill / current units (flat average rate; ignores slab changes)",
        }

    # Extra cost per late-payment tier (tier amount minus amount payable by the due date)
    tiers = (hist.get("extras") or {}).get("late_payment_tiers") or []
    if within is not None and within > 0:
        out["late_payment_tiers_extra"] = [
            {"label": t["label"], "amount": t["amount"], "extra": r2(t["amount"] - within)}
            for t in tiers if t.get("amount") is not None and t["amount"] > within
        ]
    try:
        out.update(extra_stats(l1, hist, out.get("cost_per_unit_current_bill")))
    except Exception as e:
        print(f"[warn] extra stats failed: {e}", file=sys.stderr)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python stats.py level1.json history.json")
    l1 = json.load(open(sys.argv[1], encoding="utf-8"))
    hist = json.load(open(sys.argv[2], encoding="utf-8"))
    print(json.dumps(compute_stats(l1, hist), indent=2))