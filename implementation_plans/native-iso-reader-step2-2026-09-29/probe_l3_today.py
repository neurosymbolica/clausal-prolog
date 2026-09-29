"""Probe: what iso_l3 (P1, facts only) does today with each construct class.

Run from the worktree:  ./venv/bin/python implementation_plans/native-iso-reader-step2-2026-09-29/probe_l3_today.py
Prints, per snippet: reader item kinds, L3 read/lowered/refused, and the refusal text.
Then loads a facts module through the REAL PrologLoader with L3 swapped in and
prints answers, to show what the P1 lowering binds for atoms/strings/floats.
"""
import sys, os, importlib, pathlib, tempfile, shutil
sys.path.insert(0, os.getcwd())
import clausal
assert clausal.__file__.startswith(os.getcwd()), clausal.__file__
from clausal.tools import iso_l3 as L3

SNIPPETS = {
    "int fact":        "f(1, 2).",
    "atom fact":       "f(foo, bar).",
    "quoted atom":     "f('Hello World').",
    "string":          'f("abc").',
    "float":           "f(1.5).",
    "negative int":    "f(-3).",
    "var in fact":     "f(X).",
    "compound arg":    "f(pt(1, 2)).",
    "partial list":    "f([a|T]).",
    "curly":           "f({a}).",
    "rule":            "g(X) :- f(X).",
    "conj/disj/neg":   "g(X) :- f(X), ( X > 1 ; \\+ X = 0 ).",
    "module/2":        ":- module(m, [g/1]).",
    "use_module":      ":- use_module(library(lists)).",
    "dynamic":         ":- dynamic(d/1).",
    "initialization":  ":- initialization(main).",
    "DCG":             "s --> [a].",
    "no trailing nl":  "f(1).",
}
print("read_iso WITHOUT trailing newline:", len(L3.read_iso("f(1).\ng(2).")), "items of 2")
print("read_prolog_reader.read_module same:", len(__import__("clausal.tools.prolog_reader", fromlist=["x"]).read_module("f(1).\ng(2).")))
for name, src in SNIPPETS.items():
    src = src + "\n"
    try:
        items = L3.read_iso(src)
        kinds = [type(i).__name__ for i in items]
        _, st = L3.lower_items(items)
        print(f"{name:16s} items={kinds} read={st['read']} lowered={st['lowered']} "
              f"refused={st['refused']} {st['refusals'][:1]}")
    except Exception as e:
        print(f"{name:16s} RAISED {type(e).__name__}: {str(e)[:110]}")

# Real-loader probe: facts with atom / quoted atom / string args, answers shown.
from clausal import import_hook
from clausal.logic.solve import query
from clausal.logic.variables import Var
tmp = pathlib.Path(tempfile.mkdtemp())
sys.path.insert(0, str(tmp))
def l3_source_to_code(self, data, path="<string>"):
    mod, st = L3.lower_items(L3.read_iso(data.decode()))
    print("   L3 stats:", {k: st[k] for k in ("read", "lowered", "refused")})
    return compile(mod, path, "exec")
import_hook.PrologLoader.source_to_code = l3_source_to_code
(tmp / "p_atoms.pl").write_text("k(foo).\nk('Bar').\nk(\"ab\").\nk([x, y]).\n")
try:
    m = importlib.import_module("p_atoms")
    X = Var()
    ans = [s["X"] for s in query(("k", X), {"X": X}, m)]
    print("real-loader answers k/1:", [repr(a) for a in ans])
    X = Var()
    print("k(foo) ?", bool(list(query(("k", "foo"), {}, m))),
          "| k([a,b]) via \"ab\" ?", bool(list(query(("k", ["a", "b"]), {}, m))))
except Exception as e:
    print("real-loader RAISED", type(e).__name__, str(e)[:300])
shutil.rmtree(tmp, ignore_errors=True)
