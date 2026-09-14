# -*- coding: utf-8 -*-
"""Refresh the IACT data blob in mal.html from build/interactions.json.

Run after any change to tools/interactions.py:

    python tools/interactions.py --emit && python tools/update_iact.py
"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

P = "mal.html"
s = open(P, encoding="utf-8").read()
data = json.load(open("build/interactions.json", encoding="utf-8"))
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

m = re.search(r"^const IACT=.*?;$", s, re.M)
assert m, "IACT block not found"
s = s[:m.start()] + "const IACT=" + blob + ";" + s[m.end():]

lists = json.load(open("build/qlists.json", encoding="utf-8"))
lblob = json.dumps(lists, ensure_ascii=False, separators=(",", ":"))
m = re.search(r"^const QLISTS=.*?;$", s, re.M)
assert m, "QLISTS block not found"
s = s[:m.start()] + "const QLISTS=" + lblob + ";" + s[m.end():]
print("QLISTS refreshed:", len(lists), "questions")

open(P, "w", encoding="utf-8").write(s)

from collections import Counter
print("IACT refreshed:", len(data), "questions,", len(blob), "bytes")
print(dict(Counter(v["t"] for v in data.values())))
