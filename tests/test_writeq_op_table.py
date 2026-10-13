"""writeq/1, write/1, write_term/2 follow the operator table in force.

todo/done/writeq-ignores-op-table-2026-10-14.md.  The ISO writers printed
with a frozen copy of Scryer's default table, so after an ``op/3`` the text
was not what Scryer prints and often did not read back under the table that
produced it (``:- op(700, xfx, -).`` then ``writeq(-(-(1,2),3))`` printed
``1-2-3``, a syntax error under xfx).

``clausal.terms.term_write`` now takes the table (*ops*), and the ISO
writers ask ``clausal.terms.writer_op_table()`` for it -- the one seam onto
``clausal.tools.prolog_operators.runtime_op_table()``, the process-wide table
op/3 changes.  These tests drive that seam through its interface
(``runtime_op_table`` / ``runtime_op_table_is_default``), set here with
monkeypatch, so they hold whether or not the runtime table exists yet.

Expected strings are the answers of Ulrich Neumerkel's ISO conformity table
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing,
fetched 2026-10-14); where the table says "e.g." the string is Scryer's, and
Scryer is run live as the oracle when it is built.
"""
import contextlib
import io
import itertools
import os
import pathlib
import random
import sys

import pytest

from clausal.terms import term_canonical, term_write, writer_op_table, _WQ_OPS
from clausal.tools import prolog_operators
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_reader import read_module

from tests._oracles import SCRYER, run_scryer


