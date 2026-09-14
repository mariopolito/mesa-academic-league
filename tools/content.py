# -*- coding: utf-8 -*-
"""The site's content, as the Google Sheet sees it.

    python tools/content.py export     mal.html -> content/content.json + schema.json
    python tools/content.py import     content/content.json -> mal.html (validates)
    python tools/content.py roundtrip  prove export -> import changes nothing
    python tools/content.py script OUT write the page's inline script out for `node --check`

The sheet is where content is edited; `sheet/Code.gs` publishes it by committing
content/content.json, and .github/workflows/publish.yml runs `import` on it.
Every tab is a header row plus rows of plain strings -- exactly what the sheet
displays -- and this file owns everything else: which column feeds which field,
what counts as valid, and how each table is written back into mal.html.

A content error that would break the page, or scramble a student's saved
progress, fails the publish with a message naming the tab and the row. Anything
merely odd is a warning and publishes anyway.
"""
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jslit  # noqa: E402

MAL = "mal.html"
CONTENT = "content/content.json"
SCHEMA = "content/schema.json"
GH = os.environ.get("GITHUB_ACTIONS") == "true"

SUBJECTS = ["MA", "SC", "EN", "SS"]
SUBJECT_NAME = {"MA": "Math", "SC": "Science", "EN": "English", "SS": "Social Studies"}
# Which subject each category is filed under. Every question in the packet
# agrees with this, so a mismatch in the sheet is a typo, not a choice. A new
# category also needs a code in CATCODE in mal.html; `import` checks the two
# lists agree.
CATEGORY_SUBJECT = {
    "Algebra": "MA", "Geometry": "MA", "Logic": "MA", "Numbers": "MA",
    "Probability": "MA", "Word Problems": "MA",
    "Current Events": "SS", "Economics": "SS", "US Geography": "SS", "US Law": "SS",
    "US History": "SS", "World Geography": "SS", "World History": "SS",
    "Language Arts": "EN", "Grammar": "EN", "Vocabulary": "EN", "Literature": "EN",
    "Physical Sci": "SC", "Life Sci": "SC", "Earth Sci": "SC", "General Science": "SC",
}
YES = "yes"

# The memorize boards built from other tabs. Their source is code, not data,
# so it lives here; the boards typed into the sheet are slotted in around them
# in the order the page has always shown them.
DERIVED_BOARDS = [
    ("caps", '{name:"State &rarr; Capital",l:"State",r:"Capital",pairs:CAPS.map(x=>[x[0],x[1]])}'),
    ("nick", '{name:"State &rarr; Nickname",l:"State",r:"Nickname",pairs:STATES.map(x=>[x[0],x[1].split(",")[0].split(" / ")[0]])}'),
    ("motto", '{name:"State &rarr; Motto",l:"State",r:"Motto",pairs:STATES.map(x=>[x[0],x[2].split(" / ")[0]])}'),
    ("roots", None),
    ("sci", None),
    ("tense", '{name:"Verb tense formulas",l:"Tense",r:"Formula",pairs:TENSES.map(t=>[t[0],t[1]])}'),
    ("myth", '{name:"Greek &rarr; Roman gods",l:"Greek",r:"Roman",pairs:MYTH.filter(m=>m.g!==m.r).map(m=>[m.g,m.r])}'),
    ("mythd", '{name:"God &rarr; Domain",l:"Greek god",r:"Rules over",pairs:MYTH.map(m=>[m.g,m.d])}'),
    ("econ", None),
]

# ----------------------------------------------------------------- the schema
# One entry per tab: (header, width px, options). Options: wrap, lock (the
# column is an id -- a warning pops up if someone edits it), choices (a
# dropdown), autoid (the sheet fills a blank id with prefix + next number),
# note (shown when you hover the header).


def col(h, w=120, **kw):
    d = {"h": h, "w": w}
    d.update(kw)
    return d


WRONG_NOTE = ("Three believable wrong answers, used for multiple choice. Fill all "
              "three or leave all three blank.")
