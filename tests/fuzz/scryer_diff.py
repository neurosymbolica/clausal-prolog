"""A seeded differential fuzzer: small pure goals run in Clausal and in Scryer.

Each case is a conjunction of a few goals over a few variables, drawn from
the parts of the engine where unification, attributed variables and woken
goals meet: ``=/2`` (aliases, bindings, cyclic terms such as ``X = f(X,1)``),
``dif/2``, ``freeze/2``, ``when/2`` (``nonvar``, ``ground``, ``?=``, ``,`` and
``;``), ``\\+``, ``;``, ``var``/``nonvar`` tests inside delayed goals,
``write/1`` (to see the order goals wake in), ``copy_term/2``,
``term_variables/2``, ``==/2``, ``compare/3`` and ``findall/3`` -- with the
constraints posted before and after the bindings that wake them, since the
goals come in random order.

A case runs as one top-level query, the same text in both systems::

    catch((Goal, fz_show([A,B,...])), FzE, (fz_exc(FzE), fail)) ; fz_end(N)

so each answer prints its bindings with ``writeq/1`` (``fz_ans([...])``, a
cyclic term in the ``f(...)`` form both systems write), then the answer line
of the system's own top level, whose residual goals (``dif``, ``freeze``,
``when``) are what is compared from it; an error prints ``fz_exc(E)``.
Clausal runs the program as ``clausal prog.pl -g Q1 -g Q2 ...`` (the native
ISO front end; the C trampoline, or ``--python`` for the pure-Python twin);
Scryer runs ``tests/fuzz/_scryer_fz_top.pl``'s printer over the same
queries (Scryer is the reference: operator ruling 2026-10-24).

What is compared, per case, is the sequence of lines it prints, normalised:

* fresh variables (``_123``, ``_G7``, ``_A``) renamed ``_1``, ``_2``, ... in
  order of appearance, per line;
* the answer line reduced to its residual goals (the bindings are already in
  ``fz_ans``), library qualifiers (``dif:``, ``freeze:``, ``user:``) taken
  off, and each variable of an alias (``X = Y``) written as the least name
  of its alias group (Scryer and Clausal keep different survivors).

So answers, their order and multiplicity, residual constraints, the output
of woken goals and its interleaving with answers, and error versus failure
all have to agree.  A disagreement is shrunk (goals dropped, delayed bodies
cut down, while the two still disagree) and matched against
:data:`KNOWN`, the documented differences; what is left is reported.

Run it::

    python -m tests.fuzz.scryer_diff --seeds 0-49 --cases 60 --jobs 6
    python -m tests.fuzz.scryer_diff --show 7:12     # one case, both outputs

``tests/fuzz/test_scryer_diff.py`` runs a small fixed seed set under
pytest, a larger one with ``CLAUSAL_FUZZ_SEEDS=N``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import _oracles  # noqa: E402

SCRYER_TOP = str(Path(__file__).resolve().with_name("_scryer_fz_top.pl"))

PROGRAM = textwrap.dedent("""\
    w(X) :- write(X), nl.
    fz_show(Vs) :-
        write('fz_ans('), fz_us(Vs, 6), write(')'), nl,
        writeq(fz_wq(Vs)), nl.
    fz_exc(E) :- writeq(fz_exc(E)), nl.
    fz_end(N) :- writeq(fz_end(N)), nl.
    % A term unfolded to a fixed depth: one text for one rational tree,
    % however each system represents it (writeq/1's "..." for a cycle
    % depends on where the cycle is closed).
    fz_u(T, _) :- var(T), !, writeq(T).
    fz_u(_, 0) :- !, write('~').
    fz_u(T, _) :- atomic(T), !, writeq(T).
    fz_u(T, D) :-
        T =.. [F|As], D1 is D - 1,
        writeq(F), write('('), fz_us(As, D1), write(')').
    fz_us([], _).
    fz_us([A], D) :- !, fz_u(A, D).
    fz_us([A|As], D) :- fz_u(A, D), write(','), fz_us(As, D).