# (Ulrich row, op/3 arguments in force, goal, expected output).  The op/3
# context of a "/**/" row is the context of the rows it continues.
ROWS = [
    (136, ["0,fy,-"], "writeq(-(1))", "-(1)"),
    (328, ["0,fy,-"], "writeq([-])", "[-]"),
    (215, ["100,yfx,~"], "writeq(-(1~2~3))", "- (1~2~3)"),
    (248, ["100,yfx,~"], "writeq(- (1~2))", "- (1~2)"),
    (249, ["100,yfx,~"], "writeq(1~2)", "1~2"),
    (278, ["9,xfy,."], "writeq(-[1])", "-[1]"),
    (279, ["9,xf,'$VAR'"], "writeq(- '$VAR'(0))", "-A"),
    (296, ["9,xf,'$VAR'"], "writeq('$VAR'(0))", "A"),
    (355, ["9,xf,'$VAR'"], "writeq('$VAR'(-1))", "-1'$VAR'"),
    (204, ["9,xf,e"], "writeq(1e)", "1 e"),                 # e.g.
    (220, ["9,xf,e"], "writeq(1.0e)", "1.0 e"),             # e.g.
    (196, ["100,xf,''"], "writeq(0 '')", "0 ''"),           # or 0''
    (207, ["100,xf,f"], "writeq(0'f'f')", "102 f"),         # e.g.
    (209, ["100,xf,f"], "writeq(0'ff)", "102 f"),
    (256, ["100,xf,f"], "writeq(0f)", "0 f"),
    (208, ["100,xf,'f '"], "writeq(0 'f ')", "0 'f '"),
    (132, ["100,fx,' op'"], "writeq(' op' '1')", "' op' '1'"),
    (133, ["100,fx,' op'"], "writeq(' op'[])", "' op'[]"),
    (144, ["100,xfy,."], "writeq([1])", "[1]"),
    (283, ["100,xfy,."], "writeq(-[1])", "-[1]"),
    (147, ["9,fy,fy", "9,yf,yf"], "write_canonical(fy 1 yf)", "fy(yf(1))"),
    (149, ["9,fy,fy", "9,yf,yf"], "writeq(fy(yf(1)))", "fy 1 yf"),
    (150, ["9,fy,fy", "9,yf,yf"], "writeq(yf(fy(1)))", "(fy 1)yf"),
    (319, ["9,fy,fy", "9,yf,yf"], "writeq(yf(fy(yf(fy(1)))))", "(fy (fy 1)yf)yf"),
    (151, ["9,fy,fy", "9,yfx,yfx"], "write_canonical(fy 1 yfx 2)", "fy(yfx(1,2))"),
    (152, ["9,fy,fy", "9,yfx,yfx"], "writeq(fy(yfx(1,2)))", "fy 1 yfx 2"),
    (153, ["9,fy,fy", "9,yfx,yfx"], "writeq(yfx(fy(1),2))", "(fy 1)yfx 2"),
    (154, ["9,yf,yf", "9,xfy,xfy"], "write_canonical(1 xfy 2 yf)", "xfy(1,yf(2))"),
    (155, ["9,yf,yf", "9,xfy,xfy"], "writeq(xfy(1,yf(2)))", "1 xfy 2 yf"),
    (156, ["9,yf,yf", "9,xfy,xfy"], "writeq(yf(xfy(1,2)))", "(1 xfy 2)yf"),
    (159, ["9,fy,f", "9,yf,f"], "write_canonical(f f 0)", "f(f(0))"),
    (201, ["9,fy,f", "9,yf,f"], "writeq(f(f(0)))", "f f 0"),   # e.g.
    (202, ["9,fy,f", "9,yf,f"], "write_canonical(f 0 f)", "f(f(0))"),
    (163, ["9,fy,p", "9,xfy,p"], "write_canonical(1 p p p 2)", "p(1,p(p(2)))"),
    (164, ["7,fy,p", "9,yfx,p"], "write_canonical(1 p p p 2)", "p(1,p(p(2)))"),
    (169, ["0,xfy,.", "9,yf,."], "writeq(.(.))", "('.')'.'"),
    (194, ["0,xfy,."], "writeq((.)+(.))", "'.'+'.'"),
    (181, ["1105,xfy,'|'"], "writeq((a-->b,c|d))", "a-->b,c|d"),
    (322, ["1105,xfy,'|'"], "write_canonical((a|b;c))", "'|'(a,;(b,c))"),
    (323, ["1105,xfy,'|'"], "write_canonical((a;b|c))", "'|'(;(a,b),c)"),
    (290, ["1105,xfy,'|'"], "writeq([(a|b)])", "[(a|b)]"),
    (317, ["1105,xfy,'|'"], "writeq([a,(b,c)|[]])", "[a,(b,c)]"),
    (200, ["900,fy,[$]"], "write_canonical($a+b)", "$(+(a,b))"),
    (234, ["400,fx,f"], "writeq(f/*.*/(1,2))", "f (1,2)"),
    (341, ["699,xf,>."], "writeq(>(>.(a),b))", "a>. >b"),
    (342, ["699,xf,>."], "write_canonical(a>. >b)", ">(>.(a),b)"),
    (343, ["699,xf,>."], "write_canonical(a>. =b)", "=(>.(a),b)"),
    (344, ["699,xf,>."], "write_canonical((a>.,b))", "','(>.(a),b)"),
    (345, ["699,xf,>."], "write_canonical(a>.)", ">.(a)"),
    (251, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0bop 2)", "0 bop 2"),
    (263, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0 bop 2)", "0 bop 2"),
    (252, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0bo 2)", "0 bo 2"),
    (253, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0b 2)", "0 b 2"),
    (254, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0op 2)", "0 op 2"),
    (255, ["9,yfx,[bop,bo,b,op,xor]"], "writeq(0xor 2)", "0 xor 2"),
    (266, ["9,yf,[b2,o8]"], "writeq(0b2)", "0 b2"),
    (267, ["9,yf,[b2,o8]"], "writeq(0o8)", "0 o8"),
    (274, ["20,fx,--"], "writeq(--(a))", "--a"),
    (275, ["20,fx,--", "0,fy,--"], "writeq(--(a))", "--(a)"),
    (304, ["300,fy,~"], "writeq(~ (a=b))", "~ (a=b)"),
    (333, ["9,fx,."], "writeq(.(' '))", "'.' ' '"),
    (336, ["9,yf,.>"], "writeq(((a).>).>)", "a.> .>"),
]

