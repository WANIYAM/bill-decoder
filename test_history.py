from history import normalize_history


history = normalize_history({
    "usage_history": [{"month": "2026-04", "units": "0"}],
    "billing_history": [
        {"month": "2026-04", "billed_amount": "100", "payment": "0"},
        {"month": "2026-03", "billed_amount": "90", "payment": ""},
    ],
    "extras": {
        "fpa_label": "FCA :Jul-26",
        "fpa_amount": "336.50",
        "lp_surcharges": [
            {"label": "L.P Surcharge", "amount": "336"},
            {"label": "Late Payment Surcharge (10%)", "amount": "635.92"},
            {"label": "invalid", "amount": "not visible"},
        ],
        "net_metering_evidence": [
            "NET METERING CONNECTION", "Import/export registers", "Negative bill",
            "This fourth note should be omitted",
        ],
    },
})
extras = history["extras"]
assert extras["fpa_label"] == "FCA :Jul-26"
assert extras["fpa_amount"] == 336.5
assert extras["lp_surcharges"] == [
    {"label": "L.P Surcharge", "amount": 336},
    {"label": "Late Payment Surcharge (10%)", "amount": 635.92},
]
assert extras["net_metering_evidence"] == [
    "NET METERING CONNECTION", "Import/export registers", "Negative bill",
]
assert history["billing_history"] == [
    {"month": "2026-03", "billed_amount": 90, "payment": None, "pay_date": None},
    {"month": "2026-04", "billed_amount": 100, "payment": 0, "pay_date": None},
]
assert len(extras) == 11
print("history tests passed")