""")

SCRYER_PRELUDE = (":- use_module(library(freeze)).\n"
                  ":- use_module(library(when)).\n"
                  ":- use_module(library(dif)).\n"
                  ":- use_module(library(lists)).\n")

# The command, under the C or the pure-Python trampoline (as in
# tests/iso/test_freeze_alias_merge_scryer.py).
_CHILD = textwrap.dedent(r'''
    import sys
    if sys.argv[1] == "py":
        sys.modules["clausal.logic.runtime._trampoline"] = None
        sys.modules["clausal.logic._tabling_core"] = None
    import clausal.logic.trampoline as tr
    want = ("clausal.logic._trampoline_py" if sys.argv[1] == "py"
            else "clausal.logic.runtime._trampoline")
    assert tr.trampoline.__module__ == want, tr.trampoline.__module__
    from clausal.cli import main
    sys.exit(main(sys.argv[2:]))
''')


# ── the generator ────────────────────────────────────────────────────────────

BASE_VARS = ("A", "B", "C", "D")
ATOMS = ("a", "b", "1")


@dataclasses.dataclass
class Case:
    """One generated case: its goals (text) and the variables it shows."""
    goals: list
    variables: list
    label: str = ""

    def goal_text(self) -> str:
        return ", ".join(self.goals) if self.goals else "true"

    def query(self, n) -> str:
        shown = "[" + ",".join(self.variables) + "]"
        return (f"catch(({self.goal_text()}, fz_show({shown})), FzE,"
                f" (fz_exc(FzE), fail)) ; fz_end({n})")


class _Gen:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.tag = 0
        self.extra = 0
        self.vars: list = []

    # terms
    def var(self):
        return self.rng.choice(self.vars)

    def term(self, depth=0):
        r = self.rng.random()
        if depth >= 2 or r < 0.45:
            return self.var()
        if r < 0.62:
            return self.rng.choice(ATOMS)
        if r < 0.78:
            return f"f({self.term(depth + 1)},{self.term(depth + 1)})"
        if r < 0.88:
            return f"g({self.term(depth + 1)})"
        return f"[{self.term(depth + 1)}|{self.term(depth + 1)}]"

    def fresh(self):
        self.extra += 1
        name = f"E{self.extra}"
        self.vars.append(name)
        return name

    def new_tag(self):
        self.tag += 1
        return f"t{self.tag}"

    # goals
    def binding(self):
        v = self.var()
        r = self.rng.random()
        if r < 0.3:
            return f"{v} = {self.var()}"
        if r < 0.45:
            return f"{v} = {self.rng.choice(ATOMS)}"
        if r < 0.62:
            # a cyclic term
            shape = self.rng.choice(("f({v},{t})", "[{t}|{v}]", "g({v})",
                                     "f({t},{v})"))
            return f"{v} = " + shape.format(v=v, t=self.term(1))
        if r < 0.8:
            return f"{v} = {self.term()}"
        return f"{self.term()} = {self.term()}"

    def body(self, depth):
        parts = [f"w({self.new_tag()})"]
        for _ in range(self.rng.choice((0, 0, 1, 1, 2))):
            r = self.rng.random()
            if r < 0.15:
                parts.append(f"var({self.var()})")
            elif r < 0.3:
                parts.append(f"nonvar({self.var()})")
            elif r < 0.45:
                parts.append(f"w({self.var()})")
            elif r < 0.7:
                parts.append(self.binding())
            elif r < 0.85:
                parts.append(f"dif({self.term()},{self.term()})")
            elif depth < 1:
                parts.append(self.delay(depth + 1))
            else:
                parts.append(f"w({self.var()})")
        if self.rng.random() < 0.15 and len(parts) > 1:
            return "(" + " ; ".join(parts[:2]) + ")" if len(parts) == 2 else \
                "(" + parts[0] + " ; " + ", ".join(parts[1:]) + ")"
        return "(" + ", ".join(parts) + ")" if len(parts) > 1 else parts[0]

    def condition(self, depth=0):
        r = self.rng.random()
        if depth < 1 and r < 0.25:
            op = self.rng.choice((",", ";"))
            return f"({self.condition(depth + 1)}{op}{self.condition(depth + 1)})"
        r = self.rng.random()
        if r < 0.45:
            return f"nonvar({self.var()})"
        if r < 0.8:
            return f"ground({self.term(1)})"
        if r < 0.97:
            return f"ground({self.term()})"
        # neither system has ?=/2 as a when/2 condition: a domain error
        return f"?=({self.term(1)},{self.term(1)})"

    def delay(self, depth=0):
        if self.rng.random() < 0.6:
            return f"freeze({self.var()},{self.body(depth)})"
        return f"when({self.condition()},{self.body(depth)})"

    def simple(self):
        r = self.rng.random()
        if r < 0.5:
            return self.binding()
        if r < 0.8:
            return f"dif({self.term()},{self.term()})"
        return f"w({self.var()})"

    def goal(self):
        r = self.rng.random()
        if r < 0.24:
            return self.binding()
        if r < 0.36:
            return f"dif({self.term()},{self.term()})"
        if r < 0.58:
            return self.delay()
        if r < 0.62:
            return f"\\+ {self.simple()}"
        if r < 0.69:
            return f"({self.simple()} ; {self.simple()})"
        if r < 0.72:
            return f"{self.term()} == {self.term()}"
        if r < 0.74:
            return f"{self.term()} \\== {self.term()}"
        if r < 0.78:
            a, b = self.term(), self.term()
            return f"compare({self.fresh()},{a},{b})"
        if r < 0.82:
            t = self.term()
            return f"copy_term({t},{self.fresh()})"
        if r < 0.85:
            t = self.term()
            return f"term_variables({t},{self.fresh()})"
        if r < 0.89:
            t, g = self.term(), self.simple()
            return f"findall({t},{g},{self.fresh()})"
        if r < 0.94:
            return f"w({self.var()})"
        return f"{self.rng.choice(('var', 'nonvar'))}({self.var()})"


def generate(seed: int, count: int) -> list:
    """*count* cases, the same for the same *seed*."""
    rng = random.Random(seed)
    cases = []
    for i in range(count):
        g = _Gen(rng)
        g.vars = list(BASE_VARS[:rng.choice((2, 3, 3, 4))])
        goals = [g.goal() for _ in range(rng.randint(2, 6))]
        cases.append(Case(goals, _shown(goals, g.vars), f"{seed}:{i}"))
    return cases


_NAME = re.compile(r"\b[A-Z]\w*")


def _shown(goals, candidates):
    text = " ".join(goals)
    used = set(_NAME.findall(_strip_quoted(text)))
    return [v for v in candidates if v in used]


def _strip_quoted(text):
    return re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)


# ── running ──────────────────────────────────────────────────────────────────

class Runner:
    """Runs batches of cases in a scratch directory."""

    def __init__(self, workdir, *, python_twin=False, timeout=240):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.python_twin = python_twin
        self.timeout = timeout
        self.clausal_prog = self.workdir / "fz_prog.pl"
        self.clausal_prog.write_text(PROGRAM)
        self.scryer_prog = self.workdir / "fz_prog_scryer.pl"
        self.scryer_prog.write_text(SCRYER_PRELUDE + PROGRAM)

    # each returns {index: [lines]}
    def clausal(self, queries):
        return self._run(queries, "clausal")

    def scryer(self, queries):
        return self._run(queries, "scryer")

    def _run(self, queries, who):
        """Run *queries* in one process; a case the run never ended (a crash
        there) gets the error line, and the cases after it run again."""
        env = None
        if who == "clausal":
            env = dict(os.environ)
            env["CLAUSAL_PL_FRONTEND"] = "native"
            env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get(
                "PYTHONPATH", "")
        try:
            proc = subprocess.run(cmd_for(self, who, queries),
                                  cwd=self.workdir, env=env,
                                  stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True,
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            if len(queries) == 1:
                return {queries[0][0]: ["fz_timeout"]}
            half = len(queries) // 2
            out = self._run(queries[:half], who)
            out.update(self._run(queries[half:], who))
            return out
        got = split_cases(proc.stdout)
        partial = got.pop(("partial",), [])
        missing = [q for q in queries if q[0] not in got]
        if missing:
            err = proc.stderr.strip().splitlines()
            got[missing[0][0]] = partial + [
                "fz_crash(" + (err[-1] if err else f"rc={proc.returncode}")
                + ")"]
            if missing[1:]:
                got.update(self._run(missing[1:], who))
        return got


def cmd_for(runner, who, queries):
    if who == "clausal":
        argv = [a for q in queries for a in ("-g", q[1])]
        return [sys.executable, "-c", _CHILD,
                "py" if runner.python_twin else "c", *argv,
                runner.clausal_prog.name]
    argv = [_oracles.SCRYER, str(runner.scryer_prog), SCRYER_TOP]
    for n, q in queries:
        argv += ["-g", _scryer_goal(n, q)]
    return argv + ["-g", "halt"]


def _scryer_goal(n, q):
    return f"'$fz_top':query({n}, {_oracles._quoted_atom(q + ' .')})"


_END = re.compile(r"^fz_end\((\d+)\)$")


def split_cases(stdout):
    """The lines of each case, by its ``fz_end(N)`` line (and the ``true.``
    answer after it); lines after the last end are ``("partial",)``."""
    out, cur = {}, []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        m = _END.match(line.strip())
        if m:
            out[int(m.group(1))] = cur
            cur = []
            i += 1
            if i < len(lines) and lines[i].strip() == "true.":
                i += 1
            continue
        if line.strip():
            cur.append(line.strip())
        i += 1
    if cur:
        out[("partial",)] = cur
    return out


# ── normalising ──────────────────────────────────────────────────────────────

_QUALIFIER = re.compile(r"\b(?:freeze|when|dif|user|lists):")
_FRESH = re.compile(r"(?<![\w'])_[A-Za-z0-9_]*")


def _outside_quotes(text, fn):
    parts = re.split(r"('(?:[^'\\]|\\.)*')", text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


def canon_fresh(text):
    """Rename the fresh variables of *text* ``_1``, ``_2``, ... in order."""
    names = {}

    def sub(m):
        name = m.group(0)
        if name not in names:
            names[name] = f"_{len(names) + 1}"
        return names[name]
    return _outside_quotes(text, lambda p: _FRESH.sub(sub, p))


def split_conjuncts(text):
    """Split an answer line (no final ``.``) at its top-level commas."""
    out, depth, cur, quote = [], 0, [], False
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                quote = False
        elif ch == "'":
            quote = True
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


_BINDING = re.compile(r"^([A-Z_]\w*) = (.*)$", re.S)
_VARNAME = re.compile(r"^[A-Z_]\w*$")


def residuals(line, names):
    """The residual goals of one answer line, normalised (see the module
    docstring)."""
    body = line[:-1] if line.endswith(".") else line
    if body in ("true", "false"):
        return []
    conj = split_conjuncts(body)
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    goals = []
    for c in conj:
        m = _BINDING.match(c)
        if m:
            lhs, rhs = m.group(1), m.group(2).strip()
            if _VARNAME.match(rhs):
                a, b = find(lhs), find(rhs)
                if a != b:
                    lo, hi = sorted((a, b))
                    parent[hi] = lo
            continue
        goals.append(c)

    def rename(p):
        return re.sub(r"\b[A-Z_]\w*", lambda m: find(m.group(0)), p)
    return [canon_fresh(_outside_quotes(_QUALIFIER.sub("", g), rename))
            for g in goals]


def observe(lines, names):
    """The normalised observation of one case's output lines."""
    out = []
    for line in lines:
        if line.startswith(("fz_ans(", "fz_wq(", "fz_exc(", "fz_crash(",
                            "fz_timeout", "fz_uncaught(", "fz_syntax(")):
            out.append(canon_fresh(line))
        elif line.endswith(".") and _looks_like_answer(line, names):
            out.append("res" + json.dumps(residuals(line, names)))
        else:
            out.append("out:" + canon_fresh(line))
    return out


