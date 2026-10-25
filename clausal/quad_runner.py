"""Run the quads of a file as tests: ``clausal --quads FILE``.

A quad (``clausal.tools.quads``) is a ``?- Query.`` and the answer
description that follows it.  The query runs in the file's own module; its
answers, one at a time, are compared with the description:

* ``X = T`` -- the answer binds exactly the listed variables to terms that
  are variants of ``T`` (variables spell sharing: ``_A``; a query variable
  not listed stays unbound); ``true`` -- an answer binding nothing;
* ``A ; B`` -- the next answer; ``false`` -- no more answers;
* ``...`` or ``ad_infinitum`` -- any further answers are accepted;
* an error term (``instantiation_error``, ``type_error(T, C)``,
  ``error(E, Imp)``, ``throw(Ball)``) -- the next step raises it; variables
  match anything;
* ``V ~~ '14.2000'`` -- a float equal to it up to its digits;
* ``D1 | D2`` -- either description is acceptable;
* ``sto``, ``maybe`` -- accepted without being checked.

``loops``, ``unexpected``, ``other_answer_sequence``, ``waits`` and the
stream annotations are not checked: such a quad is *skipped*, and so is one
with no description.  An answer carrying ``dif/2`` or CLP(FD) constraints
matches only a description with ``maybe``.
"""
from __future__ import annotations

import signal
import sys
from dataclasses import dataclass, field

from clausal.tools.quads import Quad, extract_quads

_UNSUPPORTED = frozenset({
    "loops", "unexpected", "inattendue", "other_answer_sequence", "waits",
    "outputs", "inputs", "peeks"})
_TAIL = frozenset({"...", "ad_infinitum"})
_ERROR_ATOM = "instantiation_error"


class _Timeout(BaseException):
    pass


@dataclass
class Result:
    quad: Quad
    status: str                       # "passed" | "failed" | "skipped"
    detail: str = ""


@dataclass
class Summary:
    results: list = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def ok(self) -> bool:
        return self.count("failed") == 0


# ── the description ───────────────────────────────────────────────────────


@dataclass
class _Answer:
    bindings: dict = field(default_factory=dict)   # name -> expected term
    approx: dict = field(default_factory=dict)     # name -> expected ~~ term
    tail: bool = False
    false: bool = False
    error: object = None
    maybe: bool = False
    unsupported: str = ""


def _flatten(t, op):
    while type(t) is tuple and len(t) == 3 and t[0] == op:
        yield from _flatten(t[1], op)
        t = t[2]
    yield t


def _error_pattern(t):
    """The ball an error element expects, or None when *t* is no error."""
    if t == _ERROR_ATOM:
        return ("error", t, _Wild())
    if type(t) is tuple and t:
        if t[0] == "throw" and len(t) == 2:
            return t[1]
        if t[0] == "error" and len(t) == 3:
            return t
        if t[0] in ("type_error", "domain_error", "syntax_error",
                    "representation_error", "resource_error",
                    "uninstantiation_error", "existence_error",
                    "permission_error", "evaluation_error"):
            return ("error", t, _Wild())
    return None


class _Wild:
    """The implementation-defined second argument of ``error/2``."""


def _answer_of(elements, names_of) -> _Answer:
    """One answer of the description: its conjunction of elements."""
    a = _Answer()
    for e in elements:
        if e == "true":
            continue
        if e == "false":
            a.false = True
        elif type(e) is str and e in _TAIL:
            a.tail = True
        elif e == "sto":
            continue
        elif e == "maybe":
            a.maybe = True
        elif type(e) is str and e in _UNSUPPORTED:
            a.unsupported = e
        elif type(e) is tuple and e and e[0] in _UNSUPPORTED:
            a.unsupported = e[0]
        elif type(e) is tuple and len(e) == 3 and e[0] in ("=", "~~"):
            (a.bindings if e[0] == "=" else a.approx)[names_of(e[1])] = e[2]
        else:
            ball = _error_pattern(e)
            if ball is None:
                a.unsupported = f"unreadable element {e!r}"
            else:
                a.error = ball
    return a


