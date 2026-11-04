"""A LARGE predicate's dispatch: a clause table walked by one generic driver.

Compiling a predicate makes one Python function holding a match arm per
clause, plus one function per first-argument (and second-argument) index
bucket.  Generating and compiling that code costs about a millisecond per
clause per function, so a predicate of thousands of clauses -- a fact
table asserted at run time, or loaded from a file -- took seconds to tens
of seconds to compile, at its load or at its first call after an assert
(todo/done/dynamic-predicate-first-call-after-many-asserts-is-super-linear-
2026-11-04.md).

From :data:`CLAUSE_TABLE_THRESHOLD` clauses on, a predicate is compiled
here instead, into a table:

* a FACT whose head is plain data (atoms, integers, floats, compound
  terms, lists and strings of those, variables) is kept as data: its head
  arguments as a term (``clause_ops.clause_terms``, the term clause/2
  reads), unified with the call's arguments left to right, renamed first
  when it has variables;
* any other clause (a rule, or a fact with a head the table does not
  hold as data) is compiled by the ordinary compiler as a predicate of its
  own one clause, and the driver delegates to it (``yield from``).  A cut
  in it leaves the whole predicate, as in the one-function compile: the
  clause function yields ``(_fail, DONE)`` and is never resumed.

A predicate whose clauses are all facts is compiled here from
:data:`FACT_TABLE_THRESHOLD` clauses: compiled, each fact cost a clause arm
in the one function and another in its index bucket, about 3 ms each at
arity 8, so loading 255 such facts took 2 s (9 s before an index position
whose clauses all have one key stopped compiling a copy of the predicate).
And a fact predicate of fewer clauses is compiled here once it has been
recompiled after a clause write :data:`RECOMPILES_BEFORE_TABLE` times: a
fact table filled by assertz between calls, which recompiled (all of it,
through the code generator) at each call, so that n asserts cost O(n^2)
compiled clauses -- 50 facts of arity 8 took 30 s (2026-11-04).

The driver tries the clauses in order, over the table built at the compile.
An assertz of a fact the table holds as data adds it to the table in place
(``table_append``) instead of invalidating the dispatch; any other write (an
asserta, a retract, a rule) invalidates it, and the next call recompiles.
The logical update view holds either way: a call reads only the clauses
the table had when it began, and one already running when the dispatch is
invalidated keeps the table it started with.  A call
whose argument at an indexed position is bound tries only the clauses
whose head can match it there (a dict from argument key to clause indices,
``arg_index._runtime_arg_key`` / ``_extract_arg_key``, as the compiled
indexing keys them), the most selective bound position chosen per call.
An answer is ``FINAL`` when no candidate clause is left after it.

Answers and their order are the one-function compile's.  What differs, in
cases no answer shows: the order in which one fact's head binds the call's
variables (left to right here; the compiler orders its head tests by
kind), so the order of goals those bindings wake; no tail-recursion
optimisation; and FINAL (the top level's "no more answers") detected per
indexed position, not per pair of positions.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left
from itertools import islice
from types import FunctionType
from typing import Any, Callable

from clausal.logic.cells import CHARS_TAG
from clausal.logic.trampoline import DONE, FINAL
from clausal.logic.variables import deref, is_var, unify

#: Clauses from which a predicate compiles to a table (see the module
#: docstring).  Below it the one-function compile is kept as it was.
CLAUSE_TABLE_THRESHOLD = 256

#: Clauses from which a predicate whose clauses are all facts compiles to a
#: table.  Its load (or first call) then costs about a microsecond per head
#: argument instead of milliseconds per compiled clause arm, and a call
#: costs about what the compiled code's does.
FACT_TABLE_THRESHOLD = 16

#: Recompiles after a clause write (``Database.get_dispatch``'s lazy
#: recompile) from which a predicate whose clauses are all facts compiles
#: to a table whatever its size.  The first such recompile still goes
#: through the code generator: a predicate asserted to once, before its
#: calls, keeps its compiled code.
RECOMPILES_BEFORE_TABLE = 2

_END = object()

#: The most nodes :func:`_plain` walks in one head argument.
_PLAIN_NODES = 100_000


def use_clause_table(db, clauses, enabled_optimisations,
                     functor: "str | None" = None, arity: int = 0) -> bool:
    """Compile *clauses* as a table?  Only a database's predicate (its
    clauses can be read back as terms), only a default compile (a caller
    narrowing the optimisations compares the generated code), and only from
    :data:`CLAUSE_TABLE_THRESHOLD` clauses -- or, when every clause is a
    fact, from :data:`FACT_TABLE_THRESHOLD` clauses, or from the predicate
    *functor*/*arity*'s :data:`RECOMPILES_BEFORE_TABLE`-th recompile after
    a clause write."""
    if db is None or enabled_optimisations is not None:
        return False
    if len(clauses) >= CLAUSE_TABLE_THRESHOLD:
        return True
    if not all(c.body[c.hoisted:] in ([], [True]) for c in clauses):
        return False
    if len(clauses) >= FACT_TABLE_THRESHOLD:
        return True
    if functor is None:
        return False
    row = db.row(functor, arity)
    return (row is not None
            and row.recompiles_after_write >= RECOMPILES_BEFORE_TABLE)


def _plain(term: Any) -> bool:
    """Is *term* data the table can unify as it is: an atom, an integer, a
    float, an unbound variable, a compound or string cell, a list, built of
    those only?  Anything else -- a partial list (``SegList``), a dict, a
    set, a Python object, another number kind -- keeps its clause compiled.
    So does a head of more than ``_PLAIN_NODES`` nodes: the walk is bounded
    (a stored clause is never cyclic -- assertz refuses one -- but a cycle
    must not hang a compile)."""
    stack = [term]
    budget = _PLAIN_NODES
    while stack:
        budget -= 1
        if budget < 0:
            return False
        t = deref(stack.pop())
        tt = type(t)
        if tt is str or tt is int or tt is float:
            continue
        if is_var(t):
            continue
        if tt is tuple:
            if len(t) < 2 or type(t[0]) is not str:
                return False
            if t[0] == CHARS_TAG:
                if len(t) != 2 or type(t[1]) is not str:
                    return False
                continue
            stack.extend(t[1:])
            continue
        if tt is list:
            stack.extend(t)
            continue
        return False
    return True


def _ground(args: tuple) -> bool:
    """Are the plain head arguments *args* free of variables?"""
    stack = list(args)
    while stack:
        t = deref(stack.pop())
        if is_var(t):
            return False
        if type(t) is tuple:
            stack.extend(t[1:])
        elif type(t) is list:
            stack.extend(t)
    return True


def fact_arguments(clause, db, arity: int):
    """The head arguments of *clause* as a tuple of terms when it is a fact
    the table holds as data (see :func:`_plain`), else None."""
    from clausal.logic.builtins.clause_ops import clause_terms  # noqa: PLC0415
    if clause.body[clause.hoisted:] not in ([], [True]):
        return None
    head, _body, why = clause_terms(clause, db)
    if why is not None:
        return None
    head = deref(head)
    if arity == 0:
        return () if type(head) is str else None
    if type(head) is not tuple or len(head) != arity + 1:
        return None
    args = head[1:]
    return args if all(_plain(a) for a in args) else None


def build_table_dispatch(
    functor: str,
    arity: int,
    clauses: list,
    compile_clauses: list,
    db,
    compile_clause: Callable[[Any, int, bool], Callable],
    *,
    final_answers: bool = True,
    env: "dict | None" = None,
) -> Callable:
    """The dispatch function of the predicate *functor*/*arity* with
    *clauses* (as stored, read back as terms) and *compile_clauses* (the
    same clauses as the compiler reads them, one for one).

    ``compile_clause(clause, i, last)`` compiles clause *i* that is not
    held as data into a one-clause function (``emit_done=False``) whose
    answers are FINAL only when *last* (no clause follows it).
    *final_answers* False: no answer is FINAL (the ``final_yield``
    optimisation is off)."""
    from clausal.logic.builtins.inspection import _copy_term  # noqa: PLC0415
    from .arg_index import (  # noqa: PLC0415
        _INDEX_VAR, _extract_arg_key, _runtime_arg_key)

    n = len(clauses)
    # One entry per clause: a fact's ``(args, ground)``, or a clause
    # function.  Both lists only ever grow (``append`` below), and a call
    # reads only the first ``len(facts)`` entries there were when it began.
    facts: list = [None] * n
    fns: list = [None] * n
    for i, (src, cl) in enumerate(zip(clauses, compile_clauses)):
        args = fact_arguments(src, db, arity)
        if args is not None:
            facts[i] = (args, _ground(args))
        else:
            fns[i] = compile_clause(cl, i, i == n - 1)

    # Index: per argument position, key -> indices of the clauses whose
    # head has that key there (ascending), and the indices of those whose
    # head can match any key (a variable, or no key).  A position is used
    # once it has two keys or more.
    index: list = []
    for pos in range(arity):
        specific: dict = {}
        defaults: list = []
        for i in range(n):
            if facts[i] is not None:
                k = _fact_key(facts[i][0][pos])
            else:
                k = _extract_arg_key(compile_clauses[i], pos, arity, env)
            _add_key(specific, defaults, k, i)
        index.append((pos, specific, defaults))
    # The positions in use.
    plans = [entry for entry in index if len(entry[1]) >= 2]

    def candidates(call_args, n0):
        """The indices below *n0* of the clauses that can match
        *call_args*, ascending."""
        best = None
        best_count = n0
        for pos, specific, defaults in plans:
            a = deref(call_args[pos])
            if is_var(a):
                continue
            k = _runtime_arg_key(a, False)
            if k is _INDEX_VAR:
                continue
            try:
                hit = specific.get(k, ())
            except TypeError:
                continue
            nh = _below(hit, n0)
            nd = _below(defaults, n0)
            count = nh + nd
            if count < best_count:
                best, best_count = (hit, nh, defaults, nd), count
        if best is None:
            return range(n0)
        hit, nh, defaults, nd = best
        # Bounded even when nothing is past *n0* yet: the lists are live,
        # and a clause appended while the call runs must not reach it.
        hit = islice(hit, nh)
        defaults = islice(defaults, nd)
        if not nd:
            return hit
        if not nh:
            return defaults
        return heapq.merge(hit, defaults)

    def dispatch(this_generator, _proceed, _fail, _catcher, *rest):
        trail = rest[-1]
        call_args = rest[:-1]
        if arity == 1:
            c0 = call_args[0]
        elif arity == 2:
            c0, c1 = call_args
        it = iter(candidates(call_args, len(facts)))
        nxt = next(it, _END)
        while nxt is not _END:
            i = nxt
            nxt = next(it, _END)
            fact = facts[i]
            if fact is None:
                # A cut in the clause yields ``(_fail, DONE)``: this
                # generator is not resumed after it (a compiled predicate's
                # own cut exit relies on the same).
                yield from fns[i](this_generator, _proceed, _fail, _catcher,
                                  *rest)
                continue
            args, ground = fact
            if not ground:
                args = _copy_term(args, {})
            mark = trail.mark()
            closed = False
            try:
                if arity == 1:
                    ok = unify(c0, args[0], trail)
                elif arity == 2:
                    ok = (unify(c0, args[0], trail)
                          and unify(c1, args[1], trail))
                else:
                    ok = True
                    for a, t in zip(call_args, args):
                        if not unify(a, t, trail):
                            ok = False
                            break
                if ok:
                    yield (_proceed,
                           FINAL if nxt is _END and final_answers else None)
            except GeneratorExit:
                # Closed after an answer (once/1, a cut): its bindings are
                # the caller's now -- as a compiled clause arm leaves them.
                closed = True
                raise
            finally:
                if not closed:
                    trail.undo(mark)
        yield (_fail, DONE)

    def append(clause) -> "Callable | None":
        """Add *clause* (just assertz'd: stored after every clause this
        table holds) to the table in place, and return the dispatch to
        install, a new function over the same table -- or None, when it
        has to be recompiled instead: *clause* is not a fact held as data,
        or the last clause is compiled, its answers FINAL as the last."""
        if fns and fns[-1] is not None and final_answers:
            return None
        args = fact_arguments(clause, db, arity)
        if args is None:
            return None
        i = len(facts)
        for pos, specific, defaults in index:
            _add_key(specific, defaults, _fact_key(args[pos]), i)
        if len(plans) < arity:
            plans[:] = [entry for entry in index if len(entry[1]) >= 2]
        fns.append(None)
        facts.append((args, _ground(args)))     # last: what a call counts
        return _named(FunctionType(
            dispatch.__code__, dispatch.__globals__, dispatch.__name__,
            dispatch.__defaults__, dispatch.__closure__))

    def _named(fn):
        fn.__name__ = fn.__qualname__ = f"{functor}__{arity}"
        fn.table_append = append
        return fn

    return _named(dispatch)


def _fact_key(a):
    """The index key of a fact's head argument *a*."""
    from .arg_index import _INDEX_VAR, _runtime_arg_key  # noqa: PLC0415
    a = deref(a)
    return _INDEX_VAR if is_var(a) else _runtime_arg_key(a, False)


def _add_key(specific: dict, defaults: list, k, i: int) -> None:
    """File clause *i* under key *k* of one position's index."""
    from .arg_index import _INDEX_VAR  # noqa: PLC0415
    if k is _INDEX_VAR:
        defaults.append(i)
        return
    try:
        specific.setdefault(k, []).append(i)
    except TypeError:
        defaults.append(i)


def _below(indices, n0: int) -> int:
    """How many of the ascending *indices* are below *n0*."""
    if not indices or indices[-1] < n0:
        return len(indices)
    return bisect_left(indices, n0)