def _looks_like_answer(line, names):
    if line in ("true.", "false."):
        return True
    first = split_conjuncts(line[:-1])
    return bool(first) and (bool(_BINDING.match(first[0]))
                            or bool(re.match(r"^(?:\w+:)?(?:dif|freeze|when)\(",
                                             first[0])))


# ── comparing, shrinking, classifying ────────────────────────────────────────

@dataclasses.dataclass
class Result:
    case: Case
    clausal: list
    scryer: list
    raw_clausal: list
    raw_scryer: list

    @property
    def agree(self):
        return self.clausal == self.scryer


def run_cases(runner, cases, *, batch=80, jobs=4):
    """Run *cases* in both systems; a list of :class:`Result`."""
    queries = [(i, c.query(i)) for i, c in enumerate(cases)]
    batches = [queries[k:k + batch] for k in range(0, len(queries), batch)]
    craw, sraw = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futs = {}
        for b in batches:
            futs[pool.submit(runner.clausal, b)] = craw
            futs[pool.submit(runner.scryer, b)] = sraw
        for f in concurrent.futures.as_completed(futs):
            futs[f].update(f.result())
    results = []
    for i, c in enumerate(cases):
        cl = craw.get(i, ["fz_missing"])
        sc = sraw.get(i, ["fz_missing"])
        results.append(Result(c, observe(cl, c.variables),
                              observe(sc, c.variables), cl, sc))
    return results


