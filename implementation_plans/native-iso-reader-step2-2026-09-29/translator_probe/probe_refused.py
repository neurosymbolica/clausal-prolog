"""Re-measure Audit 3's 'Refused or missing' row on the OLD .pl path, one construct per file.
Run from the worktree root. Prints LOAD/QUERY outcome per construct."""
import sys, os, importlib, pathlib, shutil, tempfile, warnings
warnings.filterwarnings("ignore")
ROOT = os.getcwd(); sys.path.insert(0, ROOT)
import clausal; assert clausal.__file__.startswith(ROOT)
from clausal.logic.solve import query
from clausal.logic.variables import Var
tmp = pathlib.Path(tempfile.mkdtemp()); sys.path.insert(0, str(tmp))
CASES = {
 "data compound":  ("t(X) :- X = pt(1, 2).", None),
 "cut":            ("t(X) :- member(X, [1,2]), !.", None),
 "if-then-else":   ("t(X) :- ( 1 > 0 -> X = y ; X = n ).", None),
 "clpz #=":        ("t(X) :- X #= 3 + 4.", ":- use_module(library(clpz))."),
 "clpz in/label":  ("t(X) :- X in 0..5, X #> 3, label([X]).", ":- use_module(library(clpz))."),
 "clpq {}":        ("t(X) :- {X = 2 * 3}.", ":- use_module(library(clpq))."),
 "reif if_":       ("t(X) :- if_(1 = 1, X = y, X = n).", ":- use_module(library(reif))."),
 "@<":             ("t(X) :- X = a, X @< b.", None),
 "compare/3":      ("t(X) :- compare(X, 1, 2).", None),
 "yall lambda":    ("t(X) :- maplist([Y]>>(Y > 0), [1,2]), X = ok.", ":- use_module(library(yall))."),
 "aggregate_all":  ("t(X) :- aggregate_all(count, member(_, [a,b]), X).", None),
 "nth1":           ("t(X) :- nth1(2, [a,b], X).", None),
 "keysort":        ("t(X) :- keysort([2-b, 1-a], X).", None),
 "atom_number":    ("t(X) :- atom_number('3', X).", None),
 "format/3":       ("t(X) :- format(atom(X), \"~w\", [1]).", None),
 "string chars":   ("t(X) :- X = \"ab\", X = [a|_].", None),
 "succ_or_zero":   ("t(X) :- length([a,b], X).", None),
 "initialization": ("t(ok).", ":- initialization(t(_))."),
 "set_prolog_flag":("t(X) :- current_prolog_flag(double_quotes, X).", ":- set_prolog_flag(double_quotes, codes)."),
 "single-letter p":("t(X) :- q(X).\nq(1).", None),
 "findall":        ("t(L) :- findall(Y, member(Y, [1,2]), L).", None),
 "catch/throw":    ("t(E) :- catch(throw(oops), E, true).", None),
 "\\+":            ("t(ok) :- \\+ member(z, [a]).", None),
}
for i, (name, (clause, directive)) in enumerate(CASES.items()):
    mod = f"rf{i}"
    src = f":- module({mod}, [t/1]).\n" + (directive + "\n" if directive else "") + clause + "\n"
    (tmp / f"{mod}.pl").write_text(src)
    try:
        m = importlib.import_module(mod)
    except Exception as e:
        print(f"{name:16s} LOAD  {type(e).__name__}: {str(e).splitlines()[0][:120]}"); continue
    X = Var()
    try:
        r = [s["X"] for s in query(("t", X), {"X": X}, m)][:3]
        print(f"{name:16s} OK    {r}")
    except Exception as e:
        print(f"{name:16s} QUERY {type(e).__name__}: {str(e).splitlines()[0][:120]}")
shutil.rmtree(tmp, ignore_errors=True)
