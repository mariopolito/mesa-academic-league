"""Build the Knowledge Engine prototype from game/items.json.

    python game/build_game.py

items.json is exported from the study site itself (see game/README.md), so the
game asks exactly the 749 questions the site's quiz asks under "Everything",
with the site's own wrong answers.

Writes game/engine.html (partial page, for the Artifact publish),
game/Knowledge-Engine.html (standalone, opens from disk) and engine/index.html,
the page the study site links to at /mesa-academic-league/engine/.
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
items = json.loads((HERE / "items.json").read_text(encoding="utf-8"))

TOPICS = {"tip", "cap", "state", "voc", "myth", "tense", "math", "sci", "eng", "ss", "roots"}
ids = set()
for it in items:
    assert it["t"] in TOPICS, it["t"]
    assert len(it["o"]) == 3 and it["a"] not in it["o"], it["id"]
    assert it["id"] not in ids, "duplicate id " + it["id"]
    ids.add(it["id"])
print(len(items), "items", dict(Counter(it["t"] for it in items)))

data = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
assert "</script" not in data.lower() and "<!--" not in data
src = (HERE / "engine_src.html").read_text(encoding="utf-8")
assert "/*ITEMS*/[]" in src
page = src.replace("/*ITEMS*/[]", data)
(HERE / "engine.html").write_text(page, encoding="utf-8", newline="\n")

head, _, body = page.partition("<!--BODY-->")
assert body, "engine_src.html needs a <!--BODY--> marker"
full = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + head + "</head><body>" + body + "</body></html>\n")
(HERE / "Knowledge-Engine.html").write_text(full, encoding="utf-8", newline="\n")
site = HERE.parent / "engine"
site.mkdir(exist_ok=True)
(site / "index.html").write_text(full, encoding="utf-8", newline="\n")
print("wrote game/engine.html, game/Knowledge-Engine.html and engine/index.html")