def _balanced(text):
    depth = 0
    for ch in _strip_quoted(text):
        depth += ch in "([{"
        depth -= ch in ")]}"
        if depth < 0:
            return False
    return depth == 0


def _variants(case):
    """Smaller cases: one goal dropped, or one delayed body cut down."""
    for v in _raw_variants(case):
        if all(_balanced(g) for g in v.goals):
            yield v


def _raw_variants(case):
    goals = case.goals
    for k in range(len(goals)):
        rest = goals[:k] + goals[k + 1:]
        yield Case(rest, _shown(rest, case.variables), case.label)
    for k, g in enumerate(goals):
        for smaller in _shrink_goal(g):
            new = goals[:k] + [smaller] + goals[k + 1:]
            yield Case(new, _shown(new, case.variables), case.label)


def _shrink_goal(goal):
    m = re.match(r"^(freeze\(\w+,|when\(.*?,)\((.*)\)\)$", goal)
    if m:
        parts = split_conjuncts(m.group(2))
        if len(parts) > 1:
            for k in range(len(parts)):
                rest = parts[:k] + parts[k + 1:]
                # bracketed even when one goal is left: a part may hold a
                # top-level ``;``, which an argument cannot
                yield m.group(1) + "(" + ", ".join(rest) + "))"
    m = re.match(r"^when\(\((.*)\),(.*)\)$", goal)
    if m:
        for c in split_conjuncts(m.group(1).replace(";", ",")):
            if c.count("(") == c.count(")"):
                yield f"when({c},{m.group(2)})"