def _alternatives(quad: Quad):
    """The acceptable descriptions of *quad*: a list of answer sequences,
    each ``[_Answer, ...]``, and the first unsupported reason found."""
    from clausal import cli  # noqa: PLC0415

    alts = []
    for term, names in quad.descriptions:
        for alt in _flatten(term, "|"):
            goal, variables = cli._lower_term(alt)
            by_var = {id(v): names.get(i, f"_G{i}")
                      for i, v in variables.items()}
            seq = [_answer_of(list(_flatten(ans, ",")),
                              lambda v, by=by_var: by.get(id(v), "?"))
                   for ans in _flatten(goal, ";")]
            alts.append((seq, {names.get(i, f"_G{i}"): v
                               for i, v in variables.items()}))
    alts_seq = [a for a in alts]
    return alts_seq


# ── the actual answers ────────────────────────────────────────────────────


class _Actual:
    """The query's answers, computed one at a time and remembered."""

    def __init__(self, module, quad: Quad, op_names):
        from clausal import cli, solve  # noqa: PLC0415

        goal, variables = cli._lower_term(quad.query)
        self.names = [(quad.names.get(i, f"_G{i}"), v)
                      for i, v in variables.items()]
        self.shown = [(n, v) for n, v in self.names if not n.startswith("_")]
        self._it = iter(solve(("call", goal), module=module))
        self.items: list = []          # ("answer", ...) | ("end",) | ("error", ball)
        self.done = False

    def get(self, i: int):
        from clausal import cli  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.solve import _deref_walk  # noqa: PLC0415

        while len(self.items) <= i:
            if self.done:
                return self.items[-1]
            try:
                trail = next(self._it)
            except StopIteration:
                self.items.append(("end",))
                self.done = True
            except LogicException as exc:
                self.items.append(("error", _deref_walk(exc.term)))
                self.done = True
            else:
                values = {n: _deref_walk(v) for n, v in self.shown}
                self.items.append(("answer", values,
                                   cli._answer(self.shown, trail),
                                   _has_residual(self.shown)))
        return self.items[i]


def _has_residual(shown) -> bool:
    from clausal import cli  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    free: dict = {}
    for _, v in shown:
        cli._term_vars(_deref_walk(v), free)
    return bool(cli._fd_dif_residuals(list(free.values()), str))


# ── comparing ─────────────────────────────────────────────────────────────


def _canon(values: list) -> str:
    """*values* written with their variables named by first occurrence, so
    two terms are variants exactly when their texts are equal."""
    from clausal import cli  # noqa: PLC0415
    from clausal.terms import term_writeq  # noqa: PLC0415
    tup = ("v", 0, *values)
    free: dict = {}
    cli._term_vars(tup, free)
    names = {k: f"_V{n}" for n, k in enumerate(free)}
    return term_writeq(tup, var_names=names)


def _match_pattern(p, a, env) -> bool:
    """*p* (variables are wildcards, bound consistently) against the actual
    ball *a*."""
    from clausal.logic.variables import Var  # noqa: PLC0415
    if isinstance(p, _Wild):
        return True
    if isinstance(p, Var):
        if id(p) in env:
            return _canon([env[id(p)]]) == _canon([a])
        env[id(p)] = a
        return True
    if type(p) is tuple:
        return (type(a) is tuple and len(a) == len(p)
                and all(_match_pattern(x, y, env) for x, y in zip(p, a)))
    if type(p) is list:
        return (type(a) is list and len(a) == len(p)
                and all(_match_pattern(x, y, env) for x, y in zip(p, a)))
    return p == a and type(p) is type(a)


def _approx_ok(actual, expected) -> bool:
    text = expected if type(expected) is str else repr(expected)
    try:
        want = float(text)
    except ValueError:
        return False
    if type(actual) is not float:
        return False
    decimals = len(text.split(".")[1]) if "." in text else 0
    return abs(actual - want) <= 0.5 * 10.0 ** -decimals


