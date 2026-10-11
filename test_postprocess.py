from postprocess import *

# numbers
assert to_number("54,770CR") == -54770
assert to_number("38209CR") == -38209
assert to_number("-54770CR") == -54770
assert to_number("Rs. 19,964") == 19964
assert to_number("151") == 151
assert to_number("-0.53") == -0.53
assert to_number("3,430.24") == 3430.24
assert to_number(3.0) == 3
assert to_number(None) is None
assert to_number("not visible") is None
assert to_number("") is None

# dates and months
assert to_date("22nd Apr 2026") == "2026-04-22"
assert to_date("21-Apr-2026") == "2026-04-21"
assert to_date("08 OCT 26") == "2026-10-08"
assert to_date("2026-04-03") == "2026-04-03"
assert to_date("garbage") is None
assert to_month("Apr-26") == "2026-04"
assert to_month("MAR 2026") == "2026-03"
assert to_month("SEP 26") == "2026-09"
assert to_month("2026-04") == "2026-04"

# provider
assert to_provider("K-Electric") == "KE"
assert to_provider("KESC") == "KE"
assert to_provider("Lahore Electric Supply Company LESCO") == "LESCO"
assert to_provider("IESCO") == "IESCO"

# messy full object: missing fields, bad types, zero lines, positive subsidy
r = normalize_level1({
    "provider": "KESC", "units_consumed": "151", "arrears": "0.53CR",
    "due_date": "22nd Apr 2026",
    "charges": [{"type": "Fixed", "amount": "900"},
                {"type": "weird", "amount": 5},
                {"type": "subsidy", "amount": 3332},
                {"type": "energy", "amount": 0}],
    "taxes": [{"type": "gst", "amount": "Rs. 520.21"}],
})
assert r["provider"] == "KE"
assert r["units_consumed"] == 151
assert r["arrears"] == -0.53
assert r["due_date"] == "2026-04-22"
assert r["bill_month"] is None            # missing -> null
assert len(r["charges"]) == 3             # zero line dropped
assert r["charges"][1] == {"type": "other", "amount": 5}
assert r["charges"][2] == {"type": "subsidy", "amount": -3332}
assert r["taxes"] == [{"type": "gst", "amount": 520.21}]
assert len(r) == 18                       # every field always present
assert normalize_level1(None)["charges"] == []

# CR applies to every monetary field, not only line items or arrears.
credits = normalize_level1({
    "charges": [{"type": "energy", "amount": "100CR"}],
    "total_charges": "100CR",
    "taxes": [{"type": "gst", "amount": "10CR"}],
    "total_taxes": "10CR",
    "current_bill": "90CR",
    "arrears": "5CR",
    "payable_within_due_date": "95CR",
    "payable_after_due_date": "105CR",
})
assert credits["charges"] == [{"type": "energy", "amount": -100}]
assert credits["total_charges"] == -100
assert credits["taxes"] == [{"type": "gst", "amount": -10}]
assert credits["total_taxes"] == -10
assert credits["current_bill"] == -90
assert credits["arrears"] == -5
assert credits["payable_within_due_date"] == -95
assert credits["payable_after_due_date"] == -105

r = normalize_level1({"current_bill": 20726, "arrears": -75496,
                      "payable_within_due_date": 54770})
assert r["payable_within_due_date"] == -54770

r = normalize_level1({"current_bill": 20726, "arrears": -75496,
                      "payable_within_due_date": 54770, "payable_after_due_date": 54770})
assert r["payable_within_due_date"] == -54770 and r["payable_after_due_date"] is None

print("All tests passed")