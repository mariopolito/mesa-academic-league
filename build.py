# -*- coding: utf-8 -*-
"""Wrap the partial document in mal.html into the standalone download.

mal.html must stay a PARTIAL document (no doctype/html/head/body) because the
Artifact tool supplies its own skeleton. The standalone file the coach hands
out needs a real one, hence this step. Run after every edit to mal.html.
"""
import sys

SRC = "mal.html"
OUT = "Mesa-Academic-League.html"

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Mesa Academic League — study tool for Mesa Academy for Advanced Studies. All four quarters plus mythology.">
<style>html{color-scheme:light dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
"""

s = open(SRC, encoding="utf-8").read()
for bad in ("<!doctype", "<!DOCTYPE", "<html", "<body"):
    assert bad not in s, "mal.html must stay a partial document; found " + bad

# The split point is the first markup element in the source.
ANCHOR = '<div class="board">'
i = s.index(ANCHOR)
doc = HEAD + s[:i] + "</head>\n<body>\n" + s[i:] + "\n</body>\n</html>\n"
open(OUT, "w", encoding="utf-8").write(doc)
print("wrote", OUT, len(doc), "bytes")

# The repo's copy of the page. GitHub and a static host both serve index.html,
# so the published page carries that name; the other file is the one the coach
# hands out.
open("index.html", "w", encoding="utf-8", newline="\n").write(doc)
print("wrote index.html")
