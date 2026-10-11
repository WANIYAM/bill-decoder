import os, shutil, zipfile, subprocess, sys

EXCLUDE_PY = {"package.py", "test_key.py", "make_fake_templates.py"}
STAGE, ZIP = "submission_stage", "submission.zip"

if os.path.exists(STAGE): shutil.rmtree(STAGE)
os.makedirs(f"{STAGE}/source"); os.makedirs(f"{STAGE}/output")

for f in os.listdir("."):
    if f.endswith(".py") and f not in EXCLUDE_PY:
        shutil.copy(f, f"{STAGE}/source/{f}")
for f in ("README.md", ".env.example", "requirements.txt"):
    if os.path.exists(f): shutil.copy(f, f"{STAGE}/source/{f}")
    else: print(f"WARNING: {f} is missing")
for f in ("level1.csv", "level2.csv"):
    shutil.copy(f"output/{f}", f"{STAGE}/output/{f}")
if os.path.isdir("demo"):
    vids = [f for f in os.listdir("demo") if f.lower().endswith((".mp4", ".mov", ".webm"))]
    if vids:
        os.makedirs(f"{STAGE}/demo")
        shutil.copy(f"demo/{vids[0]}", f"{STAGE}/demo/{vids[0]}")

if os.path.exists(ZIP): os.remove(ZIP)
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, _, fn in os.walk(STAGE):
        for f in fn:
            full = os.path.join(dp, f)
            z.write(full, os.path.relpath(full, STAGE).replace(os.sep, "/"))

print(f"\nBuilt {ZIP}: {os.path.getsize(ZIP)/1e6:.2f} MB")
with zipfile.ZipFile(ZIP) as z:
    for n in z.namelist(): print("  ", n)
sys.exit(subprocess.call([sys.executable, "audit.py", "--zip", ZIP]))