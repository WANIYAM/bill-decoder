import os
import csv
from level2 import SAMPLE_QUESTIONS

ids = sorted(os.path.splitext(f)[0] for f in os.listdir("train/bills"))
os.makedirs("fake_csv", exist_ok=True)
with open("fake_csv/level1.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["bill_id", "json"])
    for i in ids:
        w.writerow([i, ""])
with open("fake_csv/level2.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["bill_id", "question_id", "question", "answer"])
    for i in ids:
        for qid, q in SAMPLE_QUESTIONS:
            w.writerow([i, qid, q, ""])
            