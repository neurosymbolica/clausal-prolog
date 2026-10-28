"""After a search ends, the query's variables are unbound and reusable.

An answer marked FINAL is reported as the last, but the drivers still pull
the search to its end, so every goal's own backtracking undoes its
bindings, and what a finished search deliberately leaves (an attribute set
by put_attr/3) stays, as on a run without FINAL.  These shapes once left
the last answer's binding on the caller's variable after exhaustion, so a
Python caller reusing the variable lost answers: a catch/3 body, a
conjunction ending in catch/3, a single-clause index bucket, and the query
itself.

Each shape runs through ``solve``, ``solve_with_last`` and ``call``, on
the C trampoline and on the Python twin (a child process with the C
extension blocked).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROGRAM = textwrap.dedent("""\
    q(1).
    q(2).
    cx(a, _).
    cx(b, _).
    cx(c, _).
    cx(k, Y) :- catch(q(Y), _, true).
    cq(Y) :- catch(q(Y), _, true).
    tail(X) :- q(X), catch(true, _, true).
    w(X) :- catch(q(X), _, true), fail.
    tq(X) :- t1(X).
    :- table(t1/1).
    t1(X) :- catch(q(X), _, true).
    """)

#: (name, how): ``solve`` goals are built from the variable X; ``call``
#: rows name a predicate and its arguments.
SHAPES = [
    ("catch_q", "solve", lambda X, E: ("catch", ("q", X), E, "true")),
    ("catch_member", "solve",
     lambda X, E: ("catch", ("member", X, [1, 2, 3]), E, "true")),
    ("q_then_catch", "solve",
     lambda X, E: (",", ("q", X), ("catch", "true", E, "true"))),
    ("bucket_catch", "solve", lambda X, E: ("cx", "k", X)),
    ("pred_catch", "solve", lambda X, E: ("cq", X)),
    ("pred_tail_catch", "solve", lambda X, E: ("tail", X)),
    ("member", "solve", lambda X, E: ("member", X, [1, 2, 3])),
    ("q", "solve", lambda X, E: ("q", X)),
    # nested: what a goal leaves bound is gone before the next goal
    ("findall_then_var", "solve", lambda X, E: (
        ",", ("findall", X, ("cq", X), E), ("var", X))),
    ("forall_then_var", "solve", lambda X, E: (
        ",", ("forall", ("cq", X), "true"), ("var", X))),
    ("failed_catch_then_var", "solve", lambda X, E: (
        ";", (",", ("catch", ("q", X), E, "true"), "fail"), ("var", X))),
    ("failed_pred_then_var", "solve", lambda X, E: (";", ("w", X), ("var", X))),
    ("tabled_catch", "solve", lambda X, E: ("tq", X)),
]
CALLS = [
    ("call_bucket_catch", ("cx", "k")),
    ("call_pred_catch", ("cq",)),
    ("call_tail", ("tail",)),
    ("call_q", ("q",)),
]

_SCRIPT = textwrap.dedent(r"""
    import json, sys
    if sys.argv[1] == "py":
        class _Block:
            def find_spec(self, name, path=None, target=None):
                if name == "clausal.logic.runtime._trampoline":
                    raise ImportError("blocked: run on the Python twin")
                return None
        sys.meta_path.insert(0, _Block())
    sys.path.insert(0, sys.argv[2])
    sys.path.insert(0, sys.argv[3])
    import clausal
    import clausal.import_hook
    from clausal.import_hook import _load_module
    import clausal.logic.trampoline as T
    from clausal.logic.variables import Var, deref, is_var
    import test_final_leaves_no_bindings as t
    mod = _load_module("final_unbound_mod", sys.argv[4])
    out = {"impl": T.StepGenerator.__module__}
    drivers = {
        "solve": lambda g: [None for _ in clausal.solve(g, mod)],
        "solve_with_last": lambda g: [None for _ in clausal.solve_with_last(g, mod)],
    }
    for name, _how, make in t.SHAPES:
        for dname, drive in drivers.items():
            X, E = Var(), Var()
            n = len(drive(make(X, E)))
            unbound = is_var(deref(X))
            again = len(drive(make(X, E))) if unbound else -1
            out[f"{name}/{dname}"] = [n, unbound, again]
    for name, (functor, *pre) in t.CALLS:
        for dname, drive in {"call": clausal.call,
                             "call_with_last": clausal.call_with_last}.items():
            X = Var()
            n = len(list(drive(functor, *pre, X, module=mod)))
            unbound = is_var(deref(X))
            again = len(list(drive(functor, *pre, X, module=mod))) if unbound else -1
            out[f"{name}/{dname}"] = [n, unbound, again]
    print(json.dumps(out))
""")


def _run(which, tmp_path):
    root = Path(__file__).resolve().parent.parent
    prog = tmp_path / "final_unbound.pl"
    prog.write_text(PROGRAM)
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, which, str(root),
         str(Path(__file__).resolve().parent), str(prog)],
        capture_output=True, text=True, timeout=300, cwd=str(root),
        env={**os.environ, "PYTHONWARNINGS": "ignore"})
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


#: answers per shape
_WANT = {"catch_q": 2, "catch_member": 3, "q_then_catch": 2,
         "bucket_catch": 2, "pred_catch": 2, "pred_tail_catch": 2,
         "member": 3, "q": 2, "call_bucket_catch": 2, "call_pred_catch": 2,
         "call_tail": 2, "call_q": 2, "findall_then_var": 1,
         "forall_then_var": 1, "failed_catch_then_var": 1,
         "failed_pred_then_var": 1, "tabled_catch": 2}


@pytest.mark.parametrize("which", ["c", "py"])
def test_variables_are_unbound_after_exhaustion_and_reusable(which, tmp_path):
    got = _run(which, tmp_path)
    impl = got.pop("impl")
    assert impl == ("clausal.logic._trampoline_py" if which == "py"
                    else "_trampoline")
    bad = {k: v for k, v in got.items()
           if v != [_WANT[k.split("/")[0]], True, _WANT[k.split("/")[0]]]}
    assert not bad, bad


def test_an_exhausted_search_leaves_what_its_goals_leave():
    """Reporting a last answer changes nothing about what a search leaves
    on the trail once it is exhausted: the driver pulls the search to its
    end as before, and the goals' own backtracking decides.  put_attr/3,
    which leaves its attribute behind (a Python caller sets up an attributed
    variable this way), still does, as on the base."""
    import clausal
    from clausal.logic.atoms import mint
    from clausal.logic.variables import Trail, Var
    m = clausal.Module("final_residue")
    v, t = Var(), Trail()
    assert len(list(clausal.call("put_attr", v, mint("k"), 7, module=m,
                                 trail=t))) == 1
    got = [1 for _ in clausal.call("get_attr", v, mint("k"), Var(),
                                   module=m, trail=t)]
    assert got == [1]
