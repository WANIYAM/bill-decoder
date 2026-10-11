import sys
import json


def flat(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flat(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = d
    return out


a = flat(json.load(open(sys.argv[1])))   # expected
b = flat(json.load(open(sys.argv[2])))   # model output
ok = True
for k in sorted(set(a) | set(b)):
    x, y = a.get(k, "<missing>"), b.get(k, "<missing>")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        same = abs(x - y) <= 1
    else:
        same = x == y
    if not same:
        ok = False
        print(f"DIFF {k}: expected={x!r} got={y!r}")
print("ALL MATCH" if ok else "Differences found")