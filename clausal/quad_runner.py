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
  ``error(E, Imp)``, ``throw(Ball)``) -- the next step raises it; ``Imp``
  matches anything, the rest as a variant;
* ``V ~~ '14.2000'`` -- a float equal to it up to its digits;
* ``D1 | D2`` -- either description is acceptable; a quad with several
  descriptions needs all of them to hold;
* ``maybe``, or the pending goals themselves (``dif(X, a)``, ``X in 4..5``)
  -- the answer has a constraint pending; without one of these an answer with
  a pending constraint does not match, and with one an answer with none does
  not either;
* ``X = f(...)`` -- ``...`` is any subterm; ``unexpected`` -- this answer must
  not be the one given at that point (nothing is claimed after it);
* ``outputs(Text)`` -- what the query wrote while computing that answer;
* ``sto`` -- accepted, not checked (an occurs-check binding cannot be
  described: such a cyclic answer is not matched).

``loops``, ``other_answer_sequence``, ``waits``, ``inputs/1`` and ``peeks/1``
are not checked: such a quad is *skipped*, and so is one with no description.
Modelled on Trealla's ``library/quads.pl`` (v3.14), which it differs from:
``sto`` is accepted but not checked, a cyclic answer is not matched, and a
label is an atom.
"""
from __future__ import annotations

import contextlib
import io
import signal
import sys
import threading
from dataclasses import dataclass, field

from clausal.tools.quads import Quad, extract_quads

_UNSUPPORTED = frozenset({
    "loops", "other_answer_sequence", "waits", "inputs", "peeks"})
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
    unexpected: bool = False
    outputs: object = None
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


def _is_residual(e) -> bool:
    from clausal.tools.quads import RESIDUAL_GOALS  # noqa: PLC0415
    return (type(e) is tuple and bool(e) and type(e[0]) is str
            and (e[0], len(e) - 1) in RESIDUAL_GOALS)


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
        elif e == "maybe" or _is_residual(e):
            a.maybe = True
        elif e in ("unexpected", "inattendue"):
            a.unexpected = True
        elif type(e) is tuple and len(e) == 2 and e[0] == "outputs":
            a.outputs = e[1]
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
    """The descriptions of *quad*, each ``[(sequence, expected_vars), ...]``:
    its acceptable alternatives (``|``), each a list of ``_Answer`` s."""
    from clausal import cli  # noqa: PLC0415

    descriptions = []
    for term, names in quad.descriptions:
        alts = []
        for alt in _flatten(term, "|"):
            goal, variables = cli._lower_term(alt)
            by_var = {id(v): names.get(i, f"_G{i}")
                      for i, v in variables.items()}
            seq = [_answer_of(list(_flatten(ans, ",")),
                              lambda v, by=by_var: by.get(id(v), "?"))
                   for ans in _flatten(goal, ";")]
            alts.append((seq, {names.get(i, f"_G{i}"): v
                               for i, v in variables.items()}))
        descriptions.append(alts)
    return descriptions


# ── the actual answers ────────────────────────────────────────────────────


class _Actual:
    """The query's answers, computed one at a time and remembered."""

    def __init__(self, module, quad: Quad):
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
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
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
                                   _has_residual(self.shown),
                                   buf.getvalue()))
        return self.items[i]


def _has_residual(shown) -> bool:
    from clausal import cli  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    free: dict = {}
    for _, v in shown:
        cli._term_vars(_deref_walk(v), free)
    variables = list(free.values())
    return bool(cli._fd_dif_residuals(variables, str)
                or cli._coroutine_residuals(variables, str))


# ── comparing ─────────────────────────────────────────────────────────────


def _normalise(t, depth=0):
    """*t* with each partial list, however spelled (the engine's ``SegList``,
    or the ``[a, *Tail]`` the reader lowers ``[a|Tail]`` to), as the same
    ``('$partial', Element..., ('$hole', Var))``, so two terms compare as
    text."""
    from clausal.pythonic_ast.nodes import StarUnpack  # noqa: PLC0415
    from clausal.terms import SegList, VarSeg  # noqa: PLC0415
    if depth > 200:
        return t
    if isinstance(t, SegList):
        parts = []
        for seg in t.segments:
            if isinstance(seg, VarSeg):
                parts.append(("$hole", seg.var))
            else:
                parts.extend(_normalise(e, depth + 1) for e in seg.elements)
        return ("$partial", *parts)
    if type(t) is list:
        if any(isinstance(x, StarUnpack) for x in t):
            return ("$partial", *[
                ("$hole", x.value) if isinstance(x, StarUnpack)
                else _normalise(x, depth + 1) for x in t])
        return [_normalise(x, depth + 1) for x in t]
    if type(t) is tuple and t and t[0] != "$chars":
        return (t[0], *(_normalise(x, depth + 1) for x in t[1:]))
    return t


def _canon(values: list) -> str:
    """*values* written with their variables named by first occurrence, so
    two terms are variants exactly when their texts are equal."""
    from clausal import cli  # noqa: PLC0415
    from clausal.terms import term_writeq  # noqa: PLC0415
    tup = ("v", 0, *(_normalise(v) for v in values))
    free: dict = {}
    cli._term_vars(tup, free)
    names = {k: f"_V{n}" for n, k in enumerate(free)}
    return term_writeq(tup, var_names=names)


def _match_pattern(p, a, env) -> bool:
    """*p* against the actual term *a*, where ``...`` is any subterm and a
    variable of *p* matches anything, consistently (*env*)."""
    from clausal.logic.variables import Var  # noqa: PLC0415
    if isinstance(p, _Wild) or p == "...":
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