# The review's op/3 cases (Scryer's text): the engine's old text did not
# read back under the table that produced it.
PROBES = [
    ("xfx-minus-left", ["700,xfx,-"], "writeq(-(-(1,2),3))", "(1-2)-3"),
    ("xfx-minus-plus", ["700,xfx,-"], "writeq(-(1,2)+3)", "(1-2)+3"),
    ("xfx-caret", ["200,xfx,^"], "writeq(2^(3^4))", "2^(3^4)"),
    ("xfx-caret-neg", ["200,xfx,^"], "writeq(2^(-(1)))", "2^(- (1))"),
    ("fy100-minus", ["100,fy,-"], "writeq(-(a)^2)", "-a^2"),
    ("fy100-minus-1", ["100,fy,-"], "writeq(-(1)^2)", "- (1)^2"),
    ("fx-minus", ["200,fx,-"], "writeq(-(-(a)))", "- (-a)"),
    ("fx-minus-1", ["200,fx,-"], "writeq(-(-(1)))", "- (- (1))"),
    ("no-plus", ["0,fy,+"], "writeq(+(1))", "+(1)"),
    ("no-plus-a", ["0,fy,+"], "writeq(+(a))", "+(a)"),
    ("no-plus-pow", ["0,fy,+"], "writeq(+(1^2))", "+(1^2)"),
    ("no-minus-a", ["0,fy,-"], "writeq(-(a))", "-(a)"),
    ("no-minus-neg", ["0,fy,-"], "writeq(-(-1))", "-(-1)"),
    ("no-minus-pow", ["0,fy,-"], "writeq(-(1^2))", "-(1^2)"),
    ("minus-postfix", ["9,yf,yf"], "writeq(-(yf(1)))", "- (1 yf)"),
    ("write-unquoted", ["700,xfx,~>"], "write(f(a~>'B c'))", "f(a~>B c)"),
]

CASES = [pytest.param(*r, id=f"ulrich-{r[0]}") for r in ROWS] + [
    pytest.param(*p, id=p[0]) for p in PROBES]


def _table(ops):
    """Scryer's default table with each ``op(P, T, N)`` of *ops* applied."""
    t = OperatorTable.scryer_builtin_default()
    for o in ops:
        item = read_module(f"x :- op({o}).\n",
                           op_table=OperatorTable.scryer_builtin_default())[0]
        _op, p, spec, names = item.term[2]
        for n in names if isinstance(names, list) else [names]:
            t.define(p, spec, n)
    return t


def _program(ops, goal):
    return "".join(f":- op({o}).\n" for o in ops) + f"r :- {goal}.\n"


@pytest.fixture
def runtime_table(monkeypatch):
    """Install *table* as the runtime operator table, through the interface
    the writer's seam reads."""
    def install(table):
        monkeypatch.setattr(prolog_operators, "runtime_op_table",
                            lambda: table, raising=False)
        monkeypatch.setattr(prolog_operators, "runtime_op_table_is_default",
                            lambda: False, raising=False)
    return install


# ── the writer with an explicit table ────────────────────────────────────────


@pytest.mark.parametrize("row, ops, goal, want", CASES)
def test_writer_with_explicit_table(row, ops, goal, want):
    table = _table(ops)
    item = read_module(f"r :- {goal}.\n", op_table=table)[0]
    writer, term = item.term[2][0], item.term[2][1]
    if writer == "write_canonical":
        got = term_canonical(term)
    else:
        got = term_write(term, quoted=writer == "writeq", ops=table)
    assert got == want


# ── the ISO writers, through the native .pl front end and the seam ──────────


def _run_native(tmp_path, monkeypatch, ops, goal, name):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    import clausal.import_hook  # noqa: F401,PLC0415
    from clausal.import_hook import _load_prolog_module  # noqa: PLC0415
    from clausal.logic.solve import solve  # noqa: PLC0415
    path = tmp_path / f"{name}.pl"
    path.write_text(_program(ops, goal), encoding="utf-8")
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod = _load_prolog_module(name, str(path))
            ok = any(True for _ in itertools.islice(solve("r", mod), 1))
    finally:
        sys.modules.pop(name, None)
    assert ok
    return buf.getvalue()


@pytest.mark.parametrize("row, ops, goal, want", CASES)
def test_native_front_end(row, ops, goal, want, tmp_path, monkeypatch,
                          runtime_table):
    runtime_table(_table(ops))
    name = f"_wq_ops_{row}".replace("-", "_")
    assert _run_native(tmp_path, monkeypatch, ops, goal, name) == want


@pytest.mark.skipif(not os.path.exists(SCRYER), reason="Scryer not built here")
@pytest.mark.parametrize("row, ops, goal, want", CASES)
def test_scryer_agrees(row, ops, goal, want, tmp_path):
    path = tmp_path / "row.pl"
    path.write_text(_program(ops, goal), encoding="utf-8")
    out = run_scryer(str(path), ["r, write('@END'), nl."], timeout=60).stdout
    assert "@END" in out, out
    assert out.split("@END")[0] == want