def shrink(runner, result, rounds=12, jobs=4):
    """Drop goals while the two systems still disagree."""
    cur = result
    for _ in range(rounds):
        cands = list(_variants(cur.case))
        if not cands:
            break
        res = run_cases(runner, cands, jobs=jobs)
        smaller = [r for r in res if not r.agree]
        if not smaller:
            break
        cur = min(smaller, key=lambda r: (len(r.case.goal_text()),))
        if len(cur.case.goals) <= 1 and not any(
                True for _ in _shrink_goal(cur.case.goals[0] if cur.case.goals
                                           else "")):
            break
    return cur


# ── the known differences ────────────────────────────────────────────────────
#
# Each kind is (name, class, where it is written down, how).  The class is
# the triage: "documented" -- a deliberate or recorded difference of
# Clausal's; "scryer" -- Scryer answers against ISO or against itself;
# "ruling" -- open, a question in the report.  *how* is either a NORMALISER,
# ``(case, clausal, scryer) -> (clausal', scryer')``, that rewrites away
# exactly that kind of difference (a case is of the kinds whose normalisers,
# applied together, make the two agree -- one difference can stack on
# another), or a TEST on the shrunk result that says the whole difference
# is of its kind.

_ERR_CTX = re.compile(r"^fz_exc\(error\((.*),([^,()]*|[a-z_]+/\d+)\)\)$")


def _strip_err_context(lines):
    out = []
    for line in lines:
        m = _ERR_CTX.match(line)
        out.append(f"fz_exc(error({m.group(1)},_))" if m else line)
    return out


def _n_error_context(case, c, s):
    """Scryer's when/2 raises its errors with the context unbound
    (``error(domain_error(when_condition, C), _)``); Clausal names
    ``when/2``.  ISO leaves the context implementation-defined (7.12.1)."""
    return _strip_err_context(c), _strip_err_context(s)


def _n_dif_wakes_frozen(case, c, s):
    """Scryer's dif/2 binds the variables of its pair to try the
    unification, and a frozen goal on one of them runs (prints) during the
    try; Clausal's trial wakes nothing.  Scryer's extra output lines go."""
    text = case.goal_text()
    if "dif(" not in text or not ("freeze(" in text or "when(" in text):
        return c, s
    return c, _drop_extra_output(c, s)


def _drop_extra_output(c, s, *, repeated_only=False):
    """*s* without the output lines (``out:``) an alignment with *c* leaves
    over (only those that repeat an earlier line, *repeated_only*)."""
    import difflib
    keep = []
    sm = difflib.SequenceMatcher(a=s, b=c, autojunk=False)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        for k in range(i1, i2):
            line = s[k]
            if (tag in ("delete", "replace") and line.startswith("out:")
                    and (not repeated_only or line in s[:k])):
                continue
            keep.append(line)
    return keep


def _map_res(lines, fn):
    out = []
    for line in lines:
        if line.startswith("res["):
            line = "res" + json.dumps(fn(json.loads(line[3:])))
        out.append(line)
    return out


def _n_residual_order(case, c, s):
    """The same residual goals, listed in another order."""
    return _map_res(c, sorted), _map_res(s, sorted)


def _n_freeze_nesting(case, c, s):
    """The freeze goals of aliased variables, one conjunction nested
    differently (``((a,b),c)`` here, ``(a,b,c)`` in Scryer when the
    aliases are made the other way round)."""
    if "freeze(" not in case.goal_text():
        return c, s

    def flat(goals):
        return [g.replace("(", "").replace(")", "") if g.startswith("freeze(")
                else g for g in goals]
    return _map_res(c, flat), _map_res(s, flat)


def _n_when_on_alias(case, c, s):
    """A when/2 waiting on two variables that are then aliased is ONE delay
    here (its goal runs once, prints once, as in SWI-Prolog and SICStus);
    Scryer keeps a copy per variable, prints it twice and runs it twice."""
    if "when(" not in case.goal_text():
        return c, s

    def dedup(goals):
        out = []
        for g in goals:
            if not (g.startswith("when(") and g in out):
                out.append(g)
        return out
    s = _map_res(s, dedup)
    # the goal ran twice in Scryer: a repeated output line goes
    return c, _drop_extra_output(c, s, repeated_only=True)