TABS = [
    ("Questions", [
        col("ID", 64, lock=True, autoid="q",
            note="Leave blank on a new row; publishing fills it in. Never change "
                 "or reuse one: students' saved progress is keyed to it."),
        col("Retired", 70, choices=[YES],
            note="Set to yes to take a question off the site. Don't delete rows."),
        col("Quarter", 70, note="1, 2, 3 or 4. A question in two quarters: 2, 3"),
        col("Subject", 70, choices=SUBJECTS),
        col("Category", 130, choices=list(CATEGORY_SUBJECT)),
        col("Level", 55, choices=["1", "2", "3"]),
        col("Question", 420, wrap=True),
        col("Answer", 220, wrap=True),
        col("Hint", 320, wrap=True,
            note="Shown when a student asks for help. Nudge, don't tell."),
        col("Wrong answer 1", 150, wrap=True, note=WRONG_NOTE),
        col("Wrong answer 2", 150, wrap=True, note=WRONG_NOTE),
        col("Wrong answer 3", 150, wrap=True, note=WRONG_NOTE),
        col("List or matching", 90, choices=[YES],
            note="yes for a question with no single short answer (a list, a "
                 "matching set, an explain-the-difference). The site turns "
                 "these into boards where it can."),
        col("Board clue", 320, wrap=True,
            note="Category board only: the question rewritten as a statement "
                 "(\"This economic term describes...\"). Blank uses the question."),
        col("Board question word", 90, choices=["Who", "What", "Where"],
            note="Category board only: forces Who/What/Where for every option."),
        col("Board answer", 160, wrap=True,
            note="Category board only, rarely needed: the answer when the board "
                 "asks the question the other way round."),
        col("Board wrong answer 1", 140, wrap=True),
        col("Board wrong answer 2", 140, wrap=True),
        col("Board wrong answer 3", 140, wrap=True),
    ]),
    ("Spelling", [
        col("Word", 130, note="Renaming a word resets students' progress on it."),
        col("Quarter", 70),
        col("Level", 55, choices=["1", "2", "3"]),
        col("Definition", 320, wrap=True),
        col("Sentence", 360, wrap=True, note="Must contain the word; it is blanked out."),
        col("Spelling trap", 320, wrap=True,
            note="Shown after answering. <b>bold</b> and <em>italics</em> work."),
        col("Wrong word 1", 130), col("Wrong word 2", 130), col("Wrong word 3", 130),
    ]),
    ("Mythology", [
        col("Greek", 110, note="Renaming a god resets students' progress on it."),
        col("Roman", 110),
        col("Domain", 300, wrap=True),
        col("Memory hook", 360, wrap=True, note="Printed on the back of the card."),
        col("Card hint", 300, wrap=True,
            note="Only where the memory hook would give the Roman name away."),
    ]),
    ("States", [
        col("State", 130, lock=True, note="All fifty, no more and no fewer."),
        col("Capital", 130),
        col("Postal code", 70),
        col("Nicknames", 260, wrap=True),
        col("Motto", 260, wrap=True),
        col("Nickname story", 360, wrap=True),
        col("Motto meaning", 360, wrap=True),
    ]),
    ("Capital groups", [
        col("Letter", 70, note="The Reference page groups the capitals starting "
                               "with each letter listed here."),
    ]),
    ("Tip-offs", [
        col("ID", 64, lock=True, autoid="tip:"),
        col("Question", 380, wrap=True),
        col("Answer", 160, wrap=True),
        col("Why", 360, wrap=True),
        col("Hint", 300, wrap=True),
        col("Board statement", 320, wrap=True),
        col("Wrong answer 1", 140), col("Wrong answer 2", 140), col("Wrong answer 3", 140),
    ]),
    ("Verb tenses", [
        col("ID", 70, lock=True, autoid="tense:"),
        col("Tense", 150), col("Formula", 170),
        col("Example", 300, wrap=True), col("Meaning", 300, wrap=True),
        col("Why", 320, wrap=True), col("Hint", 300, wrap=True),
    ]),
    ("Memorize boards", [
        col("Board ID", 80, note="Short, lowercase, no spaces. Students' progress "
                                 "on a pair is keyed to it."),
        col("Board name", 170), col("Left heading", 110), col("Right heading", 130),
        col("Left", 200, wrap=True), col("Right", 320, wrap=True),
    ]),
]
README = [
    "Mesa Academic League study site: content",
    "",
    "Every question, hint and wrong answer on the site comes from this sheet.",
    "When you are done editing, choose Study site > Publish to site. Nothing",
    "goes live until then, and if something is wrong the publish stops and",
    "tells you the tab and row.",
    "",
    "Three rules keep students' saved progress safe:",
    "  1. Never delete a question row. Set Retired to yes instead.",
    "  2. Add new questions at the bottom, with the ID left blank.",
    "  3. Never edit an ID.",
    "",
    "Text can use <b>bold</b> and <em>italics</em>.",
    "",
    "Study site > Pull content from site replaces everything in this sheet",
    "with what is on the site. Only use it when asked to.",
]


