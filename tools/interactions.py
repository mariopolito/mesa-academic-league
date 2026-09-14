# -*- coding: utf-8 -*-
"""Turn the self-check questions into answerable widgets.

165 of the 359 questions have no single short answer, so the app could only ever
show them, reveal the key, and ask the student to be honest. That is the weakest
kind of practice: a sixth grader stares at "name the five Great Lakes largest to
smallest", thinks vaguely, and marks themselves right.

This module parses those questions into structured interactions the page can
actually grade:

  match  two parallel lists, click one from each side      (Match each … to …)
  order  a sequence to put in the right order              (Arrange … in order)
  parts  a) b) c) sub-answers, one input each              (State the term for: a) …)
  pick   choose N correct items out of a set               (List six forms of energy)
  cat    sort items into two or more buckets               (Classify each as …)
  some   tick every member of a subset                     (Which of these are NOT …)
  free   no reliable structure — reveal and self-grade     (Explain the difference …)

Showing the student the options gives away more than a blank page does. That is
the point: attempting and being corrected beats staring and guessing.

    python tools/interactions.py            # coverage report
    python tools/interactions.py --emit     # write build/interactions.json
"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ------------------------------------------------------------------ utilities

DASH = "–—-"
BULLET = re.compile(r"^\s*(?:([a-hA-H])[.)]|(\d{1,2})[.)])\s*")


def clean(t):
    return re.sub(r"\s+", " ", t).strip(" ;,.")


def split_items(text, seps=";,"):
    """Split a list, preferring semicolons when they are present."""
    text = text.strip()
    if ";" in text:
        parts = text.split(";")
    else:
        parts = re.split(r",(?![^()]*\))", text)
    return [clean(p) for p in parts if clean(p)]


def strip_bullet(t):
    return BULLET.sub("", t.strip()).strip()


def strip_paren(t):
    """Drop pronunciation guides and bracketed asides that would break matching."""
    t = re.sub(r"\s*\((?:[^()]*)\)", "", t)
    t = re.sub(r"\s*\[[^\]]*\]", "", t)
    return clean(t)


# "Huron /hyoor-on" and "Erie/eer-ee" are pronunciation guides; the hyphen is
# what distinguishes them from a genuine alternative like "exclamation mark/point".
PRONOUN = re.compile(r"\s*/\s*[a-z]+(?:-[a-z]+)+\s*$")
LEADIN = re.compile(r"^\s*(?:MUST BE IN THIS ORDER|ANY [A-Z]+ OF THE FOLLOWING)\s*:?\s*",
                    re.I)


def tidy_item(t):
    """Strip the debris that clings to answer-key list items."""
    t = LEADIN.sub("", t)
    t = strip_bullet(t)
    t = PRONOUN.sub("", t)
    t = strip_paren(t)
    t = re.sub(r"^\d+\s+", "", t)                      # "7 pulmonary veins"
    t = re.sub(r"^and\s+", "", t, flags=re.I)          # "…, and The Crucible"
    t = clean(t.rstrip(")"))
    if t.count("(") == t.count(")") + 1:               # unclosed in the packet
        t += ")"
    return t


NUMWORD = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
COUNT_CUE = re.compile(r"\b(%s|\d{1,2})\b" % "|".join(NUMWORD), re.I)


def stem_count(q):
    """How many items the question says it wants, if it says so at all."""
    m = COUNT_CUE.search(q or "")
    if not m:
        return None
    w = m.group(1).lower()
    return int(w) if w.isdigit() else NUMWORD[w]


def split_trailing_and(items, src="", limit=40, q=None):
    """'Among the Enemy and Among the Free' is two items, not one.

    But "Harry Potter and the Deathly Hallows" is one item, not two, and the
    text alone cannot tell them apart. The stem can: both questions name their
    length ("seven novels"), so split only when the count is one short and the
    split makes it right. With no count in the stem, fall back to splitting.
    """
    want = stem_count(q)
    if want is not None and len(items) != want - 1:
        return items
    if items and " and " in items[-1] and len(items[-1]) < limit * 2:
        head, tail = items[-1].rsplit(" and ", 1)
        if clean(head) and clean(tail):
            items = items[:-1] + [clean(head), clean(tail)]
    return items


# ------------------------------------------------------- accepted answers

DO_NOT = re.compile(r"\s*[\[(]\s*do not accept[^\])]*[\])]", re.I)
ACCEPT = re.compile(r"\s*[\[(]\s*accept\s+([^\])]*)[\])]", re.I)


def answer_alts(text):
    """(what to show, [what to accept]) for a typed answer.

    The keys carry their own marking guidance — "reject [accept object]",
    "pedal(s)", "(Samuel de) Champlain" — and a student who types any of those
    forms has answered the question.
    """
    text = DO_NOT.sub("", text).strip()
    alts = set()
    # "glamour [glamorous]" -- a bare bracket with no "accept"/"do not accept"
    # is the packet offering a second form of the same answer.
    bare = re.match(r"^(.*?)\s*\[([^\]]+)\]$", text)
    if bare and not re.match(r"\s*(do not\s+)?accept\b", bare.group(2), re.I):
        alts.add(clean(bare.group(2)))
        text = clean(bare.group(1))
    for m in ACCEPT.finditer(text):
        for piece in re.split(r"\s+or\s+|,", m.group(1)):
            if clean(piece):
                alts.add(clean(piece))
    shown = clean(ACCEPT.sub("", text))
    if not shown:
        return text, sorted(alts)
    alts.add(shown)
    alts.add(strip_paren(shown))                      # "(Samuel de) Champlain"
    inner = re.sub(r"[()]", "", shown)                # "post office (box)"
    alts.add(clean(inner))
    if shown.endswith("(s)"):
        alts.add(shown[:-3].strip())
        alts.add(shown[:-3].strip() + "s")
    for piece in shown.split("/"):
        if clean(piece) and len(clean(piece)) > 2:
            alts.add(clean(piece))
    # "9 diagonals" -- a student typing the number has answered the question,
    # and the unit is already in the prompt.
    num = re.match(r"^(-?[\d,.]+)\s+[A-Za-z][A-Za-z ]{2,}$", shown)
    if num:
        alts.add(num.group(1))
    return shown, sorted(x for x in alts if x)


# ------------------------------------------------------------------- matching

LIST_LABEL = re.compile(
    r"(?:^|\s)((?:[A-Z][A-Za-z’]*\s?){1,3}):\s*", re.M)

def label_start(m):
    """Where a LIST_LABEL match's label actually begins.

    LIST_LABEL has to allow three words so it can read "Time Periods:", which
    means it also swallows the tail of the item before it: "Zaire New Name:"
    and "McCulloch v. Maryland Constitution:" both start inside the previous
    entry. tidy_label already knows how to trim a captured label back to the
    real one, so trust it and measure from the end.
    """
    raw = m.group(1).rstrip()
    lab = tidy_label(raw, raw)
    return m.start(1) + len(raw) - len(lab)


def labelled_lists(q):
    """Pull the parallel lists out of a matching stem: [(label, [items]), ...]."""
    body = q.split(":", 1)[1] if ":" in q else q
    hits = list(LIST_LABEL.finditer(q))
    if len(hits) < 2:
        return []
    out = []
    for k, m in enumerate(hits):
        start = m.end()
        # LIST_LABEL swallows up to three words, so the next hit's start sits
        # inside this list's last item -- "McCulloch v. Maryland Constitution:"
        # ended the item at "McCulloch v". Trim to the label's own last word.
        end = label_start(hits[k + 1]) if k + 1 < len(hits) else len(q)
        items = split_items(q[start:end])
        out.append((clean(m.group(1)), items))
    return [x for x in out if len(x[1]) >= 2]


# Strict first: a separator dash must have space around it, or "y-intercept"
# and "one-fourth" get torn in half. Only if that yields nothing do we allow a
# bare dash, which is what "shale-slate, limestone-marble" needs.
PAIR_STRICT = re.compile(r"\s*=\s*|\s+[%s]\s+" % DASH)
PAIR_LOOSE = re.compile(r"\s*[=%s]\s*" % DASH)


def _pairs_from(chunks, splitter):
    pairs = []
    for chunk in chunks:
        chunk = strip_bullet(chunk)
        bits = splitter.split(chunk)
        if len(bits) == 2 and all(clean(b) for b in bits):
            pairs.append((clean(bits[0]), clean(bits[1])))
        elif chunk.count("/") == 1 and not splitter.search(chunk):
            l, r = chunk.split("/")
            if clean(l) and clean(r):
                pairs.append((clean(l), clean(r)))
            else:
                return []
        else:
            return []
    return pairs


def parse_pairs(a):
    """Answer of the form 'Amin - Uganda, Castro - Cuba, …' -> [(l, r), …].

    Several keys mix ';' and ',' as the separator inside one answer, so try the
    semicolon split first and fall back to splitting on either.
    """
    splits = (split_items(a), [clean(x) for x in re.split(r"[;,]", a) if clean(x)])
    for splitter in (PAIR_STRICT, PAIR_LOOSE):
        for chunks in splits:
            pairs = _pairs_from(chunks, splitter)
            if len(pairs) >= 3:
                return pairs
    return []


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def pairs_look_right(q, pairs):
    """Reject a parse whose left-hand values did not come from the question.

    This is the guard that catches a separator splitting inside a word: the
    slope question yields a left side of 'slope 3, y', which appears nowhere in
    the stem, so the whole parse is thrown away rather than shown to a student.
    """
    stem = _norm(q)
    for l, r in pairs:
        if len(l) < 3 or len(r) < 2:
            return False
        if not _in_stem(l, stem):
            return False
    return True


def _in_stem(value, stem):
    """'Gallia or Gaul' is one key for two spellings; either one counts."""
    if _norm(value) in stem:
        return True
    alts = [x for x in re.split(r"\s+or\s+", value, flags=re.I) if clean(x)]
    return len(alts) > 1 and all(_norm(x) in stem for x in alts)


LETTER_ITEM = re.compile(r"(?:^|\s)([A-G])[.)]\s*")
# The stems that carve into items use lower-case letters as often as capitals;
# every item is checked against the widget's own tiles before anything is cut,
# so a false split cannot silently remove text.
LETTER_ANY = re.compile(r"(?:^|\s)([A-Ga-g])[.)]\s*")
LABEL_EQ = re.compile(r"(?:^|[\s;])([A-Z][A-Za-z ]{2,30})\s*=\s*")
NUM_ITEM = re.compile(r"(?:^|[\s;,])(\d{1,2})[.)]\s+")
QUOTED = re.compile("[“\"]([^”\"]{2,90})[”\"]")

KNOWN_LABELS = (
    "Countries", "Country", "Civilizations", "Definitions", "Constitution",
    "Amendments", "New Name", "Old Name", "Cities", "Areas", "Time Periods",
    "Events", "Inventions", "Poets", "Titles", "Book", "Books", "Setting",
    "Languages", "Terms", "Words", "Examples", "Devices", "National Parks",
    "States", "Landmarks", "Cemeteries", "Parks", "Homes", "Animals", "Fables",
    "Specialty", "Works", "Cases", "Rivers", "Dictators", "Relationships",
    "Rock type", "Parent rock", "Becomes", "Character", "Characters",
)


def tidy_label(raw, fallback):
    """'Joseph Stalin Countries' -> 'Countries'.

    The label regex has to allow multi-word labels ("Time Periods"), which means
    it also swallows the last item of the preceding list. Trim back to a label we
    recognise, or to the final word.
    """
    raw = clean(raw)
    for k in sorted(KNOWN_LABELS, key=len, reverse=True):
        if raw.lower().endswith(k.lower()):
            return k
    words = raw.split()
    return words[-1] if words else fallback


def letters_map(q):
    """Lettered definition lists in a stem: {'A': 'study of ancient life', …}."""
    ms = list(LETTER_ITEM.finditer(q))
    out = {}
    for k, m in enumerate(ms):
        end = ms[k + 1].start() if k + 1 < len(ms) else len(q)
        out[m.group(1).upper()] = clean(q[m.end():end])
    return out


def expand_lefts(q, pairs):
    """'Pot' is how the key writes it; 'Pol Pot' is what the stem shows."""
    lists = labelled_lists(q)
    if not lists:
        return pairs
    pool = lists[0][1]
    low = {x.lower() for x in pool}
    out = []
    for l, r in pairs:
        # "conflict" is its own entry in a list that also holds "internal
        # conflict" -- a key that already matches the stem verbatim is not an
        # abbreviation of the longer one.
        if l.lower() in low:
            out.append((l, r))
            continue
        hits = [x for x in pool
                if len(x) > len(l)
                and re.search(r"\b%s\b" % re.escape(l), x, re.I)]
        out.append((clean(hits[0]), r) if len(hits) == 1 else (l, r))
    return out


def stem_pool(q):
    """Every list entry the stem shows, however the list is punctuated.

    The two lists are sliced against each other, not one after the other: the
    Supreme Court stem runs "...signed by a judge. 1. Brown v. Board of
    Education..." straight on, so the lettered list's last item swallows the
    whole numbered list unless the numbers end it.
    """
    marks = []
    for rx in (NUM_ITEM, LETTER_ANY):
        got = list(rx.finditer(q))
        if len(got) >= 3:
            marks += got
    marks.sort(key=lambda m: m.start())
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(q)
        x = clean(q[m.end():end]).strip(" ;,.")
        if x:
            out.append(x)
    return out


def expand_rights(q, pairs):
    """'Gideon' is how the key writes it; 'Gideon v. Wainwright' is on the page.

    The mirror of expand_lefts, and it matters for more than tidiness: a tile
    reading "Gideon" is not showing the stem's "Gideon v. Wainwright", so the
    stem cannot drop its own list without losing the full case names. Expanding
    the tile puts the whole name on the board and lets the list go.
    """
    pool = stem_pool(q)
    if not pool:
        return pairs
    low = {x.lower() for x in pool}
    lefts = {l.lower() for l, _ in pairs}
    rights = [r for _, r in pairs]
    out = []
    for l, r in pairs:
        if r.lower() in low or not r:
            out.append((l, r))
            continue
        hits = [x for x in pool
                if len(x) > len(r) and x.lower() not in lefts
                and re.search(r"\b%s\b" % re.escape(r), x, re.I)
                # A candidate that also contains another pair's answer is not
                # this answer spelled out -- it is a run-on that swallowed the
                # whole list, and expanding into it collapses the board.
                and not any(o != r and re.search(r"\b%s\b" % re.escape(o), x, re.I)
                            for o in rights)]
        out.append((l, clean(hits[0])) if len(hits) == 1 else (l, r))
    # Distinctness is the board's invariant: two tiles reading the same thing
    # cannot be told apart, so a colliding expansion is thrown away whole.
    if len({r.lower() for _, r in out}) != len({r.lower() for _, r in pairs}):
        return pairs
    return out


def as_match(q, a):
    pairs = parse_pairs(a)
    if not pairs:
        return None
    # Keys like 'Ecology - C' point into a lettered list in the stem.
    if all(len(r) == 1 and r.isalpha() for _, r in pairs):
        table = letters_map(q)
        resolved = [(l, table.get(r.upper(), "")) for l, r in pairs]
        if all(r for _, r in resolved):
            pairs = resolved
    if not pairs_look_right(q, pairs):
        return None
    lefts = [l for l, _ in pairs]
    rights = [r for _, r in pairs]
    # A matching board needs both columns distinct; repeated right-hand values
    # mean this is really a sorting question, which as_cat handles.
    if len(set(lefts)) != len(lefts) or len(set(rights)) != len(rights):
        return None
    # A right-hand side that is itself a list is a grouping question.
    if any("," in r for r in rights):
        return None
    pairs = expand_lefts(q, pairs)
    if len({l for l, _ in pairs}) != len(pairs):
        return None
    lists = labelled_lists(q)
    left_label, right_label = "Term", "Match"
    if len(lists) >= 2:
        left_label = tidy_label(lists[0][0], "Term")
        right_label = tidy_label(lists[1][0], "Match")
    return {"t": "match", "l": left_label, "r": right_label,
            "pairs": [[l, r] for l, r in pairs]}


ECHO = re.compile(r"^\s*[=%s]\s*" % DASH)


def drop_echo(left, val):
    """'Don Quixote - Spanish' keyed against 'Don Quixote' is just 'Spanish'."""
    if val.lower().startswith(left.lower()):
        rest = ECHO.sub("", val[len(left):])
        if rest and rest != val:
            return clean(rest)
    return val


def as_match_lettered(q, a):
    """'Works: A. Chains, Spy  B. …' + 'A. the 1960s, B. …' -> real pairs.

    The answer keys these by letter, so the left-hand text has to be recovered
    from the stem before the board means anything.
    """
    am = list(PART_A.finditer(a))
    if len(am) < 3:
        return None
    qm = list(LETTER_ITEM.finditer(q))
    if len(qm) < len(am):
        return None

    def carve(text, ms, upto=None):
        out = {}
        for k, m in enumerate(ms):
            end = ms[k + 1].start() if k + 1 < len(ms) else (upto or len(text))
            out[m.group(1).upper()] = clean(text[m.end():end])
        return out

    # The stem's lettered list is followed by the second list ("Setting: …"),
    # so the final item must stop there rather than run to the end.
    cut = len(q)
    for m in LIST_LABEL.finditer(q):
        if m.start() > qm[0].start():
            cut = label_start(m)
            break
    qitems, aitems = carve(q, qm, cut), carve(a, am)
    pairs = []
    for letter, val in aitems.items():
        stem = qitems.get(letter)
        if not stem or not val or len(stem) > 90:
            return None
        val = drop_echo(stem, val)
        if not val:
            return None
        pairs.append((stem, val))
    if len(pairs) < 3:
        return None
    lefts = [l for l, _ in pairs]
    rights = [r for _, r in pairs]
    if len(set(lefts)) != len(lefts):
        return None
    if len(set(rights)) != len(rights):
        return lettered_cat(q, pairs)
    return {"t": "match", "l": "Item", "r": "Match",
            "pairs": [[l, r] for l, r in pairs]}


def lettered_cat(q, pairs):
    """Same pairs, sorted into buckets instead of matched one to one."""
    used = sorted({r for _, r in pairs}, key=str.lower)
    if not 2 <= len(used) <= 8 or any(len(r) > 30 for r in used):
        return None
    cats = used
    # The stem's second list names every bucket, including the ones this key
    # never uses -- offering only the used ones would narrow the question.
    lists = labelled_lists(q)
    if len(lists) >= 2:
        listed = [strip_paren(x) for x in lists[1][1]]
        low = {x.lower() for x in listed}
        if listed and {r.lower() for r in used} <= low and len(listed) <= 10:
            byl = {r.lower(): r for r in used}
            cats = sorted((byl.get(x.lower(), x) for x in listed), key=str.lower)
    return {"t": "cat", "cats": cats, "items": [[l, r] for l, r in pairs]}


# ------------------------------------------------------------------- ordering

ORDER_CUE = re.compile(
    r"\b(arrange|in (?:the )?(?:correct |chronological )?order|"
    r"from largest to smallest|from smallest to largest|"
    r"in order of|order from|decreasing|increasing|"
    r"highest to (?:the )?lowest|lowest to highest|sequence|"
    r"beginning with the introductory|starting with the earliest|"
    r"alphabetical order|order of occurrence)\b", re.I)


PART_Q = re.compile(r"(?:^|\s)([a-hA-H])[.)]\s*")
PART_A = re.compile(r"(?:^|[;,]\s*)([a-hA-H])[.)]\s*")

IN_ORDER_TO = re.compile(r"\bin order to\b", re.I)


def as_order(q, a):
    # "…moved to Arizona in order to escape the cold" is not an ordering task.
    probe = IN_ORDER_TO.sub(" ", q)
    if not ORDER_CUE.search(probe):
        return None
    # A stem with its own a) b) c) parts is a multi-part question that happens
    # to say "a correct list will be in alphabetical order".
    if len(list(PART_Q.finditer(q))) >= 3:
        return None
    items = split_trailing_and([tidy_item(x) for x in split_items(a)], a, q=q)
    items = [x for x in items if x and len(x) < 90]
    if len(items) < 3 or len({x.lower() for x in items}) != len(items):
        return None
    if re.search(r"may vary|any \w+ of", a, re.I):
        return None
    return {"t": "order", "items": items}


# ---------------------------------------------------------------- multi-part



def as_parts(q, a):
    qm = list(PART_Q.finditer(q))
    am = list(PART_A.finditer(a))
    if len(qm) < 2 or len(am) < 2:
        return None
    letters_q = [m.group(1).lower() for m in qm]
    letters_a = [m.group(1).lower() for m in am]
    if letters_q[:len(letters_a)] != letters_a:
        return None

    def carve(text, ms):
        out = []
        for k, m in enumerate(ms):
            end = ms[k + 1].start() if k + 1 < len(ms) else len(text)
            out.append(clean(text[m.end():end]))
        return out

    prompts, answers = carve(q, qm), carve(a, am)
    if len(prompts) != len(answers):
        return None
    if any(not x for x in prompts + answers):
        return None
    if any(len(x) > 120 for x in answers):
        return None
    # A multi-part answer drawn from a small repeating vocabulary — igneous /
    # sedimentary / metamorphic, say — is really a sorting question. Buttons
    # beat free typing there, and the student still has to place every item.
    vocab = {x.lower() for x in answers}
    if (2 <= len(vocab) <= 5 and len(vocab) <= 0.75 * len(answers)
            and all(len(x) <= 20 for x in answers)):
        return {"t": "cat", "cats": full_cats(q, sorted(set(answers), key=str.lower)),
                "items": [[p, ans] for p, ans in zip(prompts, answers)]}
    shown, accept = [], []
    for ans in answers:
        disp, alts = answer_alts(ans)
        shown.append(disp)
        accept.append(alts)
    return {"t": "parts", "labels": letters_a, "prompts": prompts,
            "answers": shown, "accept": accept}


# -------------------------------------------------------------- pick N of set

# "ANY SIX OF THE FOLLOWING:" and the shorter "Any two:" are the same
# preamble. The colon is required: it separates instruction from list.
ANY_N = re.compile(
    r"\bany\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*"
    r"(?:of the following)?\s*:\s*", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def as_pick(q, a):
    m = ANY_N.search(a)
    if not m:
        return None
    n = m.group(1).lower()
    n = WORDNUM.get(n, None) or (int(n) if n.isdigit() else None)
    if not n:
        return None
    rest = a[m.end():]
    items = split_trailing_and([tidy_item(x) for x in split_items(rest)], rest)
    # Several keys tack an explanation onto the end of the list; anything long
    # is prose, not an option.
    items = [x for x in items if x and len(x) <= 40]
    if len(items) <= n or len({x.lower() for x in items}) != len(items):
        return None
    return {"t": "pick", "n": n, "options": items}


# ------------------------------------------------------------- categorisation

CAT_CUE = re.compile(
    r"\b(classify|identify (?:the following|each)|state whether each|"
    r"identify the following as)\b", re.I)


def as_cat(q, a):
    if not CAT_CUE.search(q):
        return None
    pairs = []
    for chunk in split_items(a):
        chunk = strip_bullet(chunk)
        bits = PAIR_LOOSE.split(chunk)
        if len(bits) != 2 or not all(bits):
            return None
        pairs.append((clean(bits[0]), strip_paren(bits[1])))
    if len(pairs) < 3:
        return None
    cats = sorted({r for _, r in pairs})
    if len(cats) < 2 or len(cats) > 6 or len(cats) == len(pairs):
        return None
    return {"t": "cat", "cats": full_cats(q, cats),
            "items": [[l, r] for l, r in pairs]}


# ------------------------------------------------------------- unordered set

SET_CUE = re.compile(r"^\s*(list|name|state|identify)\b", re.I)
SET_STOP = re.compile(r"may vary|explain|describe|difference|\bwhy\b", re.I)


def as_set(q, a):
    """'List the four bases…' — type each one in, order does not matter."""
    if not SET_CUE.search(q) or SET_STOP.search(q) or SET_STOP.search(a):
        return None
    if PAIR_LOOSE.search(a) or ":" in a:
        return None
    raws = [x for x in (strip_bullet(x) for x in split_items(a)) if x]
    # "editing and publishing" arrives as one chunk holding the last two items
    if raws and " and " in raws[-1] and len(raws[-1]) < 40:
        head, tail = raws[-1].rsplit(" and ", 1)
        raws[-1:] = [clean(head), clean(tail)]
    items = [strip_paren(answer_alts(x)[0]) for x in raws]
    items = [x for x in items if x]
    if not 3 <= len(items) <= 12:
        return None
    if len({x.lower() for x in items}) != len(items):
        return None
    if any(len(x) > 40 or not x for x in items):
        return None
    accept = []
    for raw, it in zip(raws, items):
        _, alts = answer_alts(raw)
        alts = set(alts) | {it}
        # "Augusta, Maine" — accept the city on its own too
        if "," in it:
            alts.add(clean(it.split(",")[0]))
        accept.append(sorted(alts))
    return {"t": "set", "items": items, "accept": accept}


# ------------------------------------------------------ select all that apply

SOME_CUE = re.compile(r"which of the following|which ones? of|are not written", re.I)


def as_some(q, a):
    """'Which of these were NOT written by Shakespeare?' -> tick the subset."""
    if not SOME_CUE.search(q):
        return None
    lists = labelled_lists(q)
    pool = lists[-1][1] if lists else split_items(q.split(":", 1)[-1])
    pool = [tidy_item(x) for x in pool]
    pool = split_trailing_and(pool)
    correct = split_trailing_and([tidy_item(x) for x in split_items(a)], a)
    if len(pool) < 4 or not 1 <= len(correct) < len(pool):
        return None
    low = {x.lower() for x in pool}
    if not all(c.lower() in low for c in correct):
        return None
    return {"t": "some", "options": pool, "correct": correct}


# --------------------------------------------------- positional a-to-b pairing

POSITIONAL_CUE = re.compile(r"\bthe following\b", re.I)


def as_positional(q, a):
    """'Pluralize the following nouns: goose, passerby, …' + 'geese, passersby, …'

    No a) b) labels, but the two lists line up one for one. Only trusted when
    the counts match exactly and every item is short.
    """
    if not POSITIONAL_CUE.search(q) or ":" not in q:
        return None
    prompts = [tidy_item(x) for x in split_items(q.rsplit(":", 1)[1])]
    answers = [tidy_item(x) for x in split_items(a)]
    prompts = [x for x in prompts if x]
    answers = [x for x in answers if x]
    if len(prompts) < 3 or len(prompts) != len(answers):
        return None
    if any(len(x) > 34 for x in prompts + answers):
        return None
    if len({x.lower() for x in prompts}) != len(prompts):
        return None
    if any(p.lower() == b.lower() for p, b in zip(prompts, answers)):
        return None
    shown, accept = [], []
    for ans in answers:
        disp, alts = answer_alts(ans)
        shown.append(disp)
        accept.append(alts)
    return {"t": "parts", "labels": [chr(97 + i) for i in range(len(prompts))],
            "prompts": prompts, "answers": shown, "accept": accept}


# A stem that names its own categories -- "as igneous, sedimentary, or
# metamorphic" -- is the authority on what the buttons should be.
CAT_LIST = re.compile(
    r"\b(?:as|either|is a|are)\s+((?:[a-z][a-z \-]{2,24},\s*){1,6}"
    r"(?:and\s+|or\s+)?[a-z][a-z \-]{2,24})\b", re.I)

# ...and where it does not, the missing bucket has to be supplied by hand.
# Keyed by a distinctive stretch of the stem.
CAT_EXTRA = {
    # 85, 180, 92 and 12 degrees happen to include no right angle, and a set of
    # buttons reading acute/obtuse/straight says so out loud.
    "Name the type of angle that has each of the given measures": ["right"],
}


def full_cats(q, cats):
    """Widen the buttons to every category the question itself offers."""
    for key, extra in CAT_EXTRA.items():
        if key in q:
            return sorted(set(cats) | set(extra), key=str.lower)
    low = {c.lower() for c in cats}
    for m in CAT_LIST.finditer(q):
        listed = [clean(x) for x in re.split(r",|\bor\b|\band\b", m.group(1))]
        listed = [x for x in listed if x]
        if len(listed) < len(cats) or not low <= {x.lower() for x in listed}:
            continue
        # Keep the key's own capitalisation for the buckets it used.
        byl = {c.lower(): c for c in cats}
        return sorted((byl.get(x.lower(), x) for x in listed), key=str.lower)
    return cats


# ------------------------------------------------------------- grouping key

def as_group(q, a):
    """'Archaic - Draconian reforms, First Punic War; Classical - ...' -> cat.

    as_match deliberately rejects this shape (a right-hand side that is itself a
    list), so without this parser a grouping question falls all the way through
    to free text. Every category and every member has to appear in the stem, for
    the same reason pairs_look_right exists.
    """
    chunks = [clean(x) for x in a.split(";") if clean(x)]
    if not 2 <= len(chunks) <= 6:
        return None
    stem = _norm(q)
    cats, items = [], []
    for chunk in chunks:
        bits = PAIR_STRICT.split(strip_bullet(chunk))
        if len(bits) != 2:
            return None
        cat, rest = clean(bits[0]), bits[1]
        members = [x for x in (tidy_item(y) for y in rest.split(",")) if x]
        # One bucket may hold a single item -- correcting the Greek-periods key
        # left the Archaic period with only the Draconian reforms in it. At
        # least one bucket still has to hold a list, or this is a 1:1 board and
        # as_match's job.
        if not cat or len(cat) > 40 or not members or not _in_stem(cat, stem):
            return None
        for m in members:
            if len(m) > 60 or not _in_stem(m, stem):
                return None
            items.append([m, cat])
        cats.append(cat)
    if len(items) < 4 or len(cats) != len(set(cats)):
        return None
    if len(items) == len(cats):
        return None
    if len({m.lower() for m, _ in items}) != len(items):
        return None
    return {"t": "cat", "cats": full_cats(q, cats), "items": items}


# ------------------------------------------------ blanks with a bank of words

# "Mrs. Smith is a great coach" is one sentence; without the lookbehinds the
# split lands inside it and the blank ends up in the wrong row.
SENT_SPLIT = re.compile(
    r"(?<!\bMr\.)(?<!\bMrs\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bJr\.)"
    r"(?<=[.!?”])\s+(?=[A-Z“‘])")
# a word bank is quoted, and this packet quotes it with single curly quotes
BANKED = re.compile("[‘']([^’']{1,40})[’']")
CHOICE = re.compile(r"\(([^()/]{1,20}/[^()]{1,20})\)")


def as_blank_choice(q, a):
    """'Jake is an excellent trumpet player, (but/and) his piano skills...' -> cat.

    Each sentence carries its own two choices and the key gives the answers in
    order. Rendered as a sorting board, one row per sentence, the student taps
    the word instead of reading the whole exercise as a wall of text.
    """
    body = q.split(":", 1)[1] if ":" in q else q
    sents = [clean(x) for x in SENT_SPLIT.split(body) if CHOICE.search(x)]
    answers = [clean(x) for x in split_items(a) if clean(x)]
    if len(sents) < 3 or len(sents) != len(answers):
        return None
    cats, items = set(), []
    for sent, ans in zip(sents, answers):
        opts = [clean(o) for o in CHOICE.search(sent).group(1).split("/")]
        if ans not in opts:
            return None
        cats |= set(opts)
        items.append([CHOICE.sub("______", sent), ans])
    if not 2 <= len(cats) <= 8:
        return None
    out = {"t": "cat", "cats": sorted(cats), "items": items}
    if ":" in q:
        out["stem"] = clean(q.split(":", 1)[0])
    return out


def as_bank_blank(q, a):
    """'...appropriate preposition: after, along, across, above' + blanks -> cat.

    The bank is printed once at the top and every sentence has a blank in it, so
    the board's buttons are the bank and its rows are the sentences.
    """
    if ":" not in q or "___" not in q:
        return None
    head, body = q.split(":", 1)
    bank = [clean(x) for x in QUOTED.findall(body) + BANKED.findall(body)]
    if len(bank) < 3:
        return None
    # the bank sits before the first sentence; the sentences follow
    first = body.find("___")
    lead_end = body.rfind(bank[-1]) + len(bank[-1])
    if lead_end >= first:
        return None
    sents = [clean(x).lstrip("’”'\" ,;") for x in SENT_SPLIT.split(body[lead_end:])
             if "___" in x]
    answers = [clean(x) for x in split_items(a) if clean(x)]
    if len(sents) < 3 or len(sents) != len(answers):
        return None
    if any(x not in bank for x in answers):
        return None
    return {"t": "cat", "cats": sorted(set(bank)), "stem": clean(head),
            "items": [[sent, ans] for sent, ans in zip(sents, answers)]}


def as_pairs_typed(q, a):
    """'bird = fledgling; deer = fawn; seal = pup; rat = pup' -> parts.

    A key like this reads as a board until you notice two animals whose young
    are both called a pup: the same tile cannot answer two rows, so it is typed
    rather than matched. as_match and as_cat get first refusal.
    """
    pairs = parse_pairs(a)
    if len(pairs) < 3 or not pairs_look_right(q, pairs):
        return None
    rights = [r for _, r in pairs]
    if len({r.lower() for r in rights}) == len(rights):
        return None                    # no duplicates: it is a board, not a fill-in
    shown, accept = [], []
    for _, r in pairs:
        text, alts = answer_alts(r)
        shown.append(text)
        accept.append(alts or [text])
    return {"t": "parts", "labels": [chr(97 + i) for i in range(len(pairs))],
            "prompts": [l for l, _ in pairs], "answers": shown, "accept": accept}


# ------------------------------------------------------------------ overrides

# Two questions the parsers get structurally right but pedagogically wrong.
# Keyed by a distinctive stretch of the stem rather than by index, because the
# question bank gets reordered.
OVERRIDES = (
    # Parsed as a typed set of "Augusta, Maine" strings, which meant the hint
    # had to name all five capitals for the question to be answerable at all.
    # Give the states and let the student produce the capitals.
    ("five US state capitals that start with the letter", {
        "t": "parts",
        "labels": ["a", "b", "c", "d", "e"],
        "prompts": ["Maine", "Maryland", "New York", "Texas", "Georgia"],
        "answers": ["Augusta", "Annapolis", "Albany", "Austin", "Atlanta"],
        "accept": [["Augusta"], ["Annapolis"], ["Albany"],
                   ["Austin"], ["Atlanta"]],
    }),

    # The stem lists five quoted examples and five devices, but the answer key
    # letters them a-e and the stem never letters anything, so no parser can
    # line them up. Written out here, which also gives Self-check a real Match
    # widget instead of reveal-and-hope.
    ("Match each example with its figurative language device", {
        "t": "match",
        "l": "Example",
        "r": "Device",
        "pairs": [
            ["“Every cloud has a silver lining.”", "idiom"],
            ["“Foolish wisdom”", "oxymoron"],
            ["“Your suitcase weighs a ton.”", "hyperbole"],
            ["“The buzzing bee flew away.”", "onomatopoeia"],
            ["“The flowers danced in the gentle breeze.”", "personification"],
        ],
    }),

    # The packet's key has the first two swapped -- (a) is "could not deny legal
    # counsel", which is Gideon, and (b) is "public school segregation", which
    # is Brown. MAL-packet-review.md SS-UL-2 carries the correction and
    # tools/corrections.py applies it to the printed packet; this applies the
    # same correction to the app, which was still teaching the packet's order.
    ("Match the following Supreme Court cases with their outcomes", {
        "t": "parts",
        "labels": ["a", "b", "c", "d"],
        "prompts": [
            "Ruled that states could not deny legal counsel to defendants",
            "Ruled that public school segregation was unconstitutional",
            "Ruled that those in police custody must be made aware of their rights",
            "Ruled that evidence collected by police during a search is only "
            "admissible with a warrant signed by a judge",
        ],
        "answers": ["Gideon", "Brown", "Miranda", "Mapp"],
        "accept": [["Gideon", "Gideon v. Wainwright"],
                   ["Brown", "Brown v. Board of Education of Topeka"],
                   ["Miranda", "Miranda v. Arizona"],
                   ["Mapp", "Mapp v. Ohio"]],
    }),
)


def override(q):
    for key, iv in OVERRIDES:
        if key in q:
            return json.loads(json.dumps(iv))
    return None


# ------------------------------------------------------- flashcard splitting

# A question that asks for four things at once makes a hopeless flashcard, so
# the parts are dealt out one per card. The stem cannot just be reused: "Name
# each city of the ancient world: its trade empire was destroyed after 146 BC"
# is not a sentence. Every lead below has been read against its own parts.
#
#   key   -> the stem's own lead, verbatim
#   value -> the lead to print on a single card, or None to keep the question
#            whole because its parts depend on each other
#
# A lead that is not in this table is never split. That is deliberate: a wrong
# split teaches a sixth grader a garbled question, and the coverage report says
# how many are waiting to be reviewed.
CARD_LEAD = {
    "State the term that means:":
        "State the term that means:",
    "Identify the following Revolutionary War battles:":
        "Identify this Revolutionary War battle:",
    "Name these early explorers of the New World:":
        "Name this early explorer of the New World:",
    "Identify the scientific instruments based on the following descriptions:":
        "Identify the scientific instrument:",
    "Identify the chemical element that:":
        "Identify the chemical element that",
    "State the meaning of the following abbreviations:":
        "State the meaning of the abbreviation:",
    "State the title of the following Charles Dickens novels by their opening lines:":
        "State the title of the Charles Dickens novel that opens:",
    "Define and identify the objective complements in the following sentences then "
    "state whether they are nouns or adjectives:":
        "Identify the objective complement in this sentence, and say whether it is "
        "a noun or an adjective:",
    "Determine if the following sentences require \u201cit\u2019s\u201d or "
    "\u201cits\u201d in the blank:":
        "Does this sentence need \u201cit\u2019s\u201d or \u201cits\u201d in the blank?",
    "Determine if the following sentences require a hyphen; if so, indicate where the "
    "hyphen should be":
        "Does this sentence need a hyphen? If so, where?",
    "Supply the missing word in each saying:":
        "Supply the missing word in the saying:",
    "Name the part of the body referenced by each adjective:":
        "Name the part of the body referenced by the adjective:",
    "Name the type of angle that has each of the given measures:":
        "Name the type of angle that measures",
    "Complete each of the following sentences with its appropriate homophone:":
        "Complete this sentence with the right homophone:",
    "Complete each of the following compound sentences with the most appropriate "
    "coordinating conjunction:":
        "Complete this sentence with the right coordinating conjunction:",
    "Complete each of the following sentences with its appropriate preposition:":
        "Complete this sentence with the right preposition:",
    "Group the following Greek events according to the three major historical periods:":
        "Which of the three major Greek historical periods does this event belong to?",
    "State whether each of the following is a reptile, mammal, amphibian, fish, or bird:":
        "Is this a reptile, mammal, amphibian, fish or bird?",
    "Identify the following objects as being either a lever or an incline plane:":
        "Is this object a lever or an incline plane?",
    "Pluralize the following singular nouns:":
        "Pluralize this singular noun:",
    "State the term used to identify the offspring of a:":
        "State the term for the offspring of a",
    "If using a standard deck of 52 cards, what is the probability of retrieving each "
    "of the following?:":
        "From a standard deck of 52 cards, give the probability of drawing",
    "Calculate the number of diagonals that may be drawn in:":
        "Calculate the number of diagonals that may be drawn in",
    "Give the sum of the measures of all the interior angles in":
        "Give the sum of the measures of all the interior angles in",
    "State whether each of the following numbers is divisible by 3 and 5, but not 2:":
        "Is this number divisible by 3 and 5, but not 2?",
    "Find the slope and y-intercept of each equation:":
        "Find the slope and y-intercept of the equation:",
    "Determine the probability that a card selected at random from a deck of 52 cards is":
        "Determine the probability that a card selected at random from a deck of 52 "
        "cards is",
    "Identify the US state where each landmark is located:":
        "Identify the US state where this landmark is located:",
    "State the SI (System International) prefix for each of the following:":
        "State the SI (System International) prefix for",
    "If canine means dog-like and feline means cat-like, to which animals do the "
    "following adjectives refer?":
        "If canine means dog-like and feline means cat-like, to which animal does this "
        "adjective refer?",
    # "Identify the planet in our solar system: the largest planet in our solar
    # system" says it twice.
    "Identify the following planets in our solar system":
        "Identify the planet:",
    "State whether each of the following is thousands, millions, billions, or trillions "
    "of miles from the Earth:":
        "Is this thousands, millions, billions, or trillions of miles from the Earth?",
    "Define the following terms:":
        "Define the term:",
    "Classify each of the following animals as mammal, fish, amphibian, reptile or bird:":
        "Classify this animal as mammal, fish, amphibian, reptile or bird:",
    "Identify the following as transparent, translucent, or opaque:":
        "Identify this as transparent, translucent, or opaque:",
    "State the number of protons, neutrons and electrons in each of the following four "
    "neutral atoms:":
        "State the number of protons, neutrons and electrons in this neutral atom:",
    "Identify the following rocks as igneous (ig-nee-us), sedimentary, or metamorphic:":
        "Identify this rock as igneous (ig-nee-us), sedimentary, or metamorphic:",
    "State the following about the United Nations:":
        "State the following about the United Nations:",
    "Match each literary work with the language in which it was first published: "
    "Works:":
        "In which language was this literary work first published?",

    # The root-word sets are already singular -- one root, one definition, one
    # word -- so the lead is reused as written.
    "Supply the word described that incorporates the Latin root cred:":
        "Supply the word described that incorporates the Latin root cred:",
    "Supply the word described that incorporates the Latin roots ben/bene:":
        "Supply the word described that incorporates the Latin roots ben/bene:",
    "Supply the word described that incorporates the Latin root spect:":
        "Supply the word described that incorporates the Latin root spect:",
    "Supply the word described that incorporates the Latin root ped:":
        "Supply the word described that incorporates the Latin root ped:",
    "Supply the word described that incorporates the Latin root ject:":
        "Supply the word described that incorporates the Latin root ject:",
    "Supply the word described that incorporates the Greek root chron:":
        "Supply the word described that incorporates the Greek root chron:",
    "Supply the word described that incorporates the Greek root pan:":
        "Supply the word described that incorporates the Greek root pan:",
    "Supply the word described that incorporates the Greek root ant:":
        "Supply the word described that incorporates the Greek root ant:",
    "Supply the word described that incorporates the Greek root demo:":
        "Supply the word described that incorporates the Greek root demo:",
    "Supply the word described that incorporates the Greek root gram:":
        "Supply the word described that incorporates the Greek root gram:",

    # "A correct list will be in alphabetical order" is an instruction to the
    # whole list and means nothing on a card holding one word.
    "Supply the following words that derive from the Persian language. A correct list "
    "will be in alphabetical order and the first letter is given":
        "Supply the word that derives from the Persian language; its first letter is "
        "given.",
    "Supply the following words that derive from the Arabic language. A correct list "
    "will be in alphabetical order and the first letter is given":
        "Supply the word that derives from the Arabic language; its first letter is "
        "given.",
    "Supply the following words that derive from the Old Norse language. A correct list "
    "will be in alphabetical order and the first letter is given":
        "Supply the word that derives from the Old Norse language; its first letter is "
        "given.",
    "Supply the following words that derive from the Scots language. A correct list "
    "will be in alphabetical order and the first letter is given":
        "Supply the word that derives from the Scots language; its first letter is "
        "given.",

    # Kept whole -- the parts are not independent questions.
    # b) and c) both say "that number", meaning the one built in a).
    "Arrange the digits 8, 2, 3, 5, 9 to:": None,
    # Every constraint in the seating puzzle is buried in the last part.
    "Determine": None,
    # b), c) and d) all point back at the country named in a).
    "Identify the following:": None,
}

# Where fixing the lead is not enough because the parts themselves are written
# as fragments of a list. Full card fronts, one per part, in the key's order.
CARD_TEXT = {
    "Match the following Supreme Court cases with their outcomes": [
        "Which Supreme Court case ruled that states could not deny legal "
        "counsel to defendants?",
        "Which Supreme Court case ruled that public school segregation was "
        "unconstitutional?",
        "Which Supreme Court case ruled that those in police custody must be "
        "made aware of their rights?",
        "Which Supreme Court case ruled that evidence collected during a search "
        "is only admissible with a warrant signed by a judge?",
    ],
    "Name each city of the ancient world": [
        "Name the city of the ancient world whose central meeting place was the Agora.",
        "Name the city of the ancient world whose library was the largest in the world.",
        "Name the city of the ancient world whose \u201changing gardens\u201d were "
        "world famous.",
        "Name the city of the ancient world that was connected by its system of roads.",
        "Name the city of the ancient world that had its trade empire destroyed "
        "after 146 BC.",
        "Name the city of the ancient world that contains holy sites to three major "
        "religions.",
    ],
}

# A question's hint is written for the whole set, and on a single card it can
# be anything from perfect to useless to the answer key. Each split question's
# hint has been read against its own parts:
#
#   "keep" -- the hint states a rule the student still has to apply, and the
#             question already shows the words it names
#   "drop" -- it identifies the parts one by one
#   text   -- a replacement that works on every card
#
# Anything not listed falls back to the automatic rule in qCards(): drop the
# hint when it contains that card's own answer, keep it otherwise.
CARD_HINT = {
    # Rules. Naming acute/obtuse/straight or it's/its gives nothing away when
    # the question is "which of these is it".
    "Determine if the following sentences require \u201cit\u2019s\u201d": "keep",
    "Name the type of angle that has each of the given measures": "keep",
    "Calculate the number of diagonals that may be drawn in": "keep",
    "State whether each of the following numbers is divisible": "keep",
    "Identify the following as transparent, translucent, or opaque":
        "One lets light straight through, one scatters it, one stops it.",
    "Define and identify the objective complements":
        "The complement follows the direct object: if it renames the object it is a "
        "noun, if it describes it it is an adjective.",

    # One clue per part -- on a single card that clue is the answer.
    "Identify the following Revolutionary War battles": "drop",
    "State the SI (System International) prefix for each": "drop",

    # The alphabetical run and the first letter are already in the stem, and on a
    # single card that scaffold is the hint: the set-level version just listed
    # the letters again.
    "Supply the following words that derive from": "The first letter is in the "
    "question and the list runs alphabetically — think of the everyday English "
    "word that fits the definition.",


    "State the term that means: a) land completely surrounded":
        "Four coastal words. Picture how much water is touching the land.",
    "State the meaning of the following abbreviations":
        "Say the letters out loud \u2014 each stands for the first letter of the "
        "words in a phrase people use every day.",
    "Supply the missing word in each saying":
        "An old proverb. Say the whole line out loud and the missing word "
        "usually falls into place.",
    "Name the part of the body referenced by each adjective":
        "These are the Latin and Greek adjectives doctors still use, and the "
        "root almost always turns up in an everyday word.",
    "If canine means dog-like and feline means cat-like":
        "Each one is built on the Latin name for the animal. Say the root out "
        "loud and listen for it.",
    "Match each literary work with the language in which it was first published":
        "Think about where the author was writing, not where the story is set.",
    "Identify the following planets in our solar system":
        "\u201cMy Very Educated Mother Just Served Us Noodles\u201d \u2014 the "
        "first letter of each word is a planet, in order from the sun.",
}


# A matching question is the worst flashcard of the lot: six cemeteries, six
# states, and a single flip that asks the student to grade all six at once.
# Matching is what the Match board is for. On a card, each pair is its own
# question -- left item on the front, its partner on the back.
#
#   key   -> a distinctive run of the stem
#   value -> the front of one card, with {} where the left-hand item goes, or
#            None to keep the question whole
#
# Every one has been read against its own pairs, and the direction is always
# left to right: the stem's first list is the prompt, the second is the answer.
MATCH_CARD = {
    "Match each parent rock with what it becomes":
        "In the rock cycle, {} becomes which rock?",
    "Match each dictator to the country he once controlled":
        "Which country did {} once control?",
    "Match the symbiotic relationship with the correct definition":
        "What does {lc} mean, in a symbiotic relationship?",
    "Match the Supreme Court case to the part of the Constitution":
        "Which part of the Constitution justified the Court’s decision in {}?",
    "Match the Supreme Court case to the Bill of Rights amendment":
        "Which Bill of Rights amendment did {} serve to clarify?",
    "Match each former country name to its new name":
        "{} is known today by which country name?",
    "Match each ancient city to the current-day country":
        "In which present-day country would you find the ancient city of {}?",
    "Match each region conquered by the Roman Empire":
        "The Roman region of {} is in which present-day country?",
    "Match each river to the ancient city that emerged along it":
        "Which ancient city emerged along the {}?",
    "List the currencies used in each of the following countries":
        "Which currency is used in {}?",
    "Match each revolutionary invention to the current-day country":
        "{} — in which present-day country did it originate?",
    "Explain the meaning of the slang words":
        "What does the slang word “{}” mean?",
    "Match each of the following poets with his/her published titles":
        "Which work on the guide’s list was written by {}?",
    "Match each fictional character with his/her corresponding book title":
        "In which book does {} appear?",
    "Match these works of literature with the time period of their settings":
        "{} — in which time period are they set?",
    "Match the following literary terms to their correct definitions":
        "In literature, what does {} mean?",
    "Match each word with the country whose language it derives from":
        "The word “{}” comes from the language of which country?",
    "Match the National Park with the state in which it is located":
        "In which state is {} National Park?",
    "Match each American landmark with the state in which it is located":
        "In which state would you find {}?",
    "Match each National Cemetery with the state in which it is located":
        "In which state is {} National Cemetery?",
    "Match each National Military Park with the state in which it is located":
        "In which state is {} National Military Park?",
    "Match each presidential home with the state in which it is located":
        "In which state is {}?",
    "Match each of the following geometric figures with its number of sides":
        "How many sides does a {} have?",
    "Match each term with the subject of its study":
        "What does {lc} study?",
    "Match each word built on the Latin root “sub”":
        "What does “{}” mean?",
    "Match each word built on the Latin root “mal”":
        "What does “{}” mean?",
    "Match each word built on the Latin root “audi”":
        "What does “{}” mean?",
    "Match each of the following dystopian novels with its appropriate author":
        "Who wrote {}?",
    "Name the authors of the following works":
        "Who wrote {}?",
    "Identify what ion is found in the following substances":
        "Which ion is found in {lc}?",
    "Match each state with its correct capital":
        "What is the capital of {}?",
    "Identify the capital city of each of the following Western States":
        "What is the capital of {}?",
    "Match the following monetary systems and the country":
        "Which country uses the {}?",
    "Match the following Germans to what they are best known for":
        "What is {} best known for?",
    "Match each example with its figurative language device":
        "Which figurative language device is this: {}",

    # Deduction puzzles. Every pair is worked out from facts about the others,
    # so one pair on its own is not answerable -- these stay whole.
    "Jane, Jeff, Joe, and Jean each have a pet": None,
    "Mark, Mike, Mary, and Max each weigh different amounts": None,
}

# "a) foo", "a. foo" and -- in the Supreme Court outcomes question -- "a). foo".
PARTMARK = re.compile(r"(?:^|\s)[a-hA-H][.)]\.?\s")


def fill(tmpl, item):
    """{} takes the item as written; {lc} lowercases its first letter, for the
    templates that read it mid-sentence."""
    if "{lc}" in tmpl:
        return tmpl.replace("{lc}", item[:1].lower() + item[1:])
    return tmpl.format(item)


def match_cards(q, iv):
    """One card per pair, or None to leave a matching question whole."""
    pairs = iv.get("pairs", [])
    if len(pairs) < 2:
        return None
    for key, tmpl in MATCH_CARD.items():
        if key in q:
            if tmpl is None:
                return None               # reviewed, deliberately kept whole
            iv["cards"] = [fill(tmpl, left) for left, _ in pairs]
            return "cards"
    return clean(q[:70])                  # unreviewed -- reported, never split


# A hint written for a whole set names the parts one by one, so once the question
# is one card wide the automatic rule drops it and the card is left with nothing.
# These are written per item -- keyed by a fragment of the item, never by index,
# so reordering a list cannot slide them out of alignment. A question listed here
# must match every one of its rows or the whole entry is refused and reported.
CARD_ITEM_HINT_USED = set()

CARD_ITEM_HINT = {
    "Match each ancient city to the current-day country": [
        ("Alexandria", "The great port Alexander founded at the mouth of the Nile."),
        ("Antioch", "On the Orontes; today it is Antakya, just north of the Syrian "
         "border."),
        ("Athens", "It has kept its name, and it is still a capital."),
        ("Jaisalmer", "The golden fort city in the Thar desert of Rajasthan."),
        ("Rome", "The city on the Tiber still names its country."),
        ("Samarkand", "A Silk Road city in Central Asia — the modern country's name "
         "ends in -stan."),
        ("Tyre", "The Phoenician port on the eastern Mediterranean, in the country "
         "just north of Israel."),
    ],
    "Match each river to the ancient city": [
        ("Euphrates", "Its city was famous for terraced gardens."),
        ("Indus", "The Bronze Age city excavated in the Indus valley, in modern "
         "Pakistan."),
        ("Nile", "The Old Kingdom capital, near the Giza pyramids."),
        ("Tiber", "Seven hills and an empire."),
        ("Tigris", "The Assyrian capital, destroyed in 612 BCE."),
        ("Yangtze", "The packet pairs it with a city on the Yunnan plateau — see the "
         "review note."),
    ],
    "Identify the chemical element that": [
        ("melting point", "Light-bulb filaments are made of it; its symbol is W."),
        ("liquid state", "Named after a planet; its symbol is Hg."),
        ("bronze", "Pennies and electrical wiring; its symbol is Cu."),
    ],
    "Match each of the following poets": [
        ("Angelou", "Her title is the memoir of her own childhood."),
        ("Carroll", "The nonsense poem from Through the Looking-Glass."),
        ("Cummings", "The modernist who would not use capital letters; his title opens "
         "with a colour."),
        ("Dickinson", "The recluse of Amherst; her title makes a metaphor out of a "
         "bird."),
        ("Frost", "New England woods, and a warning that nothing lasts."),
        ("Whitman", "He wrote it for Lincoln, after the assassination."),
    ],
    "Greek root ant": [
        ("opposite meaning", "Its partner word is a synonym."),
        ("provides conflict", "The protagonist's rival."),
        ("undo harm", "What you take against a poison."),
        ("company of others", "Against society."),
        ("South Pole", "Opposite the Arctic."),
        ("strong feeling of dislike", "Against feeling — the opposite of sympathy."),
    ],
    "Match each word with the country whose language": [
        ("bangle", "A bracelet, from Hindi."),
        ("boondocks", "From the Tagalog word for mountain."),
        ("emoji", "E for picture, moji for character."),
        ("mammoth", "From a Siberian word for the tusked beast dug out of the "
         "permafrost."),
        ("slalom", "A skiing term — the packet files it under the Scandinavian "
         "country on the list."),
        ("yogurt", "The word arrived with the Ottomans."),
        ("zombie", "It came through voodoo in the Caribbean."),
    ],
    "Give the sum of the measures of all the interior angles": [
        ("rhombus", "Four sides, like any quadrilateral: (n−2) × 180."),
        ("hexagon", "Six sides: (n−2) × 180."),
        ("octagon", "Eight sides: (n−2) × 180."),
        ("scalene triangle", "Three sides — unequal sides change nothing."),
    ],
    "Latin root “sub”": [
        ("subcutaneous", "Cutaneous means of the skin."),
        ("substitution", "A player coming on for another in a game."),
        ("subpar", "Par is the standard in golf."),
        ("subconscious", "The part of your mind you are not aware of."),
    ],
    "Latin root “audi”": [
        ("audience", "The people in the seats."),
        ("audiologist", "-ologist is one who studies."),
        ("audible", "-ible means able to be."),
        ("audition", "What an actor does to be heard by a casting director."),
    ],
    "Group the following Greek events": [
        ("Draconian reforms", "Draco's brutal law code for Athens, in the 600s BCE — "
         "generations before the Persian wars."),
        ("Battle of Marathon", "The first Persian invasion, 490 BCE, at the height of "
         "the independent city-states."),
        ("Battle of Salamis", "The naval victory over Xerxes, 480 BCE."),
        ("Peloponnesian War", "Athens against Sparta, 431–404 BCE."),
        ("First Macedonian War", "Rome against Philip V — after Alexander's empire "
         "had broken into pieces."),
        ("Battle of the Hydaspes", "Alexander himself, fighting in India in 326 BCE."),
        ("First Punic War", "Rome against Carthage, 264–241 BCE. Roman, not Greek — "
         "date it against Alexander."),
    ],
    "Identify the following Revolutionary War battles": [
        ("New York", "A town on the Hudson. The victory that convinced France to "
         "join the war."),
        ("Massachusetts", "Fought in 1775 on Breed's Hill, above Charlestown — but "
         "named for the hill beside it."),
        ("Virginia", "A port on the Chesapeake, 1781, where Washington and the French "
         "fleet trapped an army."),
    ],
    "State the SI (System International) prefix": [
        ("one hundredth", "Think of the coin worth a hundredth of a dollar."),
        ("one thousandth", "A thousandth of a metre — the smallest mark on a ruler."),
        ("one thousand", "The prefix on the metric unit a bag of sugar is sold in."),
        ("one billionth", "Computers measure their speed in these seconds."),
        ("one millionth", "From the Greek for small."),
    ],
    "Complete each of the following compound sentences": [
        ("trumpet player", "The second clause contradicts the first."),
        ("friends were busy", "The second clause is the result of the first."),
        ("never traveled to Texas", "A second negative, following “never”."),
        ("littering her trash", "The second clause explains why."),
        ("likes to surf", "Nothing is being contrasted — the two clauses simply agree."),
    ],
    "appropriate preposition": [
        ("team captain", "To be on good terms with people is to get ____ with them."),
        ("great coach", "To take care of someone is to look ____ them."),
        ("throwing the football", "From one side of the room to the other."),
        ("final season standings", "Higher up the table than the other team."),
    ],
    "appropriate homophone": [
        ("Sally spoke", "The head of a school is a person; a rule is a principle."),
        ("Jason attempted", "Praise is spelled with an i; the one with an e completes "
         "something."),
        ("Daniel moved", "Rain and cold, not a question of choice."),
    ],
    "Match each state with its correct capital": [
        ("Idaho", "The city and the river share a name, from the French for wooded."),
        ("Illinois", "Lincoln's home town — not the state's biggest city."),
        ("Iowa", "French for “of the monks.”"),
        ("Indiana", "The state's name with a Greek ending for city."),
    ],
    "capital city of each of the following Western States": [
        ("Oregon", "It shares its name with the Massachusetts town of the witch trials."),
        ("New Mexico", "Spanish for “holy faith.”"),
        ("Texas", "Named for Stephen F., the empresario who brought the first American "
         "settlers."),
        ("California", "Spanish for “holy sacrament.”"),
        ("Idaho", "The city and the river share a name, from the French for wooded."),
    ],
    "Match the following monetary systems": [
        ("Euro", "The country whose old currency was the mark, and which anchors the "
         "single currency."),
        ("dollar", "Its dollar is the world's reserve currency."),
        ("rupee", "The most populous country in South Asia."),
        ("yen", "An island nation in East Asia."),
        ("peso", "The country directly south of the United States."),
    ],
    "State the term used to identify the offspring of a": [
        ("bird", "It has just left the nest."),
        ("deer", "Bambi."),
        ("seal", "The same word as a young dog."),
        ("whale", "The same word as a young cow."),
        ("rat", "The same word as a young seal."),
        ("goat", "The same word an adult might call a child."),
        ("kangaroo", "It rides in the pouch."),
    ],
}


def card_rows(iv):
    """The left-hand values, in the order the flashcards deal them."""
    if iv["t"] == "parts":
        return list(iv.get("prompts") or [])
    if iv["t"] == "cat":
        return [x[0] for x in iv.get("items") or []]
    if iv["t"] == "match":
        return [x[0] for x in iv.get("pairs") or []]
    return []


def _squash(t):
    return re.sub(r"[^a-z0-9]+", "", str(t).lower())


def card_answers(iv):
    """The right-hand values, in the order the flashcards deal them."""
    if iv["t"] == "parts":
        return list(iv.get("answers") or [])
    if iv["t"] == "cat":
        return [x[1] for x in iv.get("items") or []]
    if iv["t"] == "match":
        return [x[1] for x in iv.get("pairs") or []]
    return []


def item_hints(q, iv):
    """Attach a per-card hint list, or leave the question alone."""
    for key, table in CARD_ITEM_HINT.items():
        if key not in q:
            continue
        rows = card_rows(iv)
        if not rows:
            return None
        out = []
        for row in rows:
            hits = [(frag, h) for frag, h in table if _norm(frag) in _norm(row)]
            # "one thousandth" contains "one thousand": the longer fragment is
            # the one that was written for this row.
            if len(hits) > 1:
                longest = max(len(f) for f, _ in hits)
                hits = [x for x in hits if len(x[0]) == longest]
            if len(hits) != 1:
                return "%s -- %r matches %d hints" % (key[:40], row[:40], len(hits))
            out.append(hits[0][1])
        answers = card_answers(iv)
        for row, hint, ans in zip(rows, out, answers):
            if ans and _squash(ans) in _squash(hint):
                return "%s -- hint for %r contains its own answer" % (key[:40], row[:30])
        iv["hints"] = out
        CARD_ITEM_HINT_USED.add(key)
        return None
    return None


def card_plan(q, iv):
    """Attach the reviewed flashcard wording, or leave the question whole."""
    if iv["t"] == "match":
        return match_cards(q, iv)
    rows = (len(iv.get("prompts", [])) if iv["t"] == "parts"
            else len(iv.get("items", [])) if iv["t"] == "cat" else 0)
    if rows < 2:
        return None
    m = PARTMARK.search(q)
    if m:
        lead = clean(q[:m.start()])
    elif ":" in q:
        # The sentence-completion questions carve into rows without lettering
        # them, so the lead is simply whatever introduces the colon.
        lead = clean(q.split(":", 1)[0]) + ":"
    else:
        return None
    for key, hint in CARD_HINT.items():
        if key in q:
            iv["chint"] = hint
            break
    for key, cards in CARD_TEXT.items():
        if key in q:
            if len(cards) != rows:
                raise AssertionError("CARD_TEXT count %d != %d parts for %r"
                                     % (len(cards), rows, key))
            iv["cards"] = cards
            return "cards"
    if lead not in CARD_LEAD:
        return lead                       # unreviewed -- reported, never split
    new = CARD_LEAD[lead]
    if new is None:
        return None                       # reviewed, deliberately kept whole
    iv["lead"] = new
    return "lead"


# ------------------------------------------------- reviewed per-question fixes

# Three keys put text after the last lettered part, so the carve ran past the
# end of the question and into the setup. The stem is still shown above the
# widget, so nothing is lost by trimming these to the question they ask.
PROMPT_FIX = {
    "Determine a) who sits in the front seat": [
        "who sits in the front seat",
        "who sits in the second seat",
        "who sits in the last seat",
    ],
    "Match the following Supreme Court cases with their outcomes": [
        "Ruled that states could not deny legal counsel to defendants",
        "Ruled that public school segregation was unconstitutional",
        "Ruled that those in police custody must be made aware of their rights",
        "Ruled that evidence collected by police during a search is only "
        "admissible with a warrant signed by a judge",
    ],
    "Determine the probability that a card selected at random": [
        "the suit of hearts",
        "a face card",
        "the number ten",
        "a suit of club or spade",
    ],
}

# Column headings, where the stem gives the two lists no labels of its own and
# the board would otherwise read "Term | Match".
MATCH_COLS = {
    "Match each parent rock with what it becomes": ("Parent rock", "Becomes"),
    "List the currencies used in each of the following countries": ("Countries", "Currency"),
    "Explain the meaning of the slang words": ("Slang", "Meaning"),
    "Jane, Jeff, Joe, and Jean each have a pet": ("Person", "Pet"),
    "Mark, Mike, Mary, and Max each weigh different amounts": ("Person", "Weight"),
    "Match each of the following geometric figures with its number of sides":
        ("Figure", "Sides"),
    "Match each term with the subject of its study": ("Terms", "Subject of study"),
    "Match each word built on the Latin root": ("Words", "Definitions"),
    "Match each of the following dystopian novels": ("Novels", "Authors"),
    "Name the authors of the following works": ("Works", "Authors"),
    "Identify what ion is found in the following substances": ("Substances", "Ion"),
    "Match each state with its correct capital": ("States", "Capitals"),
    "Identify the capital city of each of the following Western States":
        ("States", "Capitals"),
    "Match the following monetary systems": ("Monetary system", "Countries"),
    "Match the following Germans to what they are best known for":
        ("Germans", "Specialty"),
    "Match these works of literature with the time period": ("Works", "Setting"),
}


def apply_fixes(q, iv):
    """Reviewed overrides, applied after a parser has produced its structure."""
    if iv["t"] == "parts":
        for key, prompts in PROMPT_FIX.items():
            if key in q and len(prompts) == len(iv["prompts"]):
                iv["prompts"] = list(prompts)
                break
    if iv["t"] == "match":
        iv["pairs"] = [list(p) for p in expand_rights(q, [tuple(p) for p in iv["pairs"]])]
        for key, (l, r) in MATCH_COLS.items():
            if key in q:
                iv["l"], iv["r"] = l, r
                break
    return iv


# ------------------------------------------------- parallel lists in the stem

BLANK = re.compile(r"_{2,}")


def blank_fill(item, answers):
    """'The Ant and the ____' against 'The Ant and the Grasshopper' -> the word.

    A fill-in-the-blank list gives its answers as completed items, so the card
    can show the missing word beside its blank instead of repeating the title.
    """
    m = BLANK.search(item)
    if not m:
        return None
    head, tail = _norm(item[:m.start()]), _norm(item[m.end():])
    for a in answers:
        na = _norm(a)
        if head and not na.startswith(head):
            continue
        if tail and not na.endswith(tail):
            continue
        cut = a
        if head:
            cut = cut[len(cut) - len(cut.lstrip()):]
        # walk the original answer, not the normalised one, so casing survives
        raw = a.strip()
        i = len(item[:m.start()].strip(" \u201c\u201d\"'"))
        j = len(raw) - len(item[m.end():].strip(" \u201c\u201d\"'"))
        got = clean(raw[i:j]).strip(" \u201c\u201d\"'\u2019s")
        if got:
            return got
    return None


# A two-list question is better as one card per blank -- but only where the
# wording and the hints have been written for a single item. The hints are keyed
# by a fragment of the item, not by index, so reordering the list cannot slide
# them out of alignment. A stem listed here with an item that matches nothing
# keeps the two-column layout instead of shipping a card with no hint.
LIST_CARDS = {
    "Supply the animal missing": {
        "lead": "Supply the animal missing from this fable title",
        "hints": {
            "The Ant and the": "One insect stores food all summer; the other "
                               "fiddles and sings, then goes hungry in winter.",
            "The Boy Who Cried": "He raised a false alarm about the predator "
                                 "stalking his flock — until it really came.",
            "The Lion and the": "The tiny animal he spared later gnawed him "
                                "free from a hunter's net.",
            "The Scorpion and the": "The scorpion asks the good swimmer for a "
                                    "ride across the river, then stings it "
                                    "mid-stream.",
            "The Tortoise and the": "The fast one is so far ahead that it stops "
                                    "for a nap, and slow and steady wins.",
            "The Wolf in": "He walks among the flock he preys on, wearing one "
                           "of them.",
        },
    },
}


def list_cards(q, litems):
    """The authored per-item wording for a two-list stem, or None."""
    for key, spec in LIST_CARDS.items():
        if key not in q:
            continue
        hints = []
        for it in litems:
            got = [h for k, h in spec["hints"].items() if k in it]
            if len(got) != 1:
                return None
            hints.append(got[0])
        return spec["lead"], hints
    return None


def stem_lists(q, a):
    """Two labelled lists in a stem -> what a flashcard should lay out.

    Only for the questions no parser claimed. The twenty matching questions
    that do parse are already dealt out one pair per card, which is better than
    any amount of column formatting.
    """
    lists = labelled_lists(q)
    if len(lists) != 2:
        return None
    (llab, litems), (rlab, ritems) = lists
    llab, rlab = tidy_label(llab, "Items"), tidy_label(rlab, "Options")
    litems = [clean(x) for x in litems if clean(x)]
    ritems = [clean(x) for x in ritems if clean(x)]
    if not (2 <= len(litems) <= 12) or not (2 <= len(ritems) <= 14):
        return None
    out = {"lead": clean(q[:q.index(lists[0][0])]).rstrip(":"),
           "l": llab, "litems": litems, "r": rlab, "ritems": ritems}
    answers = [clean(x) for x in split_items(a) if clean(x)]
    fills = [blank_fill(x, answers) for x in litems]
    if all(fills) and len(set(fills)) == len(fills):
        out["fills"] = fills
    elif len(answers) == len(litems):
        out["fills"] = answers
    if out.get("fills"):
        got = list_cards(q, litems)
        if got:
            out["clead"], out["hints"] = got
    return out


# --------------------------------------------- a fill-in that is really a board

# Column headings for the questions that convert. A board with "Clue | Answer"
# over it reads like a form; these are read off the question itself. Anything
# not listed keeps the generic pair, which is why the conversion still works
# when a question is added.
PARTS_COLS = {
    "Identify the following Revolutionary War battles": ("Description", "Battle"),
    "Name these early explorers of the New World": ("Description", "Explorer"),
    "Identify the scientific instruments based on the following descriptions":
        ("What it does", "Instrument"),
    "Identify the chemical element that": ("Property", "Element"),
    "State the meaning of the following abbreviations": ("Abbreviation", "Meaning"),
    "State the title of the following Charles Dickens novels": ("Opening line", "Novel"),
    "State the term that means": ("Meaning", "Term"),
    "Supply the missing word in each saying": ("Saying", "Missing word"),
    "State the SI (System International) prefix": ("Quantity", "Prefix"),
    "Identify the US state where each landmark is located": ("Landmark", "State"),
    "Calculate the number of diagonals that may be drawn in": ("Figure", "Diagonals"),
    "Define the following terms": ("Term", "Definition"),
    "State the number of protons, neutrons and electrons": ("Atom", "Counts"),
    "State the following about the United Nations": ("Question", "Answer"),
    "State whether each of the following is thousands, millions, billions":
        ("Object", "Distance"),
    "Identify the following: a) the country that hosted the 2008 Summer Olympics":
        ("Question", "Answer"),
    "Find the slope and y-intercept of each equation": ("Equation", "Slope and intercept"),
    "Supply the word described that incorporates": ("Definition", "Word"),
    "Supply the following words that derive from": ("Definition", "Word"),
    "Match the following Supreme Court cases with their outcomes": ("Outcome", "Case"),
    "Name each city of the ancient world": ("Description", "City"),
    "Identify the following planets in our solar system": ("Description", "Planet"),
    "Identify the following as transparent, translucent, or opaque": ("Description", "Type"),
    "Determine a) who sits in the front seat": ("Question", "Person"),
    "Define and identify the objective complements": ("Sentence", "Complement"),
}

# Questions that stay typed. The objective-complement board would be four
# right-hand tiles reading "= noun" and one reading "= adjective", which asks
# the student to match on the half of the answer the question is not about.
PARTS_KEEP = (
    "Define and identify the objective complements",
)

TRANSFORM = ("Pluralize", "Convert the adjective", "Say and spell")
SCAFFOLD = re.compile(r"\s*\([a-z]_{2,}\)")


def parts_to_match(q, iv):
    """parts -> match, where the answers are short, distinct names.

    A fill-in with six long descriptions puts each description on the line the
    student types into, which reads badly and grades nothing a board would not.
    Matching is refused where the answer is a transformation of its own prompt
    (axis to axes) -- there the point is producing the word, not recognising it.
    """
    if iv["t"] != "parts":
        return None
    prompts, answers = iv.get("prompts") or [], iv.get("answers") or []
    if not 3 <= len(prompts) <= 8 or len(prompts) != len(answers):
        return None
    if any(k in q for k in TRANSFORM) or any(k in q for k in PARTS_KEEP):
        return None
    if len({a.lower() for a in answers}) != len(answers):
        return None
    # Arithmetic stays typed. On a board the four interior-angle sums can be
    # ranked by size and the probabilities eliminated against each other, which
    # is not the skill the question is testing.
    if sum(1 for a in answers if re.match(r"^[\d¼-¾]", a)) * 2 >= len(answers):
        return None
    for p, a in zip(prompts, answers):
        if len(a) > 26 or len(a.split()) > 3 or not a:
            return None
        if len(p) < 6:                        # "1125" types fine as it is
            return None
        if _norm(a) in _norm(p):              # the answer is sitting in its prompt
            return None
        if _norm(a)[:4] and _norm(p).startswith(_norm(a)[:4]):
            return None                       # a transformation of the prompt
    cols = ("Clue", "Answer")
    for key, val in PARTS_COLS.items():
        if key in q:
            cols = val
            break
    # "a hired or professional killer (a____)" tells you which tile it pairs
    # with before you have thought about it. The scaffold stays on the flashcard,
    # where the answer is not on screen to match against.
    lefts = [SCAFFOLD.sub("", p).strip() for p in prompts]
    pairs = expand_rights(q, list(zip(lefts, answers)))
    out = {"t": "match", "l": cols[0], "r": cols[1],
           "pairs": [[p, a] for p, a in pairs]}
    for k in ("lead", "cards", "chint", "hints"):
        if k in iv:
            out[k] = iv[k]
    # The flashcard fronts are built from the prompts as printed, scaffold and
    # all -- on a card the first letter is the hint, not a giveaway.
    if "cards" not in out and out.get("lead") and any(l != p for l, p in zip(lefts, prompts)):
        out["cards"] = ["%s %s" % (out["lead"], p) for p in prompts]
    return out


# ------------------------------------------------- the stem the widget needs

def shown_values(iv):
    """Everything the widget puts on screen before the student answers.

    A tile and a line of stem text saying the same thing is the same list
    twice, so the stem can drop it -- but only where the widget really shows
    it. `set` shows nothing (typing the members is the whole question) and
    `parts` shows its prompts but hides its answers.
    """
    t = iv["t"]
    if t == "match":
        return [x for p in iv["pairs"] for x in p]
    if t == "cat":
        return list(iv["cats"]) + [x[0] for x in iv["items"]]
    if t == "order":
        return list(iv["items"])
    if t in ("pick", "some"):
        return list(iv["options"])
    if t == "parts":
        return list(iv["prompts"])
    return []


def _words(t):
    """Normalised words, singularised, for comparing a stem item to a tile."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in _norm(t).split()}