def _n_dif_trial_runs_frozen(case, c, s):
    """Scryer's dif/2 tries the unification with the frozen goals of its
    variables running, and drops the dif when one of them fails
    (``freeze(A, A = 1), dif(A, f(B))``: no ``dif`` in Scryer's answer);
    Clausal keeps it until a binding decides it.  The answers agree; the
    residual here has a dif more."""
    text = case.goal_text()
    if ("dif(" not in text or not ("freeze(" in text or "when(" in text)
            or len(c) != len(s)):
        return c, s
    out = []
    for a, b in zip(c, s):
        if a != b and a.startswith("res[") and b.startswith("res["):
            ga, gb = json.loads(a[3:]), json.loads(b[3:])
            if all(g in ga for g in gb):
                ga = [g for g in ga if g in gb or not g.startswith("dif(")]
                a = "res" + json.dumps(ga)
        out.append(a)
    return out, s


def _n_cyclic_write(case, c, s):
    """writeq/1 of a cyclic term: where ``...`` stands depends on where the
    cycle is closed in memory, which differs (a copy, findall/3, a cell
    built through a partial list); and Scryer writes ``...`` for a shared
    subterm that closes no cycle at all (``[g(_A)|g(...)]`` for
    ``[g(_A)|g(g(_A))]``, built by ``[B|g(B)] = A, A = [g(D)|C]``).  The
    unfolded terms (``fz_ans``) are compared exactly; a line with a
    ``...`` in it is not."""
    if len(c) != len(s):
        return c, s
    out = [b if (a != b and ("..." in a or "..." in b)
                 and not a.startswith("fz_ans(")) else a
           for a, b in zip(c, s)]
    return out, s


_PARTIAL_STRING = re.compile(r'\|"([a-z]*)"\]')


def _n_scryer_string_tail(case, c, s):
    """Scryer writes a list whose tail is a list of chars with that tail as
    a string (``[C|"a"]``, its partial-string representation); Clausal
    writes the list, ``[C,a]``.  One term."""
    def spell(m):
        return "".join("," + ch for ch in m.group(1)) + "]"

    def fix(text):
        return _PARTIAL_STRING.sub(spell, text)
    s = _map_res(s, lambda goals: [fix(g) for g in goals])
    return c, [ln if ln.startswith("res[") else fix(ln) for ln in s]


_NUMBERED = re.compile(r"(?<![\w'])_\d+")


def _n_attvar_names(case, c, s):
    """Scryer's writeq/1 names one attributed variable two ways inside one
    term (``f([_19983|_19937],_)`` for ``f([X|X],_)`` after a dif/2 on X,
    or a when/2; ``==/2`` says they are one)."""
    text = case.goal_text()
    if not any(k in text for k in ("dif(", "freeze(", "when(")):
        return c, s
    return ([_NUMBERED.sub("_", ln) for ln in c],
            [_NUMBERED.sub("_", ln) for ln in s])


def _n_copy_drops_delays(case, c, s):
    """copy_term/2 (and findall/3's copy) do not copy freeze/2 and when/2
    goals; Scryer copies every attribute, so its answer shows the copies'
    delays too, and a copy bound later runs its goal (prints).  Scryer's
    extra delays and output lines go; an answer that differs stays."""
    text = case.goal_text()
    if not (("copy_term(" in text or "findall(" in text)
            and ("freeze(" in text or "when(" in text)):
        return c, s
    if len(c) == len(s):
        out = []
        for a, b in zip(c, s):
            if a != b and a.startswith("res[") and b.startswith("res["):
                ga, gb = json.loads(a[3:]), json.loads(b[3:])
                gb = [g for g in gb if g in ga
                      or not g.startswith(("freeze(", "when("))]
                b = "res" + json.dumps(gb)
            out.append(b)
        s = out
    return c, _drop_extra_output(c, s)


# A small reader for the generated terms (variables, atoms, f/2, g/1,
# lists), enough to decide where two compared terms first differ.
_TOKEN = re.compile(r"\s*([A-Z_]\w*|[a-z]\w*|\d+|[()\[\],|])")


def _read_term(text):
    toks = _TOKEN.findall(text)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def term():
        t = take()
        if t == "[":
            items = [term()]
            while peek() == ",":
                take()
                items.append(term())
            tail = "[]"
            if peek() == "|":
                take()
                tail = term()
            take()                          # ]
            for e in reversed(items):
                tail = (".", e, tail)
            return tail
        if t[0].isupper() or t[0] == "_":
            return ("$VAR", t)
        if peek() == "(":
            take()
            args = [term()]
            while peek() == ",":
                take()
                args.append(term())
            take()                          # )
            return (t, *args)
        return int(t) if t.isdigit() else t
    return term()