def schema():
    return {"readme": README,
            "tabs": [{"name": n, "columns": cols} for n, cols in TABS]}


# --------------------------------------------------------- content.json format

def dump_content(tabs):
    """One row per line, so a git diff shows exactly which cells changed.
    sheet/Code.gs writes the identical format -- keep the two in step."""
    parts = []
    for name, rows in tabs.items():
        body = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"))
                          for r in rows)
        parts.append(json.dumps(name, ensure_ascii=False) + ":[\n" + body + "\n]")
    return '{"tabs":{\n' + ",\n".join(parts) + "\n}}\n"


# ------------------------------------------------------------ mal.html -> tabs

def read_tables(s):
    names = ("CAPS CAPGROUPS POSTAL STATES TIPOFFS Q SPELL TENSES MYTH DIST STATEINFO "
             "TIPWHY TENSEWHY QHINTS TIPHINTS TIPDIST TIPSTMT TENSEHINTS SPELLDIST "
             "CATCODE").split()
    t = {n: jslit.read_const(s, n) for n in names}
    boards = []
    for key, src in jslit.object_entries(s, "MATCHSETS"):
        if dict(DERIVED_BOARDS).get(key):
            continue
        val, _ = jslit.parse_at(src, 0)
        boards.append((key, val))
    t["BOARDS"] = boards
    return t


def qtr_text(v):
    if v is None:
        return "1"
    return ", ".join(str(x) for x in (v if isinstance(v, list) else [v]))


def unentity(t):
    return html.unescape(t)


def to_tabs(t):
    tabs = {}
    rows = [[c["h"] for c in dict(TABS)["Questions"]]]
    for i, q in enumerate(t["Q"]):
        d = t["DIST"].get(q["a"], ["", "", ""])
        jd = q.get("jd", ["", "", ""])
        rows.append(["q%d" % i, YES if q.get("off") else "", qtr_text(q.get("qtr")),
                     q["s"], q["c"], str(q["l"]), q["q"], q["a"], t["QHINTS"][i],
                     d[0], d[1], d[2], YES if q.get("sc") else "", q.get("j", ""),
                     q.get("jw", ""), q.get("ja", ""), jd[0], jd[1], jd[2]])
    tabs["Questions"] = rows

    rows = [[c["h"] for c in dict(TABS)["Spelling"]]]
    for i, x in enumerate(t["SPELL"]):
        d = t["SPELLDIST"][i]
        rows.append([x["w"], qtr_text(x.get("qtr")), str(x["l"]), x["d"], x["s"],
                     x.get("h", ""), d[0], d[1], d[2]])
    tabs["Spelling"] = rows

    rows = [[c["h"] for c in dict(TABS)["Mythology"]]]
    for m in t["MYTH"]:
        rows.append([m["g"], m["r"], m["d"], m.get("n", ""), m.get("h", "")])
    tabs["Mythology"] = rows

    rows = [[c["h"] for c in dict(TABS)["States"]]]
    for (state, cap), st in zip(t["CAPS"], t["STATES"]):
        assert st[0] == state
        info = t["STATEINFO"][state]
        rows.append([state, cap, t["POSTAL"][state], st[1], st[2], info["n"], info["m"]])
    tabs["States"] = rows

    tabs["Capital groups"] = [["Letter"]] + [[g["L"]] for g in t["CAPGROUPS"]]

    rows = [[c["h"] for c in dict(TABS)["Tip-offs"]]]
    for i, (q, a) in enumerate(t["TIPOFFS"]):
        d = t["TIPDIST"][i]
        rows.append(["tip:%d" % i, q, a, t["TIPWHY"][i], t["TIPHINTS"][i],
                     t["TIPSTMT"][i], d[0], d[1], d[2]])
    tabs["Tip-offs"] = rows

    rows = [[c["h"] for c in dict(TABS)["Verb tenses"]]]
    for i, tn in enumerate(t["TENSES"]):
        rows.append(["tense:%d" % i, tn[0], tn[1], tn[2], tn[3],
                     t["TENSEWHY"][i], t["TENSEHINTS"][i]])
    tabs["Verb tenses"] = rows

    rows = [[c["h"] for c in dict(TABS)["Memorize boards"]]]
    for key, b in t["BOARDS"]:
        for left, right in b["pairs"]:
            rows.append([key, unentity(b["name"]), b["l"], b["r"], left, right])
    tabs["Memorize boards"] = rows
    return tabs