def shows_item(item, tiles):
    """Is this stem item the thing one of the tiles is showing?

    Not equality: a key abbreviates ("Three Musketeers" for "The Three
    Musketeers", "equal protection" for "equal protection clause") and a stem
    pads ("Archaic Period" for the "Archaic" bucket). Either may be the shorter,
    so the test is subset in whichever direction -- but every word of the
    shorter one has to be there, which is what keeps a decoy the widget does not
    offer from being trimmed away.
    """
    it = _words(item)
    if not it:
        return False
    for t in tiles:
        if it <= t:                     # the key spells it out more fully
            return True
        # The tile may be the shorter of the two -- "Archaic" for the stem's
        # "Archaic Period" -- but only just. A tile holding one word of a whole
        # sentence does not show that sentence, and cutting on that basis threw
        # away "State your answer as a reduced fraction" and the slang words'
        # own example sentences.
        if t <= it and len(it) - len(t) <= 2:
            return True
    return False


def stem_items(text):
    """The items of one labelled list, however the packet punctuated them."""
    # A lettered list is lettered however it is punctuated: "A. A Night Divided,
    # The Pigman B. Across Five Aprils, ..." has commas inside its items, so the
    # markers have to win over the separators -- and both styles are sliced
    # together, or "...signed by a judge. 1. Brown v. Board of Education..."
    # leaves the whole numbered list inside the lettered list's last item.
    ms = []
    for rx in (NUM_ITEM, LETTER_ANY):
        got = list(rx.finditer(text))
        if len(got) >= 2:
            ms += got
    ms.sort(key=lambda m: m.start())
    if len(ms) >= 2:
        items = [clean(text[m.end():(ms[i + 1].start() if i + 1 < len(ms) else len(text))])
                 for i, m in enumerate(ms)]
    else:
        items = [clean(x) for x in split_items(text)]
    items = [x for x in items if x]
    if len(items) < 2:
        # Five quoted sentences run together with no separator at all.
        quoted = [clean(x) for x in QUOTED.findall(text)]
        if len(quoted) >= 2:
            items = [x for x in quoted if x]
    return items


