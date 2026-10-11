import os, re, sys, csv, json, zipfile, tempfile, argparse, py_compile

L1_KEYS = ["provider", "tariff", "sanctioned_load_kw", "bill_month", "reading_date", "issue_date",
           "due_date", "previous_reading", "current_reading", "units_consumed", "charges",
           "total_charges", "taxes", "total_taxes", "current_bill", "arrears",
           "payable_within_due_date", "payable_after_due_date"]
NUM = ["sanctioned_load_kw", "previous_reading", "current_reading", "units_consumed", "total_charges",
       "total_taxes", "current_bill", "arrears", "payable_within_due_date", "payable_after_due_date"]
CHG = {"energy", "fixed", "fpa", "quarterly_adjustment", "surcharge", "meter_rent", "subsidy", "other"}
TAX = {"gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax"}
MODELS = {"claude-haiku-4-5", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gpt-4.1-mini", "gpt-5-mini"}
KEY_PATTERNS = [r"AIza[0-9A-Za-z_\-]{30,}", r"sk-ant-[A-Za-z0-9_\-]{20,}", r"sk-[A-Za-z0-9_\-]{30,}"]
SKIP = {".venv", "cache", "train", "test", "__pycache__", "output", "fake_csv", "demo", "submission_stage", ".git"}
errors, warns = [], []


def err(m): errors.append(m)
def warn(m): warns.append(m)
def isnum(x): return isinstance(x, (int, float)) and not isinstance(x, bool)


def read(p):
    with open(p, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def check_csvs(template, out):
    for name, col in (("level1.csv", "json"), ("level2.csv", "answer")):
        tp, op = os.path.join(template, name), os.path.join(out, name)
        if not os.path.exists(op):
            err(f"{name} missing in {out}"); continue
        if open(op, "rb").read(3) == b"\xef\xbb\xbf":
            warn(f"{name} has a BOM")
        tf, trows = read(tp); of, orows = read(op)
        if tf != of: err(f"{name}: columns {of} != template {tf}")
        if len(trows) != len(orows):
            err(f"{name}: {len(orows)} rows, expected {len(trows)}"); continue
        for i, (t, o) in enumerate(zip(trows, orows), 2):
            for k in tf:
                if k != col and t[k] != o[k]:
                    err(f"{name} line {i}: column '{k}' was changed or reordered")
    # level 1
    p = os.path.join(out, "level1.csv")
    if os.path.exists(p):
        _, rows = read(p)
        for r in rows:
            b, cell = r["bill_id"], r["json"]
            try:
                d = json.loads(cell)
            except Exception as e:
                err(f"L1 {b}: invalid JSON ({e})"); continue
            if "\n" in cell: err(f"L1 {b}: JSON is not on one line")
            if set(d) != set(L1_KEYS): err(f"L1 {b}: keys differ: {set(d) ^ set(L1_KEYS)}")
            if d.get("provider") not in ("KE", "LESCO", "IESCO"): err(f"L1 {b}: bad provider {d.get('provider')}")
            for k in NUM:
                if d.get(k) is not None and not isnum(d[k]): err(f"L1 {b}: {k} is not a number: {d[k]!r}")
            for k in ("reading_date", "issue_date", "due_date"):
                if d.get(k) is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d[k])): err(f"L1 {b}: {k} bad format {d[k]}")
            if d.get("bill_month") is not None and not re.fullmatch(r"\d{4}-\d{2}", str(d["bill_month"])): err(f"L1 {b}: bill_month bad format")
            for key, allowed in (("charges", CHG), ("taxes", TAX)):
                if not isinstance(d.get(key), list): err(f"L1 {b}: {key} not a list"); continue
                for e in d[key]:
                    if e.get("type") not in allowed or not isnum(e.get("amount")): err(f"L1 {b}: bad {key} entry {e}")
                    if e.get("type") == "subsidy" and e.get("amount", 0) > 0: err(f"L1 {b}: subsidy must be negative")
            nulls = [k for k in L1_KEYS if d.get(k) is None]
            if len(nulls) > 6: warn(f"L1 {b}: {len(nulls)} null fields {nulls} (extraction may have failed)")
            if d.get("taxes") and d.get("total_taxes") is not None and abs(sum(e["amount"] for e in d["taxes"]) - d["total_taxes"]) > 1:
                warn(f"L1 {b}: tax lines do not sum to total_taxes")
            if d.get("provider") == "KE" and d.get("charges") and d.get("total_charges") is not None \
                    and abs(sum(e["amount"] for e in d["charges"]) - d["total_charges"]) > 1:
                warn(f"L1 {b}: charge lines do not sum to total_charges")
            if d.get("provider") != "KE" and d.get("charges") and d.get("total_charges") is not None \
                    and abs(sum(e["amount"] for e in d["charges"]) - d["total_charges"]) > 1:
                warn(f"L1 {b}: charges sum differs from total_charges (check if FPA/subsidy explains it)")
    # level 2
    p = os.path.join(out, "level2.csv")
    if os.path.exists(p):
        _, rows = read(p)
        for r in rows:
            b, q, a = r["bill_id"], r["question_id"], r["answer"]
            if not a.strip(): err(f"L2 {b} {q}: EMPTY answer"); continue
            if "could not be answered reliably" in a: warn(f"L2 {b} {q}: fallback answer")
            if len(a) < 40: warn(f"L2 {b} {q}: very short answer")
            if sum(ord(c) > 127 for c in a) / len(a) > 0.1: warn(f"L2 {b} {q}: not mostly English")
            if re.search(r"\b\d{9,}\b", a): warn(f"L2 {b} {q}: long digit string (possible ID leak)")
            if q in ("Q10", "Q11", "Q12") and not re.search(r"estimat|approx|roughly", a, re.I):
                warn(f"L2 {b} {q}: projection not labelled as estimate")