def _check_answer(actual, ans: _Answer, expvars: dict, qnames) -> str:
    """"" when the actual answer *actual* matches *ans*, else why not."""
    from clausal.logic.variables import Var  # noqa: PLC0415
    _, values, _text, residual = actual
    if residual and not ans.maybe:
        return "the answer has residual constraints (the description lacks `maybe`)"
    exp_vals, act_vals = [], []
    for name in qnames:
        a = values[name]
        if name in ans.approx:
            if not _approx_ok(a, ans.approx[name]):
                return f"{name} = {a!r} is not ~~ {ans.approx[name]!r}"
            continue
        act_vals.append(a)
        if name in ans.bindings:
            exp_vals.append(ans.bindings[name])
        else:
            exp_vals.append(expvars.setdefault(name, Var()))
    if _canon(act_vals) != _canon(exp_vals):
        return "the bindings differ"
    return ""


def _run_alternative(actual: _Actual, seq, expvars) -> str:
    """"" if the actual answers fit the sequence *seq*, else why not."""
    qnames = [n for n, _ in actual.shown]
    for i, ans in enumerate(seq):
        if ans.unsupported:
            return f"unsupported:{ans.unsupported}"
        if ans.false and not ans.bindings:
            item = actual.get(i)
            return "" if item[0] == "end" else _unexpected(item, "no answer")
        if ans.tail and not ans.bindings and ans.error is None:
            return ""
        item = actual.get(i)
        if ans.error is not None:
            if item[0] != "error":
                return _unexpected(item, "an error")
            if _match_pattern(ans.error, item[1], {}):
                return ""
            return f"raised {_show(item[1])}"
        if item[0] != "answer":
            return _unexpected(item, "an answer")
        why = _check_answer(item, ans, expvars, qnames)
        if why:
            return f"answer {i + 1}: {item[2]}: {why}"
        if ans.tail:
            return ""
    item = actual.get(len(seq))
    if item[0] == "end":
        return ""
    return _unexpected(item, "no further answer")


def _show(t) -> str:
    from clausal.terms import term_writeq  # noqa: PLC0415
    return term_writeq(t)


def _unexpected(item, wanted: str) -> str:
    if item[0] == "end":
        return f"expected {wanted}, the query has no more answers"
    if item[0] == "error":
        return f"expected {wanted}, got the error {_show(item[1])}"
    return f"expected {wanted}, got the answer {item[2]}"


# ── running ───────────────────────────────────────────────────────────────


def run_quad(module, quad: Quad, op_names=None, timeout: float = 10.0) -> Result:
    if not quad.descriptions:
        return Result(quad, "skipped", "no answer description")
    alts = _alternatives(quad)

    def alarm(signum, frame):
        raise _Timeout()

    old = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        actual = _Actual(module, quad, op_names)
        reasons = []
        for seq, expvars in alts:
            why = _run_alternative(actual, seq, dict(expvars))
            if not why:
                return Result(quad, "passed")
            reasons.append(why)
        if all(r.startswith("unsupported:") for r in reasons):
            return Result(quad, "skipped", reasons[0].split(":", 1)[1] + " is not checked")
        return Result(quad, "failed", " | ".join(reasons))
    except _Timeout:
        return Result(quad, "failed", f"no answer within {timeout:g} s")
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001
        from clausal import cli  # noqa: PLC0415
        return Result(quad, "failed", f"raised {cli._describe(exc)}")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def run_quads(module, source: str, op_table, filename: str = "<quads>",
              out=None, timeout: float = 10.0) -> Summary:
    """Run every quad of *source* in *module*; print failures and a
    summary line to *out*."""
    out = out or sys.stdout
    summary = Summary()
    for quad in extract_quads(source, op_table):
        res = run_quad(module, quad, timeout=timeout)
        summary.results.append(res)
        if res.status == "failed":
            label = f" ({quad.label})" if quad.label else ""
            out.write(f"{filename}:{quad.line}: quad failed{label}: "
                      f"{res.detail}\n")
    out.write(f"quads: {len(summary.results)} found, "
              f"{summary.count('passed')} passed, "
              f"{summary.count('failed')} failed, "
              f"{summary.count('skipped')} skipped\n")
    return summary
