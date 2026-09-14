# -*- coding: utf-8 -*-
"""What a publish from the sheet accepts, fixes, and refuses.

    python tools/test_content.py

Each case edits a copy of the real content the way a person in the sheet
might, and checks the message they would get back. The messages are the whole
interface for someone who can't read a stack trace, so they are tested too.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import content  # noqa: E402
import jslit  # noqa: E402

s = open(content.MAL, encoding="utf-8").read()
TABLES = content.read_tables(s)
BASE = json.loads(content.dump_content(content.to_tabs(TABLES)))["tabs"]
CATCODE = TABLES["CATCODE"]
failures = []


def run(edit):
    tabs = copy.deepcopy(BASE)
    edit(tabs)
    rep = content.Report()
    t = content.from_tabs(tabs, CATCODE, rep)
    return t, rep


def col(tabs, tab, h):
    return tabs[tab][0].index(h)


def expect(name, edit, errors=(), warnings=(), check=None):
    t, rep = run(edit)
    ok = True
    for e in errors:
        if not any(e in m for m in rep.errors):
            ok = False
            print("FAIL %s: no error containing %r; got %r" % (name, e, rep.errors[:3]))
    if not errors and rep.errors:
        ok = False
        print("FAIL %s: unexpected errors %r" % (name, rep.errors[:3]))
    for w in warnings:
        if not any(w in m for m in rep.warnings):
            ok = False
            print("FAIL %s: no warning containing %r; got %r" % (name, w, rep.warnings[:3]))
    if ok and check and not rep.errors:
        try:
            check(t)
        except AssertionError as e:
            ok = False
            print("FAIL %s: %s" % (name, e))
    if ok:
        print("PASS " + name)
    else:
        failures.append(name)


def set_cell(tab, row, h, v):
    def f(tabs):
        tabs[tab][row][col(tabs, tab, h)] = v
    return f


def both(*fs):
    def f(tabs):
        for g in fs:
            g(tabs)
    return f


# ------------------------------------------------------------------ cases
expect("unchanged content publishes clean", lambda tabs: None,
       check=lambda t: None)


def new_question(tabs):
    Q = tabs["Questions"]
    row = [""] * len(Q[0])
    for h, v in (("Quarter", "2, 3"), ("Subject", "MA"), ("Category", "Algebra"),
                 ("Level", "2"), ("Question", "What is 2 + 2?"), ("Answer", "4"),
                 ("Hint", "Count on your fingers."), ("Wrong answer 1", "3"),
                 ("Wrong answer 2", "5"), ("Wrong answer 3", "22")):
        row[Q[0].index(h)] = v
    Q.append(row)


def check_new(t):
    assert len(t["Q"]) == 361, len(t["Q"])
    q = t["Q"][360]
    assert q["qtr"] == [2, 3] and q["l"] == 2 and t["DIST"]["4"] == ["3", "5", "22"], q
    assert t["QHINTS"][360] == "Count on your fingers."


expect("new question at the bottom gets the next ID", new_question,
       warnings=["new row given ID q360"], check=check_new)


def delete_row(tabs):
    del tabs["Questions"][58]


expect("deleted question row is refused", delete_row,
       errors=["q57 is missing", "set Retired to yes"])


def retire(t):
    assert t["Q"][57].get("off") == 1 and len(t["Q"]) == 360


expect("retired question stays in place, marked off",
       set_cell("Questions", 58, "Retired", "yes"), check=retire)

# Grid row 3 is sheet row 4: the header is sheet row 1.
expect("bad level names tab, row and ID", set_cell("Questions", 3, "Level", "7"),
       errors=['Questions row 4 (q2): Level must be 1, 2 or 3 -- got "7"'])
expect("category filed under the wrong subject",
       set_cell("Questions", 2, "Subject", "MA"),
       errors=["Economics is a Social Studies category, but Subject says MA"])
expect("unknown category", set_cell("Questions", 2, "Category", "Astrology"),
       errors=['Category "Astrology" is not one of the site\'s categories'])
expect("two of three wrong answers", set_cell("Questions", 2, "Wrong answer 3", ""),
       errors=["fill all three wrong answers or none (2 filled)"])
expect("wrong answer equal to the answer",
       set_cell("Questions", 1, "Wrong answer 1", "Supply"),
       errors=['wrong answer "Supply" is the same as the right answer'])


def shared_answer(tabs):
    Q = tabs["Questions"]
    a = Q[0].index("Answer")
    rows = [i for i in range(1, len(Q)) if Q[i][a] == "2/5"]
    Q[rows[1]][Q[0].index("Wrong answer 1")] = "9/10"


expect("same answer, different wrong answers", shared_answer,
       errors=["shares its answer with", "make them match"])
expect("quarter out of range", set_cell("Questions", 2, "Quarter", "5"),
       errors=['Quarter must be 1-4, each once -- got "5"'])
expect("quarter blank", set_cell("Questions", 2, "Quarter", ""),
       errors=["Quarter is blank"])


def rename_header(tabs):
    tabs["Questions"][0][tabs["Questions"][0].index("Hint")] = "Hints"


expect("renamed header", rename_header,
       errors=['missing column "Hint"'], warnings=['ignored column "Hints"'])
expect("script tag in a cell", set_cell("Questions", 2, "Hint", "hi </script> there"),
       errors=['"Hint" contains "</script" or "<!--"'])
expect("line break in a cell is joined", set_cell("Questions", 1, "Hint", "one\ntwo"),
       warnings=['"Hint" had a line break'],
       check=lambda t: None if t["QHINTS"][0] == "one two" else (_ for _ in ()).throw(
           AssertionError(t["QHINTS"][0])))
expect("board answer without board wrong answers",
       set_cell("Questions", 2, "Board answer", "demand"),
       errors=["needs three wrong answers"])
expect("spelling sentence without its word",
       set_cell("Spelling", 1, "Sentence", "No word here."),
       errors=['the Sentence must contain "centipede"'])


def drop_state(tabs):
    del tabs["States"][5]


expect("49 states", drop_state, errors=["exactly 50 states -- found 49"])
expect("duplicate postal code", set_cell("States", 2, "Postal code", "AL"),
       errors=["postal code AL is also Alabama's"])
expect("capital group letter with no capital",
       lambda tabs: tabs["Capital groups"].append(["Q"]),
       errors=["no capital starts with Q"])


def dup_board(tabs):
    B = tabs["Memorize boards"]
    B[2][B[0].index("Right")] = B[1][B[0].index("Right")]


expect("memorize board with a repeated right side", dup_board,
       errors=["appears twice, so the board can't be solved"])


def new_board(tabs):
    B = tabs["Memorize boards"]
    for i in range(4):
        B.append(["vocab", "Vocabulary & usage", "Word", "Meaning", "w%d" % i, "m%d" % i])


def check_board(t):
    boards = dict(t["BOARDS"])
    assert boards["vocab"]["name"] == "Vocabulary &amp; usage", boards["vocab"]
    out = content.write_tables(s, t)
    keys = [k for k, _ in jslit.object_entries(out, "MATCHSETS")]
    assert keys[-1] == "vocab" and keys[:3] == ["caps", "nick", "motto"], keys


expect("new memorize board lands at the end", new_board, check=check_board)
expect("board ID taken by a built-in board",
       lambda tabs: tabs["Memorize boards"].append(["caps", "x", "a", "b", "c", "d"]),
       errors=['Board ID "caps" is taken'])


def tip_gap(tabs):
    del tabs["Tip-offs"][3]


expect("deleted tip-off", tip_gap, errors=["tip:2 is missing"])


def retired_written(t):
    out = content.write_tables(s, t)
    back = content.read_tables(out)
    assert back["Q"][57].get("off") == 1
    assert content.comparable(back)["QHINTS"] == t["QHINTS"]


expect("retired flag survives the write into mal.html",
       set_cell("Questions", 58, "Retired", "yes"), check=retired_written)

print()
if failures:
    print("%d failed" % len(failures))
    sys.exit(1)
print("all passed")