def _decided_by_two_variables(a, b):
    """Whether the standard order of *a* against *b* is first decided by
    two distinct variables (ISO 7.2.1: their order is implementation
    dependent)."""
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if x == y:
            continue
        vx = isinstance(x, tuple) and x[0] == "$VAR"
        vy = isinstance(y, tuple) and y[0] == "$VAR"
        if vx and vy:
            return True
        if vx or vy:
            return False
        if not (isinstance(x, tuple) and isinstance(y, tuple)):
            return False
        if len(x) != len(y) or x[0] != y[0]:
            return False
        stack.extend(reversed(list(zip(x[1:], y[1:]))))
    return False


_COMPARE = re.compile(r"compare\(\w+,(.*)\)$")


def _variable_order(r):
    """compare/3 decided by two variables: ISO 7.2.1 leaves the order of
    variables implementation-dependent (and a goal bound since may still
    hold two variables there)."""
    for g in r.case.goals:
        m = _COMPARE.match(g)
        if not m:
            continue
        parts = split_conjuncts(m.group(1))
        if len(parts) != 2:
            continue
        try:
            if _decided_by_two_variables(_read_term(parts[0]),
                                         _read_term(parts[1])):
                return True
        except (IndexError, ValueError):
            continue
        # a variable bound earlier in the goal: unknown, the parts are the
        # terms as written
        if any(re.match(rf"{p.strip()} = ", h) for h in r.case.goals
               for p in parts if re.fullmatch(r"[A-Z]\w*", p.strip())):
            return True
    return False


def _scryer_list_order(r):
    """Scryer orders a list against a list with another tail (``[a|T]``
    against ``[a]``, ``[a,b]`` against ``[a|c]``) against ISO 7.2.1 (every
    cell is ``'.'/2``, compared argument by argument); Trealla and Clausal
    agree.  Confirmed by running the case in Trealla."""
    text = r.case.goal_text()
    if "compare(" not in text or "[" not in text:
        return False
    return trealla_observation(r.case) == [
        ln for ln in r.clausal if ln.startswith("fz_ans(")]