# ------------------------------------------------------ tabs -> tables (checks)

class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append("%s: %s" % (where, msg))

    def warn(self, where, msg):
        self.warnings.append("%s: %s" % (where, msg))


class Tab:
    """A tab's rows as dicts keyed by header, with the sheet row number kept
    for messages. Blank rows are skipped but still counted."""

    def __init__(self, name, grid, rep):
        self.name = name
        self.rep = rep
        want = [c["h"] for c in dict(TABS)[name]]
        self.rows = []
        if not grid:
            rep.error(name, "the tab is missing or empty")
            self.ok = False
            return
        header = [h.strip() for h in grid[0]]
        missing = [h for h in want if h not in header]
        # Reported before a missing column stops the tab: a header that was
        # renamed shows up as one of each, and seeing both names is the clue.
        extra = [h for h in header if h and h not in want]
        if extra:
            rep.warn(name, "ignored column%s %s" % ("s" if len(extra) > 1 else "",
                                                    ", ".join('"%s"' % e for e in extra)))
        if missing:
            rep.error(name, "missing column%s %s -- a header was renamed or deleted"
                      % ("s" if len(missing) > 1 else "", ", ".join('"%s"' % m for m in missing)))
            self.ok = False
            return
        idx = {h: header.index(h) for h in want}
        for n, raw in enumerate(grid[1:], start=2):
            cells = {}
            for h, j in idx.items():
                v = raw[j] if j < len(raw) else ""
                v = "" if v is None else str(v)
                if "\n" in v or "\r" in v or "\t" in v:
                    v = re.sub(r"\s*[\r\n\t]+\s*", " ", v)
                    rep.warn("%s row %d" % (name, n), '"%s" had a line break, joined into one line' % h)
                v = v.strip()
                if "</script" in v.lower() or "<!--" in v:
                    rep.error("%s row %d" % (name, n), '"%s" contains "</script" or "<!--", '
                              "which would break the page" % h)
                cells[h] = v
            if any(cells.values()):
                self.rows.append((n, cells))
        self.ok = True

    def where(self, n, label=""):
        return "%s row %d%s" % (self.name, n, (" (%s)" % label) if label else "")


def parse_qtr(text, where, rep):
    if not text:
        rep.error(where, "Quarter is blank")
        return None
    try:
        vals = [int(x) for x in re.split(r"[,\s]+", text) if x]
    except ValueError:
        rep.error(where, 'Quarter must be numbers like 2 or "2, 3" -- got "%s"' % text)
        return None
    if not vals or any(v not in (1, 2, 3, 4) for v in vals) or len(set(vals)) != len(vals):
        rep.error(where, 'Quarter must be 1-4, each once -- got "%s"' % text)
        return None
    return vals


def qtr_value(vals):
    """Quarter 1 is the default and the page leaves it unwritten."""
    if vals == [1]:
        return None
    return vals[0] if len(vals) == 1 else vals


def parse_level(text, where, rep):
    if text not in ("1", "2", "3"):
        rep.error(where, 'Level must be 1, 2 or 3 -- got "%s"' % text)
        return None
    return int(text)


def yes(text, where, col, rep):
    if text.lower() in ("", "no"):
        return False
    if text.lower() in ("yes", "y", "x", "true"):
        return True
    rep.error(where, '%s must be yes or blank -- got "%s"' % (col, text))
    return False


def same(a, b):
    return re.sub(r"\s+", " ", a).strip().lower() == re.sub(r"\s+", " ", b).strip().lower()


def wrongs(cells, heads, answer, where, rep, required=False):
    vals = [cells[h] for h in heads]
    filled = [v for v in vals if v]
    if not filled:
        if required:
            rep.error(where, "needs three wrong answers")
        return None
    if len(filled) != 3:
        rep.error(where, "fill all three wrong answers or none (%d filled)" % len(filled))
        return None
    for v in vals:
        if same(v, answer):
            rep.error(where, 'wrong answer "%s" is the same as the right answer' % v)
    if len({v.lower() for v in vals}) != 3:
        rep.error(where, "two of the wrong answers are the same")
    return vals


