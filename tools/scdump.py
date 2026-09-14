# -*- coding: utf-8 -*-
"""Dump the question bank out of mal.html so the interaction parsers can be
designed against real data.

    python tools/scdump.py
"""
import html
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

QRE = re.compile(
    r'\{s:"(\w+)",c:"([^"]*)",l:(\d),q:"((?:[^"\\]|\\.)*)",a:"((?:[^"\\]|\\.)*)"([^}]*)\}')


def unescape(t):
    t = t.replace('\\"', '"').replace("\\\\", "\\")
    t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    return html.unescape(t)


def load(path="mal.html"):
    s = open(path, encoding="utf-8").read()
    i = s.index("const Q=[")
    blk = s[i:s.index("\n];", i)]
    out = []
    for n, m in enumerate(QRE.finditer(blk)):
        subj, cat, lvl, q, a, tail = m.groups()
        out.append(dict(i=n, s=subj, c=cat, l=int(lvl),
                        q=unescape(q), a=unescape(a), sc="sc:1" in tail))
    return out


if __name__ == "__main__":
    recs = load()
    print("total", len(recs), " self-check", sum(1 for r in recs if r["sc"]))
    json.dump(recs, open("build/qbank.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
