from stats import compute_stats

l1 = {"bill_month": "2026-04", "units_consumed": 151, "current_bill": 3430.24,
      "total_taxes": 569.62, "total_charges": 2860.62,
      "payable_within_due_date": 3430, "payable_after_due_date": 3716,
      "charges": [{"type": "fixed", "amount": 900}, {"type": "energy", "amount": 1054}],
      "taxes": []}
units = [141, 138, 197, 239, 203, 176, 173, 187, 124, 96, 88, 115, 151]
months = [f"2025-{m:02d}" for m in range(4, 13)] + ["2026-01", "2026-02", "2026-03", "2026-04"]
hist = {"usage_history": [{"month": m, "units": u} for m, u in zip(months, units)],
        "billing_history": [], "extras": {}}

s = compute_stats(l1, hist)
assert s["tax_share_percent_of_current_bill"] == 16.61
assert s["usage_previous_months"]["months_counted"] == 12
assert s["usage_previous_months"]["count_above"]["200"] == 2
assert s["usage_including_current"]["average_units"] == 156.0
assert s["usage_previous_months"]["highest"]["units"] == 239
assert s["vs_last_month"]["change_units"] == 36
assert s["late_payment"]["extra_if_paid_late"] == 286
hist_with_tiers = {
    **hist,
    "extras": {"late_payment_tiers": [
        {"label": "Due date", "amount": 3430},
        {"label": "Tier 1", "amount": 3500},
        {"label": "Tier 2", "amount": 3716},
    ]},
}
assert compute_stats(l1, hist_with_tiers)["late_payment_tiers_extra"] == [
    {"label": "Tier 1", "amount": 3500, "extra": 70},
    {"label": "Tier 2", "amount": 3716, "extra": 286},
]
assert compute_stats(None, None)["current_units"] is None   # never crashes

extra = compute_stats(l1, hist)["same_month_last_year"]
assert extra == {
    "month": "2025-04", "units_then": 141, "units_now": 151,
    "change_units": 10, "change_percent": 7.09,
}
assert compute_stats(l1, hist)["summer_vs_winter"]["summer_jun_aug"]["count"] == 3
assert compute_stats(l1, hist)["last_3_months"]["direction_first_to_last"] == "up"
assert compute_stats(l1, hist)["ESTIMATE_next_month_units"]["next_month"] == "2026-05"
assert compute_stats(l1, {"usage_history": [], "billing_history": [], "extras": {}}).get(
    "same_month_last_year") is None
print("stats tests passed")