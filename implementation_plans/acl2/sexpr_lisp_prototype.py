"""Prototype: a Lisp whose S-expressions ARE Clausal terms.

Canonical mapping (one term per Lisp value, so Lisp `equal` is Clausal
unification / ==):

  symbol            -> str atom                 nil, t are atoms too
  integer/rational  -> int / Fraction
  string            -> ('$chars', s)
  (f a b ...)       -> ('f', a, b, ...)          symbol head, 2+ elements: a cell
  other list        -> ('()', e1, ..., en)       (f), (1 2), ((lambda ..) x)
  (a . b)           -> ('$cons', a, b)           cdr not a list

The evaluator covers the applicative core ACL2's logic is built on: quote,
if, let/let*, lambda application, defun, cond/and/or/list as macros, and
the primitives below.  It is a prototype, not a Common Lisp.
"""
from __future__ import annotations

import re
import sys
from fractions import Fraction

from clausal.logic.cells import chars, is_chars, chars_text, TUPLE_TAG

NIL, T = "nil", "t"
CONS = "$cons"

# ── the list view over canonical terms ───────────────────────────────────

def is_sym(x):
    return type(x) is str


def make_list(items, tail=NIL):
    """The canonical term for (items... . tail)."""
    items = list(items)
    if tail != NIL:                      # improper: nest $cons from the right
        out = tail
        for x in reversed(items):
            out = (CONS, x, out)
        return out
    if not items:
        return NIL
    if is_sym(items[0]) and len(items) >= 2:
        return tuple(items)              # a cell: (f a ...)
    return (TUPLE_TAG, *items)


def as_list(x):
    """The elements of a proper list term, or None."""
    if x == NIL:
        return []
    if type(x) is tuple and x:
        if x[0] == TUPLE_TAG:
            return list(x[1:])
        if x[0] == CONS:
            rest = as_list(x[2])
            return None if rest is None else [x[1], *rest]
        if is_chars(x):
            return None
        return list(x)                   # a cell is the list (f a ...)
    return None


def consp(x):
    return x != NIL and (as_list(x) is not None or (type(x) is tuple and x[:1] == (CONS,)))


def car(x):
    if x == NIL:
        return NIL
    if type(x) is tuple and x[0] == CONS:
        return x[1]
    return as_list(x)[0]


def cdr(x):
    if x == NIL:
        return NIL
    if type(x) is tuple and x[0] == CONS:
        return x[2]
    return make_list(as_list(x)[1:])


def cons(a, d):
    rest = as_list(d)
    return make_list([a]) if rest == [] else (
        make_list([a, *rest]) if rest is not None else (CONS, a, d))


# ── reader / printer ─────────────────────────────────────────────────────

_TOKEN = re.compile(r'\s*(?:(;[^\n]*)|("(?:\\.|[^"\\])*")|([()\'.])|([^\s()\'";]+))')


def read_all(text):
    toks = [m for m in _TOKEN.finditer(text) if not m.group(1) and m.group(0).strip()]
    pos = 0

    def form():
        nonlocal pos
        m = toks[pos]; pos += 1
        s, p, a = m.group(2), m.group(3), m.group(4)
        if s is not None:
            return chars(bytes(s[1:-1], "utf-8").decode("unicode_escape"))
        if p == "'":
            return make_list(["quote", form()])
        if p == "(":
            items, tail = [], NIL
            while toks[pos].group(3) != ")":
                if toks[pos].group(3) == ".":
                    pos += 1; tail = form(); continue
                items.append(form())
            pos += 1
            return make_list(items, tail)
        if re.fullmatch(r"[+-]?\d+", a):
            return int(a)
        if re.fullmatch(r"[+-]?\d+/\d+", a):
            return Fraction(a)
        return a.lower()
    out = []
    while pos < len(toks):
        out.append(form())
    return out


def read(text):
    [x] = read_all(text)
    return x


def show(x):
    if is_chars(x):
        return '"' + chars_text(x) + '"'
    if type(x) is tuple and x[0] == CONS:
        items, cur = [], x
        while type(cur) is tuple and cur[0] == CONS:
            items.append(cur[1]); cur = cur[2]
        return "(" + " ".join(map(show, items)) + " . " + show(cur) + ")"
    xs = as_list(x)
    if xs is not None and x != NIL:
        return "(" + " ".join(map(show, xs)) + ")"
    return str(x)


# ── evaluator ────────────────────────────────────────────────────────────

class LispError(Exception):
    pass


def truthy(x):
    return x != NIL


def _bool(b):
    return T if b else NIL


def _num(x):
    if isinstance(x, (int, Fraction)) and not isinstance(x, bool):
        return x
    return 0                              # ACL2's completion: non-numbers act as 0


def _norm(q):
    return int(q) if isinstance(q, Fraction) and q.denominator == 1 else q


