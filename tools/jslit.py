# -*- coding: utf-8 -*-
"""Read and write the JavaScript data literals in mal.html.

The content tables in mal.html are hand-written JS: bare object keys, trailing
commas, /* comments */ between entries, \\u escapes. This reads exactly that
subset -- objects, arrays, strings, numbers, true/false/null -- and refuses
anything else, so an expression where data was expected is an error rather
than a silent guess.

`emit()` writes values back in the house style the other tools parse
(tools/scdump.py and tools/reference.py match on `{s:"SS",c:"...",...}` and
`{d:"...",g:"...",r:"..."}`): bare keys, double-quoted strings, no spaces.
"""
import json
import re

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NUM = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
ESC = {'"': '"', "'": "'", "\\": "\\", "/": "/", "b": "\b", "f": "\f",
       "n": "\n", "r": "\r", "t": "\t", "v": "\v", "0": "\0"}


class LitError(ValueError):
    pass


def _ws(s, i):
    """Skip whitespace and comments."""
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j < 0:
                raise LitError("unclosed comment at %d" % i)
            i = j + 2
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
        else:
            break
    return i


def _string(s, i):
    q = s[i]
    i += 1
    out = []
    n = len(s)
    while i < n:
        c = s[i]
        if c == q:
            return "".join(out), i + 1
        if c == "\\":
            e = s[i + 1]
            if e == "u":
                if s[i + 2] == "{":
                    j = s.index("}", i)
                    out.append(chr(int(s[i + 3:j], 16)))
                    i = j + 1
                    continue
                cp = int(s[i + 2:i + 6], 16)
                i += 6
                # a surrogate pair written as two escapes
                if 0xD800 <= cp < 0xDC00 and s.startswith("\\u", i):
                    lo = int(s[i + 2:i + 6], 16)
                    if 0xDC00 <= lo < 0xE000:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        i += 6
                out.append(chr(cp))
                continue
            if e == "x":
                out.append(chr(int(s[i + 2:i + 4], 16)))
                i += 4
                continue
            if e == "\n":
                i += 2
                continue
            out.append(ESC.get(e, e))
            i += 2
            continue
        if c == "\n":
            raise LitError("newline inside string at %d" % i)
        out.append(c)
        i += 1
    raise LitError("unclosed string")


def parse_at(s, i):
    """Parse one literal starting at s[i]. Returns (value, index after it)."""
    i = _ws(s, i)
    c = s[i]
    if c == "{":
        obj = {}
        i = _ws(s, i + 1)
        while s[i] != "}":
            if s[i] in "\"'":
                key, i = _string(s, i)
            else:
                m = IDENT.match(s, i) or NUM.match(s, i)
                if not m:
                    raise LitError("bad key at %d: %r" % (i, s[i:i + 30]))
                key, i = m.group(0), m.end()
            i = _ws(s, i)
            if s[i] != ":":
                raise LitError("expected ':' at %d: %r" % (i, s[i:i + 30]))
            val, i = parse_at(s, i + 1)
            obj[key] = val
            i = _ws(s, i)
            if s[i] == ",":
                i = _ws(s, i + 1)
            elif s[i] != "}":
                raise LitError("expected ',' or '}' at %d: %r" % (i, s[i:i + 30]))
        return obj, i + 1
    if c == "[":
        arr = []
        i = _ws(s, i + 1)
        while s[i] != "]":
            val, i = parse_at(s, i)
            arr.append(val)
            i = _ws(s, i)
            if s[i] == ",":
                i = _ws(s, i + 1)
            elif s[i] != "]":
                raise LitError("expected ',' or ']' at %d: %r" % (i, s[i:i + 30]))
        return arr, i + 1
    if c in "\"'":
        return _string(s, i)
    for word, val in (("true", True), ("false", False), ("null", None)):
        if s.startswith(word, i) and not IDENT.match(s, i + len(word)):
            return val, i + len(word)
    m = NUM.match(s, i)
    if m:
        t = m.group(0)
        return (float(t) if any(ch in t for ch in ".eE") else int(t)), m.end()
    raise LitError("not a literal at %d: %r" % (i, s[i:i + 40]))


def skip_expr(s, i, stops=",}]"):
    """Skip any JS expression up to a top-level stop character. String-,
    comment- and bracket-aware; returns the index of the stop character."""
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            _, i = _string(s, i)
            continue
        if c == "`":
            j = i + 1
            while s[j] != "`":
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if s.startswith("/*", i) or s.startswith("//", i):
            i = _ws(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c in stops and depth == 0:
            return i
        i += 1
    raise LitError("expression runs off the end")


def const_span(s, name):
    """(start, end) of the literal assigned by `const NAME=...;`."""
    m = list(re.finditer(r"^const %s=" % re.escape(name), s, re.M))
    if len(m) != 1:
        raise LitError("const %s found %d times" % (name, len(m)))
    a = m[0].end()
    b = skip_expr(s, a, stops=";")
    return a, b


def read_const(s, name):
    a, b = const_span(s, name)
    val, end = parse_at(s, a)
    if _ws(s, end) != b:
        raise LitError("const %s is not a plain literal" % name)
    return val


def object_entries(s, name):
    """Top-level entries of an object literal as (key, raw source) pairs --
    for a const whose values are partly code, like MATCHSETS."""
    a, b = const_span(s, name)
    i = _ws(s, a)
    assert s[i] == "{", name
    i = _ws(s, i + 1)
    out = []
    while s[i] != "}":
        m = IDENT.match(s, i)
        if not m:
            raise LitError("bad key in %s at %r" % (name, s[i:i + 30]))
        key = m.group(0)
        i = _ws(s, m.end())
        assert s[i] == ":", name
        v0 = _ws(s, i + 1)
        v1 = skip_expr(s, v0)
        out.append((key, s[v0:v1].rstrip()))
        i = _ws(s, v1)
        if s[i] == ",":
            i = _ws(s, i + 1)
    return out


# ------------------------------------------------------------------ emitting

def js_str(t):
    return json.dumps(t, ensure_ascii=False)


def emit(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return json.dumps(v)
    if isinstance(v, str):
        return js_str(v)
    if isinstance(v, list):
        return "[" + ",".join(emit(x) for x in v) + "]"
    if isinstance(v, dict):
        parts = []
        for k, x in v.items():
            key = k if IDENT.fullmatch(k) else js_str(k)
            parts.append(key + ":" + emit(x))
        return "{" + ",".join(parts) + "}"
    raise TypeError(type(v))


def emit_rows(rows, indent=""):
    """An array written one entry per line, the way the hand-written tables are."""
    if not rows:
        return "[]"
    return "[\n" + ",\n".join(indent + emit(r) for r in rows) + "\n]"


def emit_map(d, indent=""):
    if not d:
        return "{}"
    return "{\n" + ",\n".join(indent + js_str(k) + ":" + emit(v)
                             for k, v in d.items()) + "\n}"


def replace_const(s, name, src):
    a, b = const_span(s, name)
    return s[:a] + src + s[b:]