def trim_tail(q, tiles):
    """'...in chronological order: California; Georgia; ...' -> drop the list.

    The labelled-list form ("Areas: ... Countries: ...") is handled above; this
    is the commoner shape, where the stem simply ends in the list itself. It is
    only cut when the tiles are showing every one of its items.
    """
    out, cut_any = q, False
    # Three passes, because one stem gives its two lists as "...for: <names> /
    # Specialty: <jobs>" and another as "MONETARY SYSTEM = ...; COUNTRIES = ...".
    # Each pass takes the last list off the end.
    for _ in range(3):
        # (where the kept text ends, where the list starts)
        cuts = []
        c = out.rfind(":")
        if c >= 12:
            cuts.append((c, c + 1))
        m = LETTER_ANY.search(out)              # "...is given. a. a hired killer"
        if m and m.start() >= 12:
            cuts.append((m.start(), m.start()))
        for m in LABEL_EQ.finditer(out):        # "MONETARY SYSTEM = Euro, ..."
            if m.start(1) >= 12:
                cuts.append((m.start(1), m.end()))
        for head, start in sorted(cuts, reverse=True):
            items = [x.strip(" /") for x in stem_items(out[start:])]
            items = [x for x in items if x]
            # Every item has to be on a tile. That is also what protects the
            # seating puzzle, whose constraints trail after its last lettered
            # part: the final "item" carries them, matches nothing, and the cut
            # is refused rather than quietly deleting the puzzle.
            if len(items) >= 3 and all(shows_item(x, tiles) for x in items):
                out, cut_any = clean(out[:head]).rstrip(" :;,/.="), True
                break
        else:
            break
    if not cut_any or len(out) < 15:
        return None
    return out


