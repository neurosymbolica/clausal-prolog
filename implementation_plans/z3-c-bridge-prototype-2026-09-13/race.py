import time, z3
from clausal.logic.variables import Trail, Var
from clausal.logic.clpq import in_q, q_le, q_ge, q_eq, maximize
from clausal.logic.clpz3 import in_z3, z3_le, z3_ge, z3_check, clausal_to_z3
from clausal.pythonic_ast.nodes import Add

def t(f):
    t0=time.perf_counter(); r=f(); return (time.perf_counter()-t0), r

def clpq_linear(NV):
    tr=Trail(); xs=[Var() for _ in range(NV)]
    for v in xs: in_q(v, 0, 1000, tr)
    ok=True
    for i in range(NV-1):
        ok = ok and q_ge(Add(left=xs[i], right=xs[i+1]), i % 100, tr)
        ok = ok and q_le(xs[i], 1000, tr)
    return ok

def z3_linear(NV):
    tr=Trail(); xs=[Var() for _ in range(NV)]
    for v in xs: in_z3(v, 0, 1000, tr)
    ok=True
    for i in range(NV-1):
        ok = ok and z3_ge(Add(left=xs[i], right=xs[i+1]), i % 100, tr)
        ok = ok and z3_le(xs[i], 1000, tr)
    return ok and z3_check(tr)

for NV in (200, 1000):
    dq, rq = t(lambda: clpq_linear(NV))
    dz, rz = t(lambda: z3_linear(NV))
    print(f"NV={NV:5}  CLP(Q) {dq*1e3:8.1f} ms ({rq})   Z3 {dz*1e3:8.1f} ms ({rz})   ratio {dz/dq:5.2f}x")