def ids(tab, prefix, rep):
    """Sort a tab's rows by their ID, filling blanks with the next number, and
    refuse a gap: a deleted row would shift every later item's saved progress
    onto the wrong question."""
    pat = re.compile(r"^%s(\d+)$" % re.escape(prefix))
    got, blank = {}, []
    for n, c in tab.rows:
        v = c["ID"]
        if not v:
            blank.append((n, c))
            continue
        m = pat.match(v)
        if not m:
            rep.error(tab.where(n), 'ID "%s" should look like %s12' % (v, prefix))
            continue
        k = int(m.group(1))
        if k in got:
            rep.error(tab.where(n), 'ID %s is also on row %d' % (v, got[k][0]))
            continue
        got[k] = (n, c)
    nxt = max(got) + 1 if got else 0
    for n, c in blank:
        c["ID"] = "%s%d" % (prefix, nxt)
        got[nxt] = (n, c)
        rep.warn(tab.where(n), "new row given ID %s" % c["ID"])
        nxt += 1
    gaps = [k for k in range(nxt) if k not in got]
    if gaps:
        rep.error(tab.name, "%s is missing. Rows can't be deleted -- students' progress "
                  "is stored by position. Put the row back%s."
                  % (", ".join("%s%d" % (prefix, k) for k in gaps[:5]),
                     " and set Retired to yes" if prefix == "q" else ""))
    return [got[k] for k in sorted(got)]