def text_files(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            if f.endswith((".py", ".md", ".txt", ".example", ".json", ".yml", ".toml")) or f == ".env.example":
                yield os.path.join(dp, f)


def check_code(src, real_key):
    if os.path.exists(os.path.join(src, ".env")): err("a real .env file is in the submission source")
    for p in text_files(src):
        t = open(p, encoding="utf-8", errors="ignore").read()
        if any(re.search(k, t) for k in KEY_PATTERNS) or (real_key and real_key in t):
            err(f"API KEY found in {p}")
        if re.search(r"textract|prebuilt-invoice|mindee|analyzeexpense", t, re.I) and not p.endswith(("audit.py", "README.md")):
            err(f"prohibited invoice-extraction service mentioned in {p}")
        if p.endswith(".py"):
            try: py_compile.compile(p, doraise=True)
            except Exception as e: err(f"syntax error in {p}: {e}")
    req = os.path.join(src, "requirements.txt")
    if not os.path.exists(req): err("requirements.txt missing")
    else:
        for l in open(req, encoding="utf-8"):
            l = l.strip()
            if l and not l.startswith("#") and "==" not in l: err(f"requirements not pinned: {l}")
    ex = os.path.join(src, ".env.example")
    model = None
    if not os.path.exists(ex): err(".env.example missing")
    else:
        env = dict(l.strip().split("=", 1) for l in open(ex, encoding="utf-8") if "=" in l and not l.startswith("#"))
        for k in ("MODEL_PROVIDER", "MODEL_NAME", "API_KEY"):
            if k not in env: err(f".env.example missing {k}")
        model = env.get("MODEL_NAME")
        if model not in MODELS: err(f"MODEL_NAME '{model}' is not an allowed model")
        if len(env.get("API_KEY", "")) > 25 and "your" not in env["API_KEY"].lower(): err(".env.example API_KEY looks real")
    rd = os.path.join(src, "README.md")
    if not os.path.exists(rd): err("README.md missing")
    else:
        t = open(rd, encoding="utf-8").read()
        if not re.search(r"python\s*3\.\d+", t, re.I): err("README: Python version not stated")
        if "ai usage" not in t.lower(): err("README: no 'AI usage' section")
        if "run.py" not in t: warn("README: run command (run.py) not found")
        if model and model not in t: warn(f"README does not mention the model '{model}'")
        if re.search(r"\[.*(write|fill|your|replace).*\]", t, re.I): warn("README still has [placeholder] text")


def check_zip(zp, template, real_key):
    size = os.path.getsize(zp) / 1e6
    print(f"ZIP size: {size:.2f} MB")
    if size > 15: err("ZIP is larger than 15 MB")
    z = zipfile.ZipFile(zp); names = z.namelist()
    for need in ("output/level1.csv", "output/level2.csv", "source/README.md", "source/.env.example", "source/requirements.txt"):
        if need not in names: err(f"ZIP missing {need}")
    for n in names:
        if re.search(r"(^|/)(\.env|\.venv|cache|__pycache__|train|test)(/|$)", n): err(f"ZIP contains forbidden path {n}")
        if n.endswith(("\\",)) or "\\" in n: err(f"ZIP entry uses backslashes: {n}")
    if not any(n.startswith("demo/") for n in names): warn("no demo video (optional, up to +5 points)")
    tmp = tempfile.mkdtemp(); z.extractall(tmp)
    check_csvs(template, os.path.join(tmp, "output"))
    check_code(os.path.join(tmp, "source"), real_key)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="test/csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--source", default=".")
    ap.add_argument("--zip")
    a = ap.parse_args()
    key = None
    if os.path.exists(".env"):
        for l in open(".env", encoding="utf-8"):
            if l.startswith("API_KEY="): key = l.split("=", 1)[1].strip() or None
    if a.zip: check_zip(a.zip, a.template, key)
    else:
        check_csvs(a.template, a.out); check_code(a.source, key)
    for w in warns: print("WARN ", w)
    for e in errors: print("ERROR", e)
    print(f"\n{len(errors)} errors, {len(warns)} warnings ->", "PASS" if not errors else "FIX THE ERRORS")
    sys.exit(1 if errors else 0)