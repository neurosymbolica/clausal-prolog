"""Ruling D6: in Clausal Prolog a dict is predicate forms only.

In the plain (engine) layout a dict literal becomes a fresh variable bound by
``dict_pairs(Var, [K-V, ...])`` placed before the goal that uses it, ``get/3``
keeps the engine's name, and ``X is {**D, k: v}`` becomes
``dict_put_pairs([k-v], D, X)``. The agreement test runs every case on the
live engine from the Clausal source (the ground truth) and from the translated
``.pl`` under both ``.pl`` front ends, and compares the answer lists.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import clausal
from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError, clausal_source_to_prolog)

REPO = Path(clausal.__file__).resolve().parents[1]

CASES = {
    "fact":     "findall(P, (fact_dict(D), dict_pairs(D, P)), L)",
    "read":     "findall(V, rd(V), L)",
    "nested":   "findall(V, nested(V), L)",
    "template": "findall(P, (tmpl(DS), member(D, DS), dict_pairs(D, P)), L)",
    # the KEY is bound inside the findall goal: building the template dict
    # before the findall (instead of inside its goal) cannot be right here
    "tkey":     "findall(P, (tkey(DS), member(D, DS), dict_pairs(D, P)), L)",
    "update":   "findall(P, upd(P), L)",
    "arg":      "findall(V, arg_call(V), L)",
    "negated":  "findall(1, neg(zz), L)",
    "missing":  "findall(V, (fact_dict(D), get(D, zz, V)), L)",
}
LIB = """-module(dm, [fact_dict(D), rd(V), nested(V), tmpl(L), upd(P), arg_call(V), neg(K), tkey(L)])
-private([a, b, c, inner, x, n, k, zz])
fact_dict({a: 1, b: 2}),
rd(V) <- (D is {a: 1}, get(D, a, V))
nested(V) <- (D is {inner: {x: 7}}, get(D, inner, I), get(I, x, V))
tmpl(L) <- (findall({n: X}, member(X, [1, 2]), L))
tkey(L) <- (findall({K: 1}, member(K, [a, b]), L))
upd(P) <- (D is {a: 1, b: 2}, D2 is {**D, b: 9, c: 3}, dict_pairs(D2, P))
arg_call(V) <- (pick({k: 5}, V))
pick(D, V) <- (get(D, k, V))
neg(K) <- (not get({a: 1}, K, _))
"""
DRIVER = ("-import_from(dm, [fact_dict, rd, nested, tmpl, upd, arg_call, neg, tkey])\n"
          "-private([zz])\n"
          # neg/1, not neg/0: an IMPORTED 0-arity goal passed to findall is a
          # separate translator-front-end defect (reported), not D6's.
          + "".join(f"c_{n}(L) <- ({g})\n" for n, g in CASES.items()))
SIGS = {"dm": {("fact_dict", 1), ("rd", 1), ("nested", 1), ("tmpl", 1),
               ("upd", 1), ("arg_call", 1), ("neg", 1), ("tkey", 1)}}

RUN = textwrap.dedent("""
    import sys, importlib
    sys.path.insert(0, sys.argv[1])
    from clausal import solve
    from clausal.logic.variables import Var, deref
    def fmt(v):
        v = deref(v)
        if isinstance(v, list): return "[" + ",".join(fmt(x) for x in v) + "]"
        if isinstance(v, tuple): return fmt(v[1]) + "-" + fmt(v[2]) if v[0] == "-" else str(v)
        return str(v)
    m = importlib.import_module("drv"); m = m.__dict__.get("$module", m)
    for name in sys.argv[2:]:
        L = Var()
        try:
            out = "no_solution"
            for _ in solve(("c_" + name, L), m):
                out = fmt(L); break
        except Exception as e:
            out = "RAISES " + type(e).__name__
        print(name + "=" + out)
""")


def _answers(root: Path, frontend: str | None) -> dict:
    env = dict(os.environ)
    if frontend:
        env["CLAUSAL_PL_FRONTEND"] = frontend
    proc = subprocess.run([sys.executable, "-c", RUN, str(root), *CASES], cwd=REPO,
                          env=env, capture_output=True, text=True, timeout=300)
    got = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    assert len(got) == len(CASES), (proc.stdout, proc.stderr[-800:])
    return got


@pytest.fixture(scope="module")
def truth(tmp_path_factory):
    root = tmp_path_factory.mktemp("d6_truth")
    (root / "dm.clausal").write_text(LIB)
    (root / "drv.clausal").write_text(DRIVER)
    return _answers(root, None)


def test_the_ground_truth_is_the_engine_documented_one(truth):
    assert truth == {
        "fact": "[[a-1,b-2]]", "read": "[1]", "nested": "[7]",
        "template": "[[n-1],[n-2]]", "tkey": "[[a-1],[b-1]]", "update": "[[a-1,b-9,c-3]]", "arg": "[5]",
        "negated": "[1]", "missing": "[]",
    }


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_every_case_agrees_with_the_engine(tmp_path, truth, frontend):
    for name, src in (("dm", LIB), ("drv", DRIVER)):
        (tmp_path / f"{name}.pl").write_text(clausal_source_to_prolog(
            src, strict=True, module_path=name, module_signatures=SIGS,
            module_specs="plain"))
    assert _answers(tmp_path, frontend) == truth


def _plain(src, **kw):
    return clausal_source_to_prolog(src, module_path="m", module_specs="plain", **kw)


def test_no_marker_and_no_iso_lowering_reaches_the_output():
    out = _plain(LIB)
    for gone in ("$clausal_dict_literal", "attribute(", "profile_get", "attrs_put"):
        assert gone not in out


def test_a_template_literal_is_built_inside_the_findall_goal():
    out = _plain("t(L) <- (findall({n: X}, member(X, [1, 2]), L))\n")
    assert "findall(Dict__1, (member(X, [1, 2]), dict_pairs(Dict__1, [n - X])), L)" in out


def test_a_negated_literal_stays_inside_the_negation():
    out = _plain("n() <- (not get({a: 1}, zz, _))\n")  # (0-arity is fine here: not imported)
    assert "\\+ (dict_pairs(Dict__1, [a - 1]), get(Dict__1, zz, _))" in out


def test_the_strict_subscript_is_refused_until_the_engine_has_a_strict_read():
    with pytest.raises(UntranslatableConstructError, match="dict subscript"):
        _plain("s(P, V) <- (V is P[k])\n", strict=True)


def test_the_relative_layout_keeps_the_iso_lowering():
    out = clausal_source_to_prolog("r(V) <- (D is {a: 1}, get(D, a, V))\n")
    assert "attribute(a, 1)" in out and "profile_get(" in out