def from_tabs(tabs, catcode, rep):
    t = {}
    T = {name: Tab(name, tabs.get(name), rep) for name, _ in TABS}
    if not all(x.ok for x in T.values()):
        return None
    if set(catcode) != set(CATEGORY_SUBJECT):
        rep.error("tools/content.py", "CATEGORY_SUBJECT and CATCODE in mal.html list "
                  "different categories")

    # ------------------------------------------------------------ Questions
    tab = T["Questions"]
    Q, hints, dist, dist_from = [], [], {}, {}
    W = ["Wrong answer 1", "Wrong answer 2", "Wrong answer 3"]
    BW = ["Board wrong answer 1", "Board wrong answer 2", "Board wrong answer 3"]
    for n, c in ids(tab, "q", rep):
        w = tab.where(n, c["ID"])
        q = {}
        s = c["Subject"]
        if s not in SUBJECTS:
            rep.error(w, 'Subject must be MA, SC, EN or SS -- got "%s"' % s)
        cat = c["Category"]
        if cat not in CATEGORY_SUBJECT:
            rep.error(w, 'Category "%s" is not one of the site\'s categories' % cat)
        elif s in SUBJECTS and CATEGORY_SUBJECT[cat] != s:
            rep.error(w, '%s is a %s category, but Subject says %s'
                      % (cat, SUBJECT_NAME[CATEGORY_SUBJECT[cat]], s))
        lv = parse_level(c["Level"], w, rep)
        for h in ("Question", "Answer"):
            if not c[h]:
                rep.error(w, "%s is blank" % h)
        q.update(s=s, c=cat, l=lv, q=c["Question"], a=c["Answer"])
        qt = parse_qtr(c["Quarter"], w, rep)
        if qt and qtr_value(qt) is not None:
            q["qtr"] = qtr_value(qt)
        if yes(c["List or matching"], w, "List or matching", rep):
            q["sc"] = 1
        if c["Board clue"]:
            q["j"] = c["Board clue"]
        if c["Board question word"]:
            if c["Board question word"] not in ("Who", "What", "Where"):
                rep.error(w, 'Board question word must be Who, What or Where -- got "%s"'
                          % c["Board question word"])
            q["jw"] = c["Board question word"]
        if c["Board answer"]:
            q["ja"] = c["Board answer"]
            jd = wrongs(c, BW, c["Board answer"], w, rep, required=True)
            if jd:
                q["jd"] = jd
        elif any(c[h] for h in BW):
            rep.error(w, "board wrong answers need a Board answer")
        if yes(c["Retired"], w, "Retired", rep):
            q["off"] = 1
        if not c["Hint"] and not q.get("off"):
            rep.warn(w, "no hint")
        d = wrongs(c, W, c["Answer"], w, rep)
        if d:
            a = c["Answer"]
            if a in dist and dist[a] != d:
                rep.error(w, 'shares its answer with %s, but the wrong answers differ. '
                          'Questions with the same answer share wrong answers -- make '
                          'them match.' % dist_from[a])
            else:
                dist[a], dist_from[a] = d, c["ID"]
        Q.append(q)
        hints.append(c["Hint"])
    t["Q"], t["QHINTS"], t["DIST"] = Q, hints, dist

    # ------------------------------------------------------------- Spelling
    tab = T["Spelling"]
    SPELL, SD, seen = [], [], {}
    for n, c in tab.rows:
        w = tab.where(n, c["Word"])
        word = c["Word"]
        if not word:
            rep.error(w, "Word is blank")
            continue
        if word.lower() in seen:
            rep.error(w, '"%s" is also on row %d' % (word, seen[word.lower()]))
        seen[word.lower()] = n
        x = {"w": word, "l": parse_level(c["Level"], w, rep), "d": c["Definition"],
             "s": c["Sentence"], "h": c["Spelling trap"]}
        if not c["Definition"]:
            rep.error(w, "Definition is blank")
        if word.lower() not in c["Sentence"].lower():
            rep.error(w, 'the Sentence must contain "%s" -- the word is blanked out of it'
                      % word)
        qt = parse_qtr(c["Quarter"], w, rep)
        if qt and qtr_value(qt) is not None:
            x["qtr"] = qtr_value(qt)
        SPELL.append(x)
        SD.append(wrongs(c, ["Wrong word 1", "Wrong word 2", "Wrong word 3"], word, w, rep,
                         required=True) or ["", "", ""])
    t["SPELL"], t["SPELLDIST"] = SPELL, SD

    # ------------------------------------------------------------ Mythology
    tab = T["Mythology"]
    MYTH, seen = [], {}
    for n, c in tab.rows:
        w = tab.where(n, c["Greek"])
        for h in ("Greek", "Roman", "Domain"):
            if not c[h]:
                rep.error(w, "%s is blank" % h)
        if c["Greek"].lower() in seen:
            rep.error(w, '"%s" is also on row %d' % (c["Greek"], seen[c["Greek"].lower()]))
        seen[c["Greek"].lower()] = n
        m = {"d": c["Domain"], "g": c["Greek"], "r": c["Roman"]}
        if c["Card hint"]:
            m["h"] = c["Card hint"]
        m["n"] = c["Memory hook"]
        MYTH.append(m)
    t["MYTH"] = MYTH

    # --------------------------------------------------------------- States
    tab = T["States"]
    CAPS, STATES, POSTAL, INFO = [], [], {}, {}
    codes = {}
    for n, c in tab.rows:
        st = c["State"]
        w = tab.where(n, st)
        if st in POSTAL:
            rep.error(w, "%s is listed twice" % st)
        for h in ("Capital", "Nicknames", "Motto"):
            if not c[h]:
                rep.error(w, "%s is blank" % h)
        code = c["Postal code"]
        if not re.fullmatch(r"[A-Z]{2}", code):
            rep.error(w, 'Postal code must be two capital letters -- got "%s"' % code)
        elif code in codes:
            rep.error(w, "postal code %s is also %s's" % (code, codes[code]))
        codes[code] = st
        for h in ("Nickname story", "Motto meaning"):
            if not c[h]:
                rep.warn(w, "%s is blank" % h)
        CAPS.append([st, c["Capital"]])
        STATES.append([st, c["Nicknames"], c["Motto"]])
        POSTAL[st] = code
        INFO[st] = {"n": c["Nickname story"], "m": c["Motto meaning"]}
    if len(CAPS) != 50:
        rep.error("States", "there must be exactly 50 states -- found %d" % len(CAPS))
    t["CAPS"], t["STATES"], t["POSTAL"], t["STATEINFO"] = CAPS, STATES, POSTAL, INFO

    # ------------------------------------------------------- Capital groups
    tab = T["Capital groups"]
    groups, seen = [], set()
    for n, c in tab.rows:
        L = c["Letter"].upper()
        w = tab.where(n, L)
        if not re.fullmatch(r"[A-Z]", L):
            rep.error(w, 'Letter must be a single letter -- got "%s"' % c["Letter"])
            continue
        if L in seen:
            rep.error(w, "%s is listed twice" % L)
        seen.add(L)
        items = sorted(cap + ", " + POSTAL.get(st, "") for st, cap in CAPS if cap.startswith(L))
        if not items:
            rep.error(w, "no capital starts with %s" % L)
        groups.append({"L": L, "n": len(items), "items": items})
    t["CAPGROUPS"] = groups

    # ------------------------------------------------------------- Tip-offs
    tab = T["Tip-offs"]
    t["TIPOFFS"], t["TIPWHY"], t["TIPHINTS"], t["TIPSTMT"], t["TIPDIST"] = [], [], [], [], []
    for n, c in ids(tab, "tip:", rep):
        w = tab.where(n, c["ID"])
        for h in ("Question", "Answer", "Why", "Hint", "Board statement"):
            if not c[h]:
                rep.error(w, "%s is blank" % h)
        t["TIPOFFS"].append([c["Question"], c["Answer"]])
        t["TIPWHY"].append(c["Why"])
        t["TIPHINTS"].append(c["Hint"])
        t["TIPSTMT"].append(c["Board statement"])
        t["TIPDIST"].append(wrongs(c, W, c["Answer"], w, rep, required=True) or ["", "", ""])

    # ---------------------------------------------------------- Verb tenses
    tab = T["Verb tenses"]
    t["TENSES"], t["TENSEWHY"], t["TENSEHINTS"] = [], [], []
    for n, c in ids(tab, "tense:", rep):
        w = tab.where(n, c["ID"])
        for h in ("Tense", "Formula", "Example", "Meaning"):
            if not c[h]:
                rep.error(w, "%s is blank" % h)
        for h in ("Why", "Hint"):
            if not c[h]:
                rep.warn(w, "%s is blank" % h)
        t["TENSES"].append([c["Tense"], c["Formula"], c["Example"], c["Meaning"]])
        t["TENSEWHY"].append(c["Why"])
        t["TENSEHINTS"].append(c["Hint"])

    # ------------------------------------------------------ Memorize boards
    tab = T["Memorize boards"]
    derived = {k for k, v in DERIVED_BOARDS if v}
    boards = {}
    for n, c in tab.rows:
        key = c["Board ID"]
        w = tab.where(n, key)
        if not re.fullmatch(r"[a-z][a-z0-9]*", key):
            rep.error(w, 'Board ID must be short, lowercase, no spaces -- got "%s"' % key)
            continue
        if key in derived:
            rep.error(w, 'Board ID "%s" is taken by a board built from another tab' % key)
            continue
        if not (c["Left"] and c["Right"]):
            rep.error(w, "Left and Right both need something")
        b = boards.setdefault(key, {"row": n, "name": c["Board name"], "l": c["Left heading"],
                                    "r": c["Right heading"], "pairs": []})
        for h, k in (("Board name", "name"), ("Left heading", "l"), ("Right heading", "r")):
            if c[h] != b[k]:
                rep.error(w, '%s differs from row %d of the same board ("%s")' % (h, b["row"], b[k]))
        b["pairs"].append([c["Left"], c["Right"]])
    for key, b in boards.items():
        w = "Memorize boards (%s)" % key
        if not b["name"] or not b["l"] or not b["r"]:
            rep.error(w, "needs a Board name, Left heading and Right heading")
        if len(b["pairs"]) < 4:
            rep.error(w, "needs at least 4 pairs -- has %d" % len(b["pairs"]))
        for side, j in (("Left", 0), ("Right", 1)):
            vals = [p[j].lower() for p in b["pairs"]]
            dup = sorted({v for v in vals if vals.count(v) > 1})
            if dup:
                rep.error(w, '%s "%s" appears twice, so the board can\'t be solved' % (side, dup[0]))
    t["BOARDS"] = [(k, {"name": html.escape(b["name"], quote=False), "l": b["l"], "r": b["r"],
                        "pairs": b["pairs"]}) for k, b in boards.items()]
    return t