def trim_stem(q, iv):
    """The stem with every list the widget already shows taken out of it."""
    hits = list(LIST_LABEL.finditer(q))
    if len(hits) < 2:
        tiles = [_words(x) for x in shown_values(iv)]
        return trim_tail(q, [x for x in tiles if x]) if tiles else None
    tiles = [_words(x) for x in shown_values(iv)]
    tiles = [x for x in tiles if x]
    if not tiles:
        return None
    head = q[:label_start(hits[0])]
    keep, dropped = [], False
    for k, m in enumerate(hits):
        end = label_start(hits[k + 1]) if k + 1 < len(hits) else len(q)
        seg = q[label_start(m):end]
        items = stem_items(q[m.end():end])
        if len(items) >= 2 and all(shows_item(x, tiles) for x in items):
            dropped = True
        else:
            keep.append(seg)
    if not dropped:
        return None
    out = clean(head + " ".join(keep)).rstrip(" :;,")
    return out if len(out) >= 15 else None


# ------------------------------------------- the typed set, offered as a board

# Keyed by a distinctive stretch of the stem, never by index, because `Q` gets
# reordered. Each entry is (rewritten stem, distractors[, replacement items]).
# The third element is only for the question whose key writes its own items
# inconsistently -- capitalisation is a tell, so the tiles are levelled.
SET_PICK = {
    "four bases that make up the ladder": (
        "Which of these are the four bases that make up the ladder of"
        " deoxyribonucleic acid (DNA)?",
        ["uracil", "ribose", "deoxyribose", "phosphate"]),
    "ten systems of the human body": (
        "Which of these are the ten systems of the human body?",
        # Not "immune" and not "integumentary": both are real body systems that
        # the packet's list of ten happens to leave out, and a tile marked wrong
        # for naming one would be teaching a falsehood. These four are regions
        # and processes -- not systems at all.
        ["Cranial", "Thoracic", "Metabolic", "Cellular"]),
    "eight parts of speech": (
        "Which of these are the eight parts of speech?",
        ["Articles", "Gerunds", "Participles", "Infinitives"]),
    "Colorado River flows through or borders": (
        "Which five US states does the Colorado River flow through or border?",
        # Texas has a Colorado River of its own; New Mexico and Wyoming are in
        # the basin but the river itself never reaches them.
        ["New Mexico", "Wyoming", "Texas", "Idaho"]),
    "share a border with Mississippi": (
        "Which of these US states share a border with Mississippi?",
        ["Missouri", "Georgia", "Florida", "Texas"]),
    "four original New England colonies": (
        "Which of these were the four original New England colonies?",
        # Vermont is New England now and was no colony then. Maine is left out
        # of the pool entirely: the packet accepts it for the fourth, so it can
        # be neither a right tile nor a wrong one.
        ["New York", "Vermont", "New Jersey", "Pennsylvania"]),
    "share a border with Ohio": (
        "Which of these US states share a border with Ohio?",
        ["Illinois", "New York", "Virginia", "Wisconsin"]),
    "five most common chemical elements": (
        "Which of these are the five most common chemical elements that make up"
        " living tissue?",
        ["Calcium, Ca", "Sulfur, S", "Sodium, Na", "Iron, Fe"],
        ["Oxygen, O", "Hydrogen, H", "Carbon, C", "Nitrogen, N",
         "Phosphorus, P"]),
}
SET_PICK_USED = set()