PRIMS = {
    "car": car, "cdr": cdr, "cons": cons,
    "consp": lambda x: _bool(consp(x)),
    "atom": lambda x: _bool(not consp(x)),
    "endp": lambda x: _bool(not consp(x)),
    "null": lambda x: _bool(x == NIL),
    "not": lambda x: _bool(x == NIL),
    "equal": lambda a, b: _bool(a == b),
    "eq": lambda a, b: _bool(a == b),
    "symbolp": lambda x: _bool(is_sym(x)),
    "stringp": lambda x: _bool(is_chars(x)),
    "integerp": lambda x: _bool(type(x) is int),
    "rationalp": lambda x: _bool(isinstance(x, (int, Fraction))),
    "acl2-numberp": lambda x: _bool(isinstance(x, (int, Fraction))),
    "natp": lambda x: _bool(type(x) is int and x >= 0),
    "zp": lambda x: _bool(not (type(x) is int and x > 0)),
    "binary-+": lambda a, b: _norm(_num(a) + _num(b)),
    "binary-*": lambda a, b: _norm(_num(a) * _num(b)),
    "unary--": lambda a: -_num(a),
    "unary-/": lambda a: _norm(Fraction(1, _num(a))) if _num(a) else 0,
    "<": lambda a, b: _bool(_num(a) < _num(b)),
    "numerator": lambda q: Fraction(_num(q)).numerator,
    "denominator": lambda q: Fraction(_num(q)).denominator,
}


def _fold(op, unit):
    def f(*args):
        out = unit
        for a in args:
            out = PRIMS[op](out, a)
        return out
    return f


VARIADIC = {
    "+": _fold("binary-+", 0), "*": _fold("binary-*", 1),
    "-": lambda a, *bs: PRIMS["unary--"](a) if not bs else _norm(_num(a) - sum(map(_num, bs))),
    "/": lambda a, *bs: PRIMS["unary-/"](a) if not bs else _norm(Fraction(_num(a)) / _prod(bs)),
    ">": lambda a, b: PRIMS["<"](b, a),
    "<=": lambda a, b: _bool(not truthy(PRIMS["<"](b, a))),
    ">=": lambda a, b: _bool(not truthy(PRIMS["<"](a, b))),
    "list": lambda *xs: make_list(xs),
}


def _prod(xs):
    out = Fraction(1)
    for x in xs:
        out *= _num(x)
    return out


class Lisp:
    """One Lisp world: its defuns.  ``eval(form)`` takes and returns terms."""

    def __init__(self):
        self.defuns = {}

    def load(self, text):
        out = NIL
        for form in read_all(text):
            out = self.eval(form)
        return out

    def eval(self, x, env=None):
        env = env or {}
        while True:                       # loop for tail positions of if/let
            if is_sym(x):
                if x in (NIL, T) or x.startswith(":"):
                    return x
                if x in env:
                    return env[x]
                raise LispError(f"unbound variable {x}")
            if not (type(x) is tuple) or is_chars(x):
                return x                  # numbers, strings
            xs = as_list(x)
            if xs is None:
                raise LispError(f"cannot evaluate {show(x)}")
            head, args = xs[0], xs[1:]
            if head == "quote":
                return args[0]
            if head == "if":
                x = args[1] if truthy(self.eval(args[0], env)) else (args[2] if len(args) > 2 else NIL)
                continue
            if head == "cond":
                for clause in args:
                    test, *body = as_list(clause)
                    v = self.eval(test, env)
                    if truthy(v):
                        x = make_list(["progn", *body]) if body else make_list(["quote", v])
                        break
                else:
                    return NIL
                continue
            if head == "progn":
                for f in args[:-1]:
                    self.eval(f, env)
                x = args[-1]; continue
            if head == "and":
                v = T
                for f in args:
                    v = self.eval(f, env)
                    if not truthy(v):
                        return NIL
                return v
            if head == "or":
                for f in args:
                    v = self.eval(f, env)
                    if truthy(v):
                        return v
                return NIL
            if head in ("let", "let*"):
                new = dict(env)
                for b in as_list(args[0]):
                    name, val = as_list(b)
                    new[name] = self.eval(val, new if head == "let*" else env)
                env, x = new, make_list(["progn", *args[1:]])
                continue
            if head == "defun":
                name, params, *body = args
                self.defuns[name] = (as_list(params), body[-1])
                return name
            vals = [self.eval(a, env) for a in args]
            if type(head) is tuple and as_list(head)[0] == "lambda":
                _, params, body = as_list(head)
                env, x = dict(zip(as_list(params), vals)), body
                continue
            if head in self.defuns:
                params, body = self.defuns[head]
                if len(params) != len(vals):
                    raise LispError(f"{head} takes {len(params)} arguments")
                env, x = dict(zip(params, vals)), body
                continue
            fn = PRIMS.get(head) or VARIADIC.get(head)
            if fn is None:
                raise LispError(f"undefined function {head}")
            return fn(*vals)


sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