# ------------------------------------------------------ tables -> mal.html

def write_tables(s, t):
    rep = jslit.replace_const
    s = rep(s, "CAPS", jslit.emit(t["CAPS"]))
    s = rep(s, "CAPGROUPS", jslit.emit_rows(t["CAPGROUPS"], " "))
    s = rep(s, "POSTAL", jslit.emit_map(t["POSTAL"], "  "))
    s = rep(s, "STATES", jslit.emit_rows(t["STATES"]))
    s = rep(s, "TIPOFFS", jslit.emit_rows(t["TIPOFFS"]))
    s = rep(s, "Q", jslit.emit_rows(t["Q"]))
    s = rep(s, "SPELL", jslit.emit_rows(t["SPELL"]))
    s = rep(s, "TENSES", jslit.emit_rows(t["TENSES"]))
    s = rep(s, "MYTH", jslit.emit_rows(t["MYTH"], " "))
    s = rep(s, "DIST", jslit.emit_map(t["DIST"]))
    s = rep(s, "STATEINFO", jslit.emit_map(t["STATEINFO"]))
    for name in ("TIPWHY", "TENSEWHY", "QHINTS", "TIPHINTS", "TIPDIST", "TIPSTMT",
                 "TENSEHINTS", "SPELLDIST"):
        s = rep(s, name, jslit.emit_rows(t[name]))
    typed = dict(t["BOARDS"])
    entries = []
    for key, src in DERIVED_BOARDS:
        if src:
            entries.append((key, src))
        elif key in typed:
            entries.append((key, jslit.emit(typed.pop(key))))
    entries += [(k, jslit.emit(v)) for k, v in typed.items()]
    s = rep(s, "MATCHSETS", "{\n" + ",\n".join("  %s:%s" % kv for kv in entries) + "\n}")
    return s


