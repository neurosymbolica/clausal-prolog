"""The dumb seam, step (c) (operator GO 2026-09-26).

(c) RAW OUT: a goal-position seam -- ``if``/``while``/``for``, a
comprehension or generator expression, ``each``/``once_bind``/``with_bases``
-- hands back the engine's INTERNAL form: an atom is the plain ``str``, a
string is the carrier ``('$chars', s)``, a dict is the ``DictTerm``, and
nothing is walked or converted unless a SNAPSHOT is needed for correctness
(a value the engine will unbind again on backtracking).  Python text is
``to_python(T)``; comparisons are against ``--``-wrapped terms.

Step (d) -- the leak rule at the doors ``wrap_text`` never sees -- is
tests/test_leak_doors.py.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom, is_atom
from clausal.logic.cells import chars, is_chars
from clausal.terms import DictTerm, Var


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [verdict(V), result(A, B, C), sp(X), txt(T), pair(K, N), "
    "dct(D), kv(K, V), mk(P), color(C), big(X, D), mk2(P, A), mk3(P, A), al(X, Y), al2(X, Y), attr(P), bigmk(P, A), tp(P), nxt(N, M)])\n"
    "-double_quotes(chars)\n"
    "-private([permitted, art_6, k, red, blue, x])\n"
    "from clausal import to_python\n"
    "\n"
    "verdict(result(permitted, \"Article 6(1)\", art_6)),\n"
    "sp(permitted),\n"
    "txt(\"some text\"),\n"
    "pair(permitted, 1),\n"
    "pair(art_6, 2),\n"
    "dct({{k: \"text\", permitted: 1}}),\n"
    "kv(permitted, \"one\"),\n"
    "kv(k, permitted),\n"
    "mk(pair(A, B)) <- (between(1, 2, A), B is A),\n"
    "color(red),\n"
    "color(blue),\n"
    "doc = [(\"row\", i, (\"cell\", \"a\", i * 2)) for i in range(20000)]\n"
    "big(x, D) <- (D is ++doc),\n"
    "mk2(P, A) <- (P is pair(A, A), between(1, 2, A)),\n"
    "mk3(P, A) <- (between(1, 2, A), P is pair(A, A)),\n"
    "al(X, Y) <- (X is Y, Y is pair(1, 2)),\n"
    "al2(X, Y) <- (X is Y),\n"
    "attr(P) <- (dif(Y, 3), P is pair(Y, 2)),\n"
    "bigmk(P, A) <- (P is pair(++list(range(2000)), A), between(1, 2, A)),\n"
    "-table(tp/1)\n"
    "tp(pair(A, A)) <- between(1, 2, A),\n"
    "nxt(N, M) <- (N < 3, M is ++(N + 1)),\n"
)


def _rb(name, body):
    return _load(name, RB.format(name=name) + body)


# ── (c) the internal form comes out ─────────────────────────────────────────

class TestRawOut:
    def test_an_atom_is_the_plain_str(self):
        m = _rb("_ro_a", "def go():\n    for X in --sp(X):\n        return X\n")
        v = m.go()
        assert v == "permitted" and type(v) is str and is_atom(v)

    def test_a_string_is_the_carrier_and_compares_with_a_seam_literal(self):
        m = _rb("_ro_b", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T, (T == --\"some text\"), (T == \"some text\"), to_python(T)\n"
        ))
        t, eq_seam, eq_py, text = m.go()
        assert is_chars(t) and t == chars("some text")
        assert eq_seam is True, "a string answer IS the seam literal under -double_quotes(chars)"
        assert eq_py is False, "and is not a Python str -- ask to_python for text"
        assert text == "some text" and type(text) is str

    def test_a_compound_answer_is_the_cell_with_nothing_converted(self):
        m = _rb("_ro_c", "def go():\n    for V in --verdict(V):\n        return V\n")
        v = m.go()
        assert v == ("result", "permitted", chars("Article 6(1)"), "art_6")
        assert type(v[1]) is str and is_chars(v[2])

    def test_a_compound_answer_equals_its_seam_literal(self):
        m = _rb("_ro_c2", (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V == --result(permitted, \"Article 6(1)\", art_6)\n"
        ))
        assert m.go() is True

    def test_a_dict_answer_is_the_dictterm(self):
        m = _rb("_ro_d", "def go():\n    for D in --dct(D):\n        return D\n")
        d = m.go()
        assert isinstance(d, DictTerm)
        assert is_chars(d["k"]) and d["permitted"] == 1

    def test_if_exports_the_same_form_as_for(self):
        m = _rb("_ro_e", (
            "def go():\n"
            "    if --txt(T):\n"
            "        return T\n"
        ))
        assert is_chars(m.go())

    def test_a_dict_comprehension_and_a_generator_are_raw_too(self):
        m = _rb("_ro_f", (
            "def comp():\n"
            "    return {K: V for K, V in --kv(K, V)}\n"
            "def gen():\n"
            "    return list(X for X in --sp(X))\n"
        ))
        d = m.comp()
        assert set(d) == {"permitted", "k"} and all(type(k) is str for k in d)
        assert is_chars(d["permitted"]) and d["k"] == "permitted"
        assert m.gen() == ["permitted"]

    def test_with_bases_hands_back_the_raw_form(self, tmp_path):
        rb = tmp_path / "ro_lib.clausal"
        rb.write_text("-module(ro_lib, [txt(T)])\n-double_quotes(chars)\ntxt(\"t\"),\n")
        host = _rb("_ro_g", (
            "from clausal.import_hook import _load_module\n"
            "def go(path):\n"
            "    m = _load_module('ro_lib_alias', path)\n"
            "    for T in --m.txt(T):\n"
            "        return T\n"
        ))
        assert host.go(str(rb)) == chars("t")

    def test_the_boundary_walk_is_gone(self):
        import clausal.logic.seam as seam
        assert not hasattr(seam, "_to_boundary")


# ── (c) the snapshot rule: walk only what backtracking would unbind ─────────

class TestSnapshot:
    """THE SOUND RULE: an answer crosses by identity only if it is proven to
    hold NO Var object -- atomic, a compiled constant, or walked completely
    within the probe budget -- and is deref-walked into a copy otherwise.
    Every case below is one the trail-count heuristic (roborev 243) got
    wrong or never covered."""

    def _walks(self, monkeypatch):
        import clausal.logic.seam as seam
        calls = []
        real = seam._deref_walk
        monkeypatch.setattr(seam, "_deref_walk", lambda v: (calls.append(1), real(v))[1])
        return calls

    # ── the HIGH: a goal variable inside another goal variable's value ──

    def test_mk2_for_loop_answers_are_the_values_not_live_vars(self):
        m = _rb("_ss_h1", "def go():\n    return [P for P, A in --mk2(P, A)]\n")
        assert m.go() == [("pair", 1, 1), ("pair", 2, 2)]

    def test_mk2_answers_kept_across_iterations_do_not_change(self):
        m = _rb("_ss_h2", (
            "def go():\n"
            "    out = []\n"
            "    for P, A in --mk2(P, A):\n"
            "        out.append(P)\n"
            "    return out\n"
        ))
        assert m.go() == [("pair", 1, 1), ("pair", 2, 2)]

    def test_mk2_if_answer_equals_its_seam_literal(self):
        m = _rb("_ss_h3", "def go():\n    if --mk2(P, A):\n        return P == --pair(1, 1)\n")
        assert m.go() is True

    def test_the_other_binding_order_is_equally_covered(self):
        m = _rb("_ss_h4", "def go():\n    return [P for P, A in --mk3(P, A)]\n")
        assert m.go() == [("pair", 1, 1), ("pair", 2, 2)]

    def test_a_body_built_term_past_the_probe_budget_is_still_copied(self):
        """Soundness at budget exhaustion: the probe gives up on a big value,
        which means COPY, never identity."""
        m = _rb("_ss_h5", "def go():\n    return [(P[2], A) for P, A in --bigmk(P, A)]\n")
        assert m.go() == [(1, 1), (2, 2)]

    # ── aliasing, attributed variables, tabling, findall, while ──

    def test_aliased_goal_variables_bound_to_one_term(self):
        m = _rb("_ss_a1", "def go():\n    return [(X, Y, X == Y) for X, Y in --al(X, Y)]\n")
        assert m.go() == [(("pair", 1, 2), ("pair", 1, 2), True)]

    def test_aliased_goal_variables_left_unbound_are_one_variable(self):
        m = _rb("_ss_a2", "def go():\n    for X, Y in --al2(X, Y):\n        return X is Y\n")
        assert m.go() is True

    def test_a_value_bound_through_an_attributed_variable_is_copied_with_the_hole(self):
        from clausal.logic.variables import is_var
        m = _rb("_ss_at", "def go():\n    return [P for P in --attr(P)]\n")
        (p,) = m.go()
        assert p[0] == "pair" and is_var(p[1]) and p[2] == 2

    def test_a_tabled_predicates_answers_are_stable(self):
        m = _rb("_ss_tb", (
            "def go():\n"
            "    out = [P for P in --tp(P)]\n"
            "    return sorted(out)\n"
        ))
        assert m.go() == [("pair", 1, 1), ("pair", 2, 2)]

    def test_a_findall_result_crosses_as_the_list(self):
        m = _rb("_ss_fa", "def go():\n    if --findall(X, sp(X), L):\n        return L\n")
        assert m.go() == ["permitted"]

    def test_a_while_loop_exports_each_iteration(self):
        m = _rb("_ss_wh", (
            "def go():\n"
            "    cur, seen = 0, []\n"
            "    while --nxt(++cur, N):\n"
            "        seen.append(N)\n"
            "        cur = N\n"
            "    return seen\n"
        ))
        assert m.go() == [1, 2, 3]

    # ── the certificates ──

    def test_a_compiled_constant_answer_crosses_by_identity_with_zero_walks(self, monkeypatch):
        """THE PERF CONTRACT: a stored cell is the compiler's constant -- it
        can hold no Var and is the same object every call -- so it is handed
        out by identity, never walked, however large."""
        calls = self._walks(monkeypatch)
        rows = ", ".join(f'("row", {i}, ("cell", "a", {i * 2}))' for i in range(3000))
        m = _rb("_ss_cc", (
            f"-private([stored])\n"
            f"stored_doc = (\"doc\", {rows})\n"
            "def first():\n"
            "    if --lst(L):\n"
            "        return L\n"
        ))
        # the fact lst([permitted, "text"]) holds a LIST (fresh per call) --
        # the cell inside it is the constant; verdict/1's answer IS a constant:
        m2 = _rb("_ss_cc2", (
            "def go():\n"
            "    if --verdict(V):\n"
            "        return V\n"
            "def loop():\n"
            "    return [V for V in --verdict(V)]\n"
        ))
        v1 = m2.go(); v2 = m2.go()
        assert v1 is v2, "the compiled constant itself, by identity"
        assert m2.loop()[0] is v1
        assert calls == [], f"walked {len(calls)} time(s)"
        from clausal.logic.cells import is_compiled_constant
        assert is_compiled_constant(v1)

    def test_a_large_stored_cell_is_never_walked(self, monkeypatch):
        calls = self._walks(monkeypatch)
        rows = ", ".join(f'row({i}, cell(a, {i * 2}))' for i in range(5000))
        m = _load("_ss_big", (
            "-module(_ss_big, [big(X, D), row(I, C), cell(A, B)])\n"
            "-implicit_functors\n"
            "-private([x, a])\n"
            f"big(x, doc({rows})),\n"
            "def go():\n"
            "    if --big(X, D):\n"
            "        return D\n"
        ))
        d1 = m.go(); d2 = m.go()
        assert d1 is d2 and len(d1) == 5001
        assert calls == [], f"walked {len(calls)} time(s)"

    def test_a_plusplus_built_list_is_copied_once_and_equal(self, monkeypatch):
        """A Python object carries no certificate and is larger than the
        probe budget: it is copied, once, and the copy is equal."""
        calls = self._walks(monkeypatch)
        m = _rb("_ss_pp", "def go():\n    if --big(X, D):\n        return D\n")
        d = m.go()
        assert d == m.doc and d is not m.doc
        assert len(calls) == 1

    def test_a_small_body_built_ground_answer_is_proven_by_the_probe(self, monkeypatch):
        calls = self._walks(monkeypatch)
        m = _rb("_ss_pr", "def go():\n    return [P for P in --mk(P)]\n")
        assert m.go() == [("pair", 1, 1), ("pair", 2, 2)]
        # pair(A, B) with A, B BOUND holds Var objects -> not proven -> copied
        assert len(calls) == 2

    def test_probe_semantics(self):
        from clausal.logic.seam import _probe_var_free
        from clausal.logic.variables import Var, Trail, unify
        v = Var(); unify(v, 1, Trail())
        assert _probe_var_free(("f", 1, ["a", {"k": ("g", 2)}]))
        assert not _probe_var_free(("f", v)), "a BOUND var still refuses"
        assert not _probe_var_free(("f", Var()))
        assert not _probe_var_free(list(range(600)), budget=512), "budget exhausted is not proven"
        assert not _probe_var_free(DictTerm({"k": Var()}))


def test_the_constant_registry_is_bounded_and_dropping_is_sound(monkeypatch):
    from clausal.logic import cells
    monkeypatch.setattr(cells, "_COMPILED_GROUND_CAP", 10)
    saved = dict(cells._COMPILED_GROUND)
    cells._COMPILED_GROUND.clear()
    try:
        consts = [(("k", i),) for i in range(12)]
        code = compile("x = 1", "<t>", "exec")
        class C:                       # a stand-in code object: only co_consts is read
            co_consts = tuple(consts)
        cells.register_compiled_constants(C)
        assert len(cells._COMPILED_GROUND) <= 12 and len(cells._COMPILED_GROUND) >= 6
        # a dropped constant is simply no longer certified -- never a wrong answer
        from clausal.logic.seam import export
        from clausal.logic.variables import Var, Trail, unify
        for c in consts:
            v = Var(); unify(v, c, Trail())
            assert export(v) == c
    finally:
        cells._COMPILED_GROUND.clear(); cells._COMPILED_GROUND.update(saved)

