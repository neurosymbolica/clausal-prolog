import os, tempfile, textwrap
from clausal.import_hook import _load_module
from clausal import Var
from clausal.logic.seam import once_bind, export
from clausal.logic.variables import unify, Trail, deref

SRC = "-module(pt3, [idpred])\nidpred(X, X),\n"
d = tempfile.mkdtemp(); p = os.path.join(d, "pt3.clausal")
open(p, "w").write(SRC); mod = _load_module("pt3", p)

class Payload:
    def __init__(self, n): self.n = n
    def __repr__(self): return f"Payload({self.n})"
obj = Payload(42)

print("control FIRST: an int through idpred/2")
W = Var()
try:
    print(f"   once_bind -> {once_bind(('idpred', 42, W), mod.__dict__)}, export -> {export(W)!r}")
except Exception as e:
    print(f"   CONTROL FAILED {type(e).__name__}: {str(e)[:80]}  -- nothing below is meaningful")

print("\nroute A: the object directly in the goal tuple")
W = Var()
try:
    ok = once_bind(("idpred", obj, W), mod.__dict__)
    got = export(W)
    print(f"   once_bind -> {ok}, export -> {got!r}, SAME object: {got is obj}")
except Exception as e:
    print(f"   {type(e).__name__}: {str(e)[:100]}")

print("\nroute B: pre-bind to a Var, pass the Var")
t = Trail(); V = Var(); unify(V, obj, t)
W = Var()
try:
    ok = once_bind(("idpred", V, W), mod.__dict__)
    got = export(W)
    print(f"   once_bind -> {ok}, export -> {got!r}, SAME object: {got is obj}")
except Exception as e:
    print(f"   {type(e).__name__}: {str(e)[:100]}")