def set_to_some(q, iv):
    """A typed set becomes 'tick every one that belongs', or stays typed."""
    if iv["t"] != "set":
        return None
    key = next((k for k in SET_PICK if k.lower() in q.lower()), None)
    if not key:
        return None
    SET_PICK_USED.add(key)
    ent = SET_PICK[key]
    stem, wrong = ent[0], ent[1]
    items = ent[2] if len(ent) > 2 else iv["items"]
    assert len(items) == len(iv["items"]), key
    low = {x.lower() for x in items}
    assert not (low & {x.lower() for x in wrong}),         "a distractor is also a correct answer: %s" % key
    return {"t": "some", "options": items + wrong, "correct": items,
            "stem": stem}


# ---------------------------------------------------------------- classifier

PARSERS = (as_match, as_match_lettered, as_order, as_parts, as_pick, as_cat,
           as_group, as_blank_choice, as_bank_blank, as_some, as_positional,
           as_set, as_pairs_typed)
# Priority matters when a question parses more than one way. Ordering beats
# matching (same items either way, but order is what is being tested), sorting
# beats free-text parts, and the typed set is the last resort before free.
ORDERED = ("order", "match", "cat", "some", "pick", "parts", "set")


def classify(q, a):
    """First parser that produces something usable wins, in a fixed priority."""
    hand = override(q)
    if hand:
        return hand
    found = {}
    for fn in PARSERS:
        # No blanket except here: a NameError in a parser silently turned a
        # whole interaction type off once already, and the only symptom was a
        # lower count in the coverage report.
        got = fn(q, a)
        if got:
            found[got["t"]] = got
    for t in ORDERED:
        if t in found:
            return apply_fixes(q, found[t])
    return None