def comparable(t):
    """The tables with the parts that are allowed to differ removed: DIST's key
    order is never read, and board names round-trip through the entity form."""
    out = dict(t)
    out["DIST"] = dict(sorted(t["DIST"].items()))
    out.pop("CATCODE", None)
    return out


# ------------------------------------------------------------------- main

def annotate(level, msg):
    if GH:
        msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::%s::%s" % (level, msg))
    else:
        print("%s: %s" % (level.upper(), msg))


def load_mal():
    return open(MAL, encoding="utf-8").read()


def cmd_export():
    s = load_mal()
    t = read_tables(s)
    os.makedirs("content", exist_ok=True)
    open(CONTENT, "w", encoding="utf-8", newline="\n").write(dump_content(to_tabs(t)))
    open(SCHEMA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(schema(), ensure_ascii=False, indent=1) + "\n")
    print("wrote %s and %s" % (CONTENT, SCHEMA))


def cmd_import():
    s = load_mal()
    catcode = jslit.read_const(s, "CATCODE")
    tabs = json.load(open(CONTENT, encoding="utf-8"))["tabs"]
    rep = Report()
    t = from_tabs(tabs, catcode, rep)
    shown = 10  # GitHub shows ten annotations of each kind per step
    for m in rep.warnings[:shown]:
        annotate("warning", m)
    if len(rep.warnings) > shown:
        annotate("warning", "...and %d more notes" % (len(rep.warnings) - shown))
    for m in rep.errors[:shown]:
        annotate("error", m)
    if rep.errors:
        if len(rep.errors) > shown:
            annotate("error", "...and %d more problems" % (len(rep.errors) - shown))
        print("%d problem%s -- nothing was published." % (len(rep.errors), "" if len(rep.errors) == 1 else "s"))
        sys.exit(1)
    out = write_tables(s, t)
    # Read it back: what was written must parse to exactly what was checked.
    back = read_tables(out)
    assert comparable(back) == comparable(dict(t, CATCODE=None)), "write-back mismatch"
    if out != s:
        open(MAL, "w", encoding="utf-8").write(out)
        print("mal.html updated: %d questions (%d retired), %d spelling words, %d gods"
              % (len(t["Q"]), sum(1 for q in t["Q"] if q.get("off")), len(t["SPELL"]), len(t["MYTH"])))
    else:
        print("mal.html already matches the sheet")


def cmd_roundtrip():
    s = load_mal()
    t = read_tables(s)
    tabs = json.loads(dump_content(to_tabs(t)))["tabs"]
    rep = Report()
    back = from_tabs(tabs, t["CATCODE"], rep)
    assert not rep.errors, rep.errors
    a, b = comparable(t), comparable(back)
    for k in a:
        if a[k] != b[k]:
            print("DIFFERS:", k)
            if isinstance(a[k], list):
                for i, (x, y) in enumerate(zip(a[k], b[k])):
                    if x != y:
                        print("  first at", i, x, y)
                        break
    assert a == b, "tables differ after the round trip"
    out = write_tables(s, back)
    assert comparable(read_tables(out)) == a, "mal.html differs after write-back"
    print("round trip clean: %d warnings" % len(rep.warnings))
    for m in rep.warnings[:8]:
        print("  " + m)
    return out


def cmd_script(dest):
    page = open("index.html", encoding="utf-8").read()
    blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert blocks, "no inline script in index.html"
    open(dest, "w", encoding="utf-8").write("\n;\n".join(blocks))
    print("wrote %d script block(s) to %s" % (len(blocks), dest))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export":
        cmd_export()
    elif cmd == "import":
        cmd_import()
    elif cmd == "roundtrip":
        cmd_roundtrip()
    elif cmd == "script":
        cmd_script(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
