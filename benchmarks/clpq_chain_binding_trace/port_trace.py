"""Trace the port's decisions (bounded_simplex.TRACE, back substitutions,
verify_bound) while binding a chain X1 =< ... =< Xn.  Used by run.sh.

usage: port_trace.py N MODE   MODE in: forward, backward, all
"""
import os, sys
os.environ["CLAUSAL_CLPQ"] = "holzbaur"
from clausal.logic.clpq import holzbaur, bounded_simplex as bs
from clausal.logic.clpq.attributes import state_of
from clausal.logic.clpq.components import list_elements, component_all_variables, component_basis
from clausal.logic.clpq.linear_forms import independent
from clausal.logic.pending import drain
from clausal.logic.variables import Trail, Var, deref, unify, is_var

n = int(sys.argv[1]); mode = sys.argv[2]
t = Trail()
xs = [Var() for _ in range(n)]
names = {}           # id(order var) -> name
def order_of(v):
    s = state_of(v)
    return None if s is None or s.variable_order is None else deref(s.variable_order)
def post_chain():
    for a, b in zip(xs, xs[1:]):
        assert holzbaur.q_le(a, b, t)
post_chain()
for i, x in enumerate(xs):
    names[id(order_of(x))] = f"X{i+1}"
# slack Sk: the term of X(k+1)'s row that X(k)'s row lacks (Scryer's s-numbering)
def _row_vars(x):
    s = state_of(deref(x))
    return [deref(v) for v, _ in s.linear_form.terms]
prev = {id(order_of(xs[0]))}
for k in range(1, n):
    vs = _row_vars(xs[k])
    new = [v for v in vs if id(order_of(v)) not in prev and id(order_of(v)) not in names]
    for v in new:
        names[id(order_of(v))] = f"S{k}"
    prev = {id(order_of(v)) for v in vs}
slack = [0]
def name(v):
    v = deref(v)
    if not is_var(v):
        return repr(v)
    o = order_of(v)
    if o is None:
        return f"?{id(v)%1000}"
    if id(o) not in names:
        slack[0] += 1
        names[id(o)] = f"S{slack[0]}"
    return names[id(o)]

def q(c):
    a, b = c
    return str(a) if b == 1 else f"{a}/{b}"
def row(form):
    parts = [f"{q(c)}*{name(v)}" for v, c in form.terms]
    return " + ".join(parts) + f" + {q(form.constant)}"
def comp():
    for x in xs:
        if is_var(deref(x)):
            s = state_of(deref(x))
            if s and s.component is not None:
                return deref(s.component)
    return None
def bstr(b):
    return "none" if b is None else str(b).replace(" ", "")
def show_store():
    c = comp()
    if c is None:
        print("  (no component)"); return
    members = [deref(m) for m in list_elements(component_all_variables(c))]
    print("  members:", " ".join(name(m) for m in members))
    print("  basis:  ", " ".join(name(m) for m in list_elements(component_basis(c)) or []))
    for m in members:
        s = state_of(m)
        if s and s.linear_form is not None and not independent(s.linear_form, m):
            print(f"    {name(m)} = {row(s.linear_form)}   bounds={bstr(s.bounds)}")
        elif s:
            print(f"    {name(m)} indep bounds={bstr(s.bounds)}")

def hook(event, *args):
    print("   ", event, *[name(a) if isinstance(a, Var) or hasattr(a, 'attrs') else a for a in args])
for mod in (bs,):
    mod.TRACE = hook

# rows rewritten per back substitution
stats = {"rows_read": 0, "rows_rewritten": 0}
def wrap(fn, label):
    def w(members, variable, form, *rest):
        before = {}
        ms = [deref(m) for m in list_elements(members)]
        for m in ms:
            s = state_of(m)
            if s is not None: before[id(m)] = s.linear_form
        r = fn(members, variable, form, *rest)
        changed = [name(m) for m in ms if state_of(m) is not None and state_of(m).linear_form is not before.get(id(m))]
        stats["rows_read"] += len(ms); stats["rows_rewritten"] += len(changed)
        print(f"    {label} {name(variable)} := {row(form)} ; read {len(ms)} rows, rewrote {len(changed)}: {' '.join(changed)}")
        return r
    return w
bs.back_substitute_variables = wrap(bs.back_substitute_variables, "bs")
bs.back_substitute_collect_bindings = wrap(bs.back_substitute_collect_bindings, "bs_collect")

from clausal.logic.clpq import attribute_hooks as ah
_vb = ah.verify_bound
def _verify_bound(variable, state, value, *rest):
    if variable is not None:
        print(f"  verify {name(variable)} = {deref(value)}")
    return _vb(variable, state, value, *rest)
ah.verify_bound = _verify_bound
print("after posting the chain:")
show_store()
def bind(i):
    print(f"\n== bind {name(xs[i])} = {i}")
    assert unify(xs[i], i, t)
    for _ in drain(t):
        break
    show_store()
order = {"forward": range(n), "backward": range(n - 1, -1, -1)}.get(mode)
if mode == "all":
    print("\n== bind all in one unification")
    assert unify(xs, list(range(n)), t)
    for _ in drain(t): break
    show_store()
else:
    for i in order:
        bind(i)
print("\ntotals", stats)