CI = "--ci" in sys.argv


def note(msg):
    """A GitHub annotation on a publish from the sheet; a plain line locally."""
    print(("::warning::" if CI else "NOTE: ") + msg)


def guard(bad, local_msg, ci_msg, out):
    """Assert locally. On a publish, drop the offending widgets and say so."""
    if not bad:
        return
    if not CI:
        raise AssertionError(local_msg % bad)
    for i in bad:
        out.pop(i, None)
        note(ci_msg % ("q%d" % i))


def main():
    recs = json.load(open("build/qbank.json", encoding="utf-8"))
    sc = [r for r in recs if r["sc"]]
    out, counts = {}, {}
    unreviewed, hint_fail = [], []
    split = 0
    for r in sc:
        iv = classify(r["q"], r["a"])
        t = iv["t"] if iv else "free"
        counts[t] = counts.get(t, 0) + 1
        if iv:
            plan = card_plan(r["q"], iv)
            bad = item_hints(r["q"], iv)
            if bad:
                hint_fail.append(bad)
            if plan in ("lead", "cards"):
                split += 1
            elif plan:
                unreviewed.append((r["i"], plan))
            out[r["i"]] = iv
    boards = 0
    for i, iv in list(out.items()):
        got = parts_to_match(next(r["q"] for r in sc if r["i"] == i), iv)
        if got:
            out[i] = got
            boards += 1
            counts["parts"] -= 1
            counts["match"] = counts.get("match", 0) + 1
    picks = 0
    for i, iv in list(out.items()):
        got = set_to_some(next(r["q"] for r in sc if r["i"] == i), iv)
        if got:
            out[i] = got
            picks += 1
            counts["set"] -= 1
            counts["some"] = counts.get("some", 0) + 1
    print("fill-ins turned into boards: %d" % boards)
    print("typed sets turned into boards: %d" % picks)
    left = [i for i, v in out.items() if v["t"] == "set"]
    guard(left, "typed sets with no SET_PICK entry: %s",
          "Questions %s is a list question with no wrong answers written for its "
          "board yet, so it shows as reveal-the-answer. Ask Mario to add them.", out)
    idlep = [k for k in SET_PICK if k not in SET_PICK_USED]
    if idlep and not CI:
        raise AssertionError("SET_PICK entries that matched no question: %s" % idlep)
    for k in idlep:
        note('The list board written for "%s" no longer matches a question -- its '
             "wording changed. Ask Mario to update it." % k)
    print("self-check questions:", len(sc))
    for t in sorted(counts, key=lambda k: -counts[k]):
        print("  %-6s %3d" % (t, counts[t]))
    print("interactive: %d of %d" % (len(out), len(sc)))
    print("flashcards split into parts: %d" % split)
    dup = [i for i, v in out.items() if v["t"] == "match"
           and len({r.lower() for _, r in v["pairs"]}) != len(v["pairs"])]
    guard(dup, "matching boards with repeated right-hand tiles: %s",
          "Questions %s would make a matching board with the same answer twice, "
          "which can't be solved, so it shows as reveal-the-answer instead.", out)
    print("per-card hint sets: %d" % sum(1 for v in out.values() if v.get("hints")))
    idle = [k for k in CARD_ITEM_HINT if k not in CARD_ITEM_HINT_USED]
    if idle:
        print("CARD_ITEM_HINT entries that matched no question:")
        for k in idle:
            print("  " + k)
    if hint_fail:
        print("CARD_ITEM_HINT no longer matches its question:")
        for x in hint_fail:
            print("  " + x)
        if CI:
            note("%d flashcard hint set%s no longer match%s its question's wording, so "
                 "those cards show without per-card hints. Ask Mario to update them."
                 % (len(hint_fail), "" if len(hint_fail) == 1 else "s",
                    "es" if len(hint_fail) == 1 else ""))
    if unreviewed:
        print("UNREVIEWED leads (kept whole -- add them to CARD_LEAD):")
        for i, lead in unreviewed:
            print("  [%d] %s" % (i, lead))
    for r in sc:
        iv = out.get(r["i"])
        if iv:
            got = trim_stem(r["q"], iv)
            if got:
                if iv["t"] == "parts" and not got.endswith("?"):
                    got += ":"
                iv["stem"] = got
    print("stems trimmed: %d" % sum(1 for v in out.values() if v.get("stem")))
    lists = {}
    for r in sc:
        if r["i"] in out:
            continue
        got = stem_lists(r["q"], r["a"])
        if got:
            lists[r["i"]] = got
    print("stem list layouts: %d" % len(lists))
    if "--emit" in sys.argv:
        json.dump(out, open("build/interactions.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        json.dump(lists, open("build/qlists.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("wrote build/interactions.json and build/qlists.json")
    if "--show" in sys.argv:
        want = sys.argv[sys.argv.index("--show") + 1]
        for r in sc:
            iv = classify(r["q"], r["a"])
            t = iv["t"] if iv else "free"
            if t == want:
                print("\n--- [%s] %s" % (t, r["q"][:150]))
                print("    A: %s" % r["a"][:150])
                if iv:
                    print("    IV: %s" % json.dumps(iv, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