def test_op_directive_reaches_the_writer_only_through_the_seam(
        tmp_path, monkeypatch, runtime_table):
    """With the default runtime table the writer prints as it always did --
    the case the seam's fast path covers."""
    runtime_table(_table([]))
    monkeypatch.setattr(prolog_operators, "runtime_op_table_is_default",
                        lambda: True, raising=False)
    out = _run_native(tmp_path, monkeypatch, [], "writeq(-(-(1,2),3))",
                      "_wq_ops_default")
    assert out == "1-2-3"


# ── ignore_ops and write_canonical ignore the table ──────────────────────────


@pytest.mark.parametrize("goal, want", [
    ("write_canonical(1~2)", "~(1,2)"),
    ("write_term(1~2, [ignore_ops(true)])", "~(1,2)"),
    ("write_term(- (1~2), [ignore_ops(true)])", "-(~(1,2))"),
    ("write_term(1~2, [])", "1~2"),
    ("writeq(1~2)", "1~2"),
])
def test_ignore_ops(goal, want, tmp_path, monkeypatch, runtime_table):
    ops = ["700,xfx,~"]
    runtime_table(_table(ops))
    assert _run_native(tmp_path, monkeypatch, ops, goal,
                       "_wq_ops_ignore") == want


# ── the seam ─────────────────────────────────────────────────────────────────


def test_seam_without_runtime_accessor(monkeypatch):
    monkeypatch.delattr(prolog_operators, "runtime_op_table", raising=False)
    assert writer_op_table() is _WQ_OPS


def test_seam_fast_path_when_default(monkeypatch):
    calls = []
    monkeypatch.setattr(prolog_operators, "runtime_op_table",
                        lambda: calls.append(1), raising=False)
    monkeypatch.setattr(prolog_operators, "runtime_op_table_is_default",
                        lambda: True, raising=False)
    assert writer_op_table() is _WQ_OPS
    assert calls == []


def test_seam_returns_the_runtime_table(monkeypatch, runtime_table):
    table = _table(["700,xfx,-"])
    runtime_table(table)
    assert writer_op_table() is table


# ── the default table's output is unchanged ──────────────────────────────────


@pytest.mark.parametrize("term, want", [
    (("mod", ("+", 1, 2), 3), "(1+2) mod 3"),
    (("is", ("f", "a"), ["x"]), "f(a) is [x]"),
    (("-", 1), "- (1)"),
    (("-", 1, ("-", 2, 3)), "1-(2-3)"),
    (("-", "a", -1), "a- -1"),
    (("-", ("^", 1, 2)), "- (1^2)"),
    (("-", ("-", "a")), "- -a"),
    (("+", 1), "+1"),
    (("\\+", (",", "a", "b")), "\\+ (a,b)"),
    (("=", "-", "-"), "(-)=(-)"),
])
def test_default_table_pinned(term, want):
    assert term_write(term, quoted=True) == want
    assert term_write(term, quoted=True,
                      ops=OperatorTable.scryer_builtin_default()) == want


_DEFAULT_NAMES = ["-", "+", "*", "^", "=", "**", "/", "mod", ":", "is", "xor",
                  "rdiv", "\\+", "\\", ",", ";", "->", ":-", "-->", "|", "=..",
                  "f", "$VAR", "{}", ".", "a b", "'", "[]"]


def _rand_default(rng, d=0):
    if d > 4 or rng.random() < 0.3:
        return rng.choice([0, 1, -1, 1.5, -2.5, "a", [], "{}",
                           rng.choice(_DEFAULT_NAMES), "a b", "0"])
    n = rng.choice(_DEFAULT_NAMES)
    if n == "$VAR":
        return ("$VAR", rng.choice([0, 27, -1, "x"]))
    ar = 2 if n == "." else rng.choice([1, 2, 2, 3])
    return (n,) + tuple(_rand_default(rng, d + 1) for _ in range(ar))


def test_default_table_copy_writes_the_same():
    """A table equal to the default (the runtime table before any op/3)
    writes byte for byte what the frozen default writes."""
    rng = random.Random(20261014)
    copy = OperatorTable.scryer_builtin_default()
    for _ in range(3000):
        t = _rand_default(rng)
        for quoted in (True, False):
            assert (term_write(t, quoted=quoted, ops=copy)
                    == term_write(t, quoted=quoted)), t