def trealla_observation(case):
    """The ``fz_ans`` lines of *case* in Trealla, or None."""
    if not os.path.exists(_oracles.TREALLA):
        return None
    with tempfile.TemporaryDirectory() as d:
        prog = Path(d) / "t.pl"
        prog.write_text(":- use_module(library(dif)).\n"
                        ":- use_module(library(freeze)).\n"
                        ":- use_module(library(when)).\n" + PROGRAM)
        goal = f"forall(({case.goal_text()}), fz_show([{','.join(case.variables)}]))"
        try:
            proc = subprocess.run(
                [_oracles.TREALLA, "-q", str(prog), "-g", goal + ", halt"],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return None
    return [canon_fresh(ln.strip()) for ln in proc.stdout.splitlines()
            if ln.startswith("fz_ans(")]


#: The documents each kind of difference is written down in.
_COROUTINING = "docs/coroutining.md"
_ALIAS_ROWS = "tests/iso/test_freeze_alias_merge_scryer.py (CLAUSAL_ONLY_ROWS)"
_COPY_TODO = "todo/copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30.md"
_ISO_REPORT = "docs/iso_prolog_compatibility_report.md"

#: (name, class, where, normaliser) -- applied together, see above.
NORMALISERS = [
    ("copy-drops-freeze-when", "documented", _COPY_TODO,
     _n_copy_drops_delays),
    ("residual-order", "ruling", _COROUTINING, _n_residual_order),
    ("freeze-conjunction-nesting", "documented", _ALIAS_ROWS,
     _n_freeze_nesting),
    ("scryer-error-context", "scryer", _COROUTINING, _n_error_context),
    ("scryer-dif-wakes-frozen-goal", "scryer", _ALIAS_ROWS,
     _n_dif_wakes_frozen),
    ("when-on-alias-runs-once", "documented", _ALIAS_ROWS, _n_when_on_alias),
    ("scryer-dif-trial-runs-frozen-goal", "scryer", _COROUTINING,
     _n_dif_trial_runs_frozen),
    ("cyclic-writeq-ellipsis", "ruling", _ISO_REPORT, _n_cyclic_write),
    ("scryer-string-tail", "scryer", _ISO_REPORT, _n_scryer_string_tail),
    ("scryer-attvar-names", "scryer", _COROUTINING, _n_attvar_names),
]

#: (name, class, where, test) -- each on its own.
TESTS = [
    ("variable-order", "documented", "ISO 7.2.1; " + _ISO_REPORT,
     _variable_order),
    ("scryer-list-order", "scryer", _ISO_REPORT, _scryer_list_order),
]


def classify(result):
    """``(name, class, where)`` of the known difference *result* is -- for
    stacked differences the names joined with ``+`` and the first one's
    class -- or None."""
    for name, kind, where, test in TESTS:
        try:
            if test(result):
                return name, kind, where
        except Exception:  # noqa: BLE001 -- a test that does not apply
            continue
    c, s = list(result.clausal), list(result.scryer)
    used = []
    for name, kind, where, norm in NORMALISERS:
        c2, s2 = norm(result.case, c, s)
        if (c2, s2) != (c, s):
            used.append((name, kind, where))
            c, s = c2, s2
        if c == s:
            break
    if c != s or not used:
        return None
    # the kinds that were needed: drop one that changed nothing the others
    # did not also fix
    needed = []
    for k, item in enumerate(used):
        rest = [u for u in used if u is not item]
        c3, s3 = list(result.clausal), list(result.scryer)
        for name, _kind, _where, norm in NORMALISERS:
            if any(name == u[0] for u in rest):
                c3, s3 = norm(result.case, c3, s3)
        if c3 != s3:
            needed.append(item)
    needed = needed or used[:1]
    return ("+".join(n for n, _, _ in needed), needed[0][1],
            "; ".join(sorted({w for _, _, w in needed})))


# ── the command ──────────────────────────────────────────────────────────────

def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def fuzz(seeds, count, *, workdir, python_twin=False, jobs=4, do_shrink=True,
         log=print):
    """Run the cases of *seeds*; returns (total, [(result, shrunk, known)])."""
    runner = Runner(workdir, python_twin=python_twin)
    cases = [c for s in seeds for c in generate(s, count)]
    results = run_cases(runner, cases, jobs=jobs)
    bad = [r for r in results if not r.agree]
    log(f"{len(cases)} cases, {len(bad)} disagree")
    report = []
    tests = {name for name, *_ in TESTS}
    for r in bad:
        known = classify(r)
        if known and not set(known[0].split("+")) & tests:
            # explained whole by the normalisers: nothing to shrink
            report.append((r, r, known))
            continue
        small = shrink(runner, r, jobs=jobs) if do_shrink else r
        report.append((r, small, classify(small)))
    return len(cases), report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", default="0-9")
    ap.add_argument("--cases", type=int, default=60, help="cases per seed")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--python", action="store_true",
                    help="the pure-Python trampoline")
    ap.add_argument("--no-shrink", action="store_true")
    ap.add_argument("--show", help="SEED:INDEX -- print one case's outputs")
    ap.add_argument("--goal", help="run one goal text in both")
    ap.add_argument("--json", help="write the disagreements here")
    ap.add_argument("--workdir")
    args = ap.parse_args(argv)
    workdir = args.workdir or tempfile.mkdtemp(prefix="fz_")
    if args.show or args.goal:
        if args.goal:
            case = Case([args.goal], _shown([args.goal], list(BASE_VARS) + [
                f"E{i}" for i in range(1, 9)]))
        else:
            s, i = map(int, args.show.split(":"))
            case = generate(s, i + 1)[i]
        runner = Runner(workdir, python_twin=args.python)
        r = run_cases(runner, [case], jobs=1)[0]
        print("goal:   ", case.goal_text())
        print("clausal:", *r.raw_clausal, sep="\n  ")
        print("scryer: ", *r.raw_scryer, sep="\n  ")
        print("agree" if r.agree else "DISAGREE")
        if not r.agree:
            print("clausal:", r.clausal)
            print("scryer: ", r.scryer)
        return 0 if r.agree else 1
    total, report = fuzz(parse_seeds(args.seeds), args.cases, workdir=workdir,
                         python_twin=args.python, jobs=args.jobs,
                         do_shrink=not args.no_shrink)
    unknown = 0
    rows = []
    for full, small, known in report:
        tag = f"known: {known[0]} ({known[1]})" if known else "UNEXPLAINED"
        unknown += not known
        print(f"--- {full.case.label} [{tag}]")
        print("  goal:   ", small.case.goal_text())
        print("  clausal:", small.clausal)
        print("  scryer: ", small.scryer)
        rows.append({"label": full.case.label, "goal": full.case.goal_text(),
                     "shrunk": small.case.goal_text(),
                     "clausal": small.clausal, "scryer": small.scryer,
                     "raw_clausal": small.raw_clausal,
                     "raw_scryer": small.raw_scryer,
                     "known": known[0] if known else None,
                     "class": known[1] if known else None})
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))
    counts: dict = {}
    for _, _, known in report:
        key = f"{known[0]} ({known[1]})" if known else "UNEXPLAINED"
        counts[key] = counts.get(key, 0) + 1
    for key, n in sorted(counts.items()):
        print(f"  {n:5d}  {key}")
    print(f"{total} cases, {len(report)} disagree, {unknown} unexplained")
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
