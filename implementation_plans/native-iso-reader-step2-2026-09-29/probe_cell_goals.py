"""Which ISO goal CELLS (reader output shape: functor-first tuples, atoms = str)
does the engine already solve when handed them directly? This is the question
'can L3 lower a body goal to a generic call-by-name, or does it need a dedicated node?'

Run from the worktree root. Each goal runs in a scratch module that imports clpz/clpq/reif
as the seam would, via a tiny .seam file.
"""
import sys, os, importlib, pathlib, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
import clausal
assert clausal.__file__.startswith(os.getcwd())
from clausal.logic.solve import query
from clausal.logic.variables import Var
from clausal.logic.cells import CHARS_TAG

tmp = pathlib.Path(tempfile.mkdtemp()); sys.path.insert(0, str(tmp))
(tmp / "host.seam").write_text("-module(host, [p/2])\n-private([a, b])\np(1, a),\np(2, a),\np(3, b),\n")
m = importlib.import_module("host")
X, Y, L, T = Var(), Var(), Var(), Var()
V = {"X": X, "Y": Y, "L": L, "T": T}
G = {
 "X is 3+4":              ("is", X, ("+", 3, 4)),
 "X is max(3,5)":         ("is", X, ("max", 3, 5)),
 "X is 7 rdiv 2":         ("is", X, ("rdiv", 7, 2)),
 "X is 2**0.5":           ("is", X, ("**", 2, 0.5)),
 "3 < 4":                 ("<", 3, 4),
 "X = f(Y), Y = 1":       (",", ("=", X, ("f", Y)), ("=", Y, 1)),
 "(X=1 ; X=2)":           (";", ("=", X, 1), ("=", X, 2)),
 "\\+ X = 1 (X unbound)": ("\\+", ("=", X, 1)),
 "call(=, X, 1)":         ("call", "=", X, 1),
 "findall p/2":           ("findall", X, ("p", X, Y), L),
 "setof X, Y^p":          ("setof", X, ("^", Y, ("p", X, Y)), L),
 "setof X, p (groups)":   ("setof", X, ("p", X, Y), L),
 "dif(X,1), X=2":         (",", ("dif", X, 1), ("=", X, 2)),
 "X @< b":                (",", ("=", X, "a"), ("@<", X, "b")),
 "compare(O,1,2)":        ("compare", X, 1, 2),
 "X =.. L":               ("=..", ("f", 1), L),
 "X #= 3+4":              ("#=", X, ("+", 3, 4)),
 "X in 0..5, X #> 3, label":(",", ("in", X, ("..", 0, 5)), (",", ("#>", X, 3), ("label", [X]))),
 "{X = 2*Y, Y = 3} clpq": ("{}", (",", ("=", X, ("*", 2, Y)), ("=", Y, 3))),
 "if_(1=1, X=y, X=n)":    ("if_", ("=", 1, 1), ("=", X, "y"), ("=", X, "n")),
 "memberd(X,[a,b])":      ("memberd", X, ["a", "b"]),
 "once(member(X,[a,b]))": ("once", ("member", X, ["a", "b"])),
 "forall(member..)":      ("forall", ("member", X, [1, 2]), ("integer", X)),
 "catch(throw(e),E,true)":("catch", ("throw", "e"), X, "true"),
 "X = \"ab\", X = [a|_]": (",", ("=", X, (CHARS_TAG, "ab")), ("=", X, (".", "a", Y))),
 "atom_length(abc,N)":    ("atom_length", "abc", X),
 "nth1(2,[a,b],X)":       ("nth1", 2, ["a", "b"], X),
 "keysort":               ("keysort", [("-", 2, "b"), ("-", 1, "a")], X),
 "atom_number('3',N)":    ("atom_number", "3", X),
 "aggregate_all(count)":  ("aggregate_all", "count", ("p", Y, "a"), X),
 "format(atom(A),..)":    ("format", ("atom", X), (CHARS_TAG, "~w"), [1]),
 "succ_or_fail(3,X)":     ("succ", 3, X),
 "get(D,k,V) dict pred":  ("get", {"k": 1}, "k", X),
 "current_prolog_flag":   ("current_prolog_flag", "bounded", X),
 "X is 5 euro + 1 euro":  ("is", X, ("+", ("euro", 5), ("euro", 1))),
}
for name, g in G.items():
    for v in (X, Y, L, T):
        pass
    X2, Y2, L2 = Var(), Var(), Var()
    def sub(t):
        if t is X: return X2
        if t is Y: return Y2
        if t is L: return L2
        if isinstance(t, tuple): return tuple(sub(a) for a in t)
        if isinstance(t, list): return [sub(a) for a in t]
        return t
    g2 = sub(g)
    try:
        res = [ {k: s[k] for k in ("X", "L") if k in s} for s in query(g2, {"X": X2, "L": L2}, m)][:3]
        print(f"{name:26s} OK  {res}"[:160])
    except Exception as e:
        print(f"{name:26s} ERR {type(e).__name__}: {str(e).splitlines()[0][:110]}")