# ── round trip under random tables ───────────────────────────────────────────

_NAMES = ["-", "+", "*", "^", "=", "~", "~>", "&&", "#", "++", "fy", "yf",
          "op", "xor", "bop", "f", "\\", "**", "/", "mod", ":"]
_PRIS = [1, 9, 100, 199, 200, 201, 300, 400, 500, 699, 700, 999, 1000, 1100,
         1200]


def _rand_table(rng):
    t = OperatorTable.scryer_builtin_default()
    for _ in range(rng.randint(1, 6)):
        n = rng.choice(_NAMES)
        kind = rng.choice(["pre", "in", "post", "del"])
        if kind == "del":
            spec, p = rng.choice(["fy", "xfx", "xf"]), 0
        else:
            spec = rng.choice({"pre": ["fy", "fx"], "in": ["xfx", "xfy", "yfx"],
                               "post": ["xf", "yf"]}[kind])
            p = rng.choice(_PRIS)
        # ISO 8.14.3.3: no name is both an infix and a postfix operator.
        if spec in ("xf", "yf") and t.lookup_infix(n):
            continue
        if spec in ("xfx", "xfy", "yfx") and t.lookup_postfix(n):
            continue
        t.define(p, spec, n)
    return t


def _rand_term(rng, d=0):
    if d > 4 or rng.random() < 0.3:
        return rng.choice([0, 1, -1, 2, 1.5, -2.5, "a", "b", [], "{}",
                           rng.choice(_NAMES), "'", "a b", "0"])
    n = rng.choice(_NAMES + ["g", "."])
    ar = 2 if n == "." else rng.choice([1, 1, 2, 2, 2, 3])
    return (n,) + tuple(_rand_term(rng, d + 1) for _ in range(ar))


def _norm(t):
    """The reader returns a proper list as a Python list."""
    if type(t) is tuple:
        if t[0] == "." and len(t) == 3:
            h, tl = _norm(t[1]), _norm(t[2])
            return [h] + tl if isinstance(tl, list) else (".", h, tl)
        return (t[0],) + tuple(_norm(a) for a in t[1:])
    if isinstance(t, list):
        return [_norm(a) for a in t]
    return t


def _scryer_program(table, text):
    """A Scryer program that installs *table* and write_canonical's *text*."""
    lines = []
    for entries in table._ops.values():
        for e in entries:
            if e.name not in (",", "|"):
                lines.append(f":- op({e.precedence}, {e.specifier}, "
                             f"{term_canonical(e.name)}).")
    default = OperatorTable.scryer_builtin_default()
    look = {"fx": "lookup_prefix", "fy": "lookup_prefix",
            "xf": "lookup_postfix", "yf": "lookup_postfix"}
    for entries in default._ops.values():
        for e in entries:
            if getattr(table, look.get(e.specifier, "lookup_infix"))(e.name) is None:
                lines.append(f":- op(0, {e.specifier}, {term_canonical(e.name)}).")
    lines.append(f":- initialization((X = ({text}\n), write_canonical(X), nl)).")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_round_trip_under_random_tables(seed, tmp_path):
    """writeq under a random table, read back under the same table: the
    same term.  The native reader cannot yet read some postfix-operator
    texts (``b++ ++`` with yf, ``b yf-1`` with xf -- reader limits, not the
    writer's); those are read back by Scryer instead."""
    rng = random.Random(seed)
    reader_gaps = []
    for _ in range(1500):
        table = _rand_table(rng)
        term = _rand_term(rng)
        text = term_write(term, quoted=True, ops=table)
        item = read_module(f"t(({text}\n)).\n", op_table=table)[0]
        if type(item).__name__ == "Clause":
            assert _norm(item.term[1]) == _norm(term), text
        else:
            reader_gaps.append((table, term, text))
    assert len(reader_gaps) <= 5, [g[2] for g in reader_gaps]
    if reader_gaps and not os.path.exists(SCRYER):
        pytest.skip("Scryer not built here: reader-gap texts unchecked")
    for table, term, text in reader_gaps:
        path = tmp_path / "rt.pl"
        path.write_text(_scryer_program(table, text), encoding="utf-8")
        out = run_scryer(str(path), timeout=60).stdout.strip()
        assert out == term_canonical(term), text