def _match_ball(p, a) -> bool:
    """The error an element describes against the ball raised: the context
    (the second argument of ``error/2``) is implementation defined and
    matches anything; the rest is matched as a variant, as in Trealla."""
    from clausal.logic.variables import Var  # noqa: PLC0415
    if type(p) is tuple and len(p) == 3 and p[0] == "error":
        if not (type(a) is tuple and len(a) == 3 and a[0] == "error"):
            return False
        return _canon([p[1]]) == _canon([a[1]]) and (
            isinstance(p[2], (_Wild, Var)) or _canon([p[2]]) == _canon([a[2]]))
    return _canon([p]) == _canon([a])


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


def _contains_dots(t) -> bool:
    if t == "...":
        return True
    if type(t) in (tuple, list):
        return any(_contains_dots(x) for x in t)
    return False


def _outputs_text(spec) -> str:
    """The text an ``outputs/1`` argument names: a string, an atom or a
    list of characters."""
    if type(spec) is tuple and len(spec) == 2 and spec[0] == "$chars":
        return spec[1]
    if type(spec) is list:
        return "".join(x for x in spec if type(x) is str)
    return spec if type(spec) is str else ""


def _check_answer(actual, ans: _Answer, expvars: dict, qnames) -> str:
    """"" when the actual answer *actual* matches *ans*, else why not."""
    from clausal.logic.variables import Var  # noqa: PLC0415
    _, values, _text, residual, output = actual
    for name in (*ans.bindings, *ans.approx):
        if name not in qnames:
            return f"{name} is no variable of the query"
    if ans.outputs is not None and output != _outputs_text(ans.outputs):
        return f"the query wrote {output!r}, not {_outputs_text(ans.outputs)!r}"
    if residual and not ans.maybe:
        return "the answer has residual constraints (the description lacks `maybe`)"
    if ans.maybe and not residual:
        return "the description says `maybe`, but nothing is pending"
    exp_vals, act_vals = [], []
    for name in qnames:
        a = values[name]
        if name in ans.approx:
            if not _approx_ok(a, ans.approx[name]):
                return f"{name} = {a!r} is not ~~ {ans.approx[name]!r}"
            continue
        if name in ans.bindings and _contains_dots(ans.bindings[name]):
            if not _match_pattern(ans.bindings[name], a, {}):
                return f"{name} does not match"
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
        if ans.unexpected:
            if item[0] == "answer" and not _check_answer(
                    item, ans, expvars, qnames):
                return f"answer {i + 1}: {item[2]} occurs but is unexpected"
            return ""
        if ans.error is not None:
            if item[0] != "error":
                return _unexpected(item, "an error")
            if _match_ball(ans.error, item[1]):
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


def run_quad(module, quad: Quad, timeout: float = 10.0) -> Result:
    """Run one quad; the limit *timeout* is for this quad alone."""
    try:
        return _run_quad(module, quad, timeout)
    except _Timeout:        # an alarm in the unwinding of _run_quad itself
        return Result(quad, "failed", f"no answer within {timeout:g} s")


def _run_quad(module, quad: Quad, timeout: float) -> Result:
    if not quad.descriptions:
        return Result(quad, "skipped", "no answer description")
    descriptions = _alternatives(quad)

    # SIGALRM bounds a query that never answers; where the platform has
    # none (Windows), or off the main thread, the query runs without a limit.
    timed = (hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
             and threading.current_thread() is threading.main_thread())
    old = None

    def alarm(signum, frame):
        signal.setitimer(signal.ITIMER_REAL, 0)     # once: nothing fires again
        raise _Timeout()

    try:
        if timed:
            old = signal.signal(signal.SIGALRM, alarm)
            signal.setitimer(signal.ITIMER_REAL, timeout)
        actual = _Actual(module, quad)
        skipped = ""
        for alts in descriptions:           # every description must hold
            reasons = []
            for seq, expvars in alts:       # any alternative will do
                why = _run_alternative(actual, seq, dict(expvars))
                if not why:
                    reasons = []
                    break
                reasons.append(why)
            if not reasons:
                continue
            if all(r.startswith("unsupported:") for r in reasons):
                skipped = reasons[0].split(":", 1)[1] + " is not checked"
                continue
            return Result(quad, "failed", " | ".join(
                r.split(":", 1)[1] + " is not checked"
                if r.startswith("unsupported:") else r for r in reasons))
        if skipped:
            return Result(quad, "skipped", skipped)
        return Result(quad, "passed")
    except _Timeout:
        return Result(quad, "failed", f"no answer within {timeout:g} s")
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001
        from clausal import cli  # noqa: PLC0415
        return Result(quad, "failed", f"raised {cli._describe(exc)}")
    finally:
        if timed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old is not None:
                signal.signal(signal.SIGALRM, old)


def run_quads(module, source: str, op_table, filename: str = "<quads>",
              out=None, timeout: float = 10.0) -> Summary:
    """Run every quad of *source* in *module*; print failures and a
    summary line to *out*."""
    out = out or sys.stdout
    summary = Summary()
    from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES  # noqa: PLC0415
    from clausal.toplevel import _uses_control  # noqa: PLC0415

    clausal_file = filename.endswith(CLAUSAL_PROLOG_SUFFIXES)
    for quad in extract_quads(source, op_table):
        if clausal_file and _uses_control(quad.query):
            # as the ?- top-level refuses them against a .clausal file
            res = Result(quad, "failed",
                         "error(syntax_error(cut_free),read_term/3): !, -> "
                         "and *-> are not Clausal Prolog")
        else:
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
