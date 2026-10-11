import os
import sys
import csv
import json
import argparse

from level2 import process_bill, FALLBACK
from postprocess import normalize_level1

IMG_EXTS = (".png", ".jpg", ".jpeg")
CACHE_DIR = "cache"


def find_image(bills_dir, bill_id):
    for ext in IMG_EXTS:
        p = os.path.join(bills_dir, bill_id + ext)
        if os.path.exists(p):
            return p
    return None


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def clean_answer(text):
    return " ".join(str(text).split())      # single line, normal spacing


def run_bill(bill_id, bills_dir, questions, use_cache):
    cache_path = os.path.join(CACHE_DIR, bill_id + ".json")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        if all(qid in data["answers"] for qid, _ in questions):
            print(f"  (cached) {bill_id}")
            return data["level1"], data["answers"]

    image = find_image(bills_dir, bill_id)
    if image is None:
        print(f"  [error] no image found for {bill_id}", file=sys.stderr)
        return normalize_level1(None), {qid: FALLBACK for qid, _ in questions}

    l1, _, answers = process_bill(image, questions)

    healthy = l1.get("provider") is not None and all(a != FALLBACK for a in answers.values())
    if healthy:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"level1": l1, "answers": answers}, f, ensure_ascii=False)
    return l1, answers


def validate(out_dir, n_bills, n_questions_rows):
    ok = True
    _, r1 = read_csv(os.path.join(out_dir, "level1.csv"))
    _, r2 = read_csv(os.path.join(out_dir, "level2.csv"))
    print(f"\nlevel1.csv rows: {len(r1)} (expected {n_bills})")
    print(f"level2.csv rows: {len(r2)} (expected {n_questions_rows})")
    for r in r1:
        try:
            json.loads(r["json"])
        except Exception:
            ok = False
            print(f"  [bad] invalid JSON for {r['bill_id']}")
    for r in r2:
        if not r["answer"].strip():
            ok = False
            print(f"  [bad] empty answer {r['bill_id']} {r['question_id']}")
        elif r["answer"] == FALLBACK:
            print(f"  [warn] fallback answer {r['bill_id']} {r['question_id']}")
    print("VALID" if ok and len(r1) == n_bills and len(r2) == n_questions_rows else "PROBLEMS FOUND")


def main():
    ap = argparse.ArgumentParser(description="Generate level1.csv and level2.csv")
    ap.add_argument("--bills", required=True, help="folder with bill images")
    ap.add_argument("--csv", required=True, help="folder with the two template CSVs")
    ap.add_argument("--out", default="output", help="output folder")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached results")
    args = ap.parse_args()

    f1, rows1 = read_csv(os.path.join(args.csv, "level1.csv"))
    f2, rows2 = read_csv(os.path.join(args.csv, "level2.csv"))

    questions = {}
    for r in rows2:
        questions.setdefault(r["bill_id"], []).append((r["question_id"], r["question"]))
    bill_ids = []
    for r in rows1 + rows2:
        if r["bill_id"] not in bill_ids:
            bill_ids.append(r["bill_id"])

    results = {}
    for i, bid in enumerate(bill_ids, 1):
        print(f"[{i}/{len(bill_ids)}] {bid}")
        try:
            results[bid] = run_bill(bid, args.bills, questions.get(bid, []), not args.no_cache)
        except Exception as e:      # last-resort guard: never lose the whole run
            print(f"  [error] {bid} failed: {e}", file=sys.stderr)
            results[bid] = (normalize_level1(None),
                            {qid: FALLBACK for qid, _ in questions.get(bid, [])})

    for r in rows1:
        r["json"] = json.dumps(results[r["bill_id"]][0], separators=(",", ":"), ensure_ascii=False)
    for r in rows2:
        r["answer"] = clean_answer(results[r["bill_id"]][1].get(r["question_id"], FALLBACK))

    write_csv(os.path.join(args.out, "level1.csv"), f1, rows1)
    write_csv(os.path.join(args.out, "level2.csv"), f2, rows2)
    validate(args.out, len(rows1), len(rows2))


if __name__ == "__main__":
    main()