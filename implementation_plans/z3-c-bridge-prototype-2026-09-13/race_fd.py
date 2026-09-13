import time, z3
from clausal.logic.variables import Trail, Var, deref
from clausal.logic.clpfd import in_domain, all_different, fd_ne, label
from clausal.logic.clpz3 import in_z3, all_different_z3, z3_ne, label_z3
from clausal.pythonic_ast.nodes import Add, Sub

def nqueens_clpfd(N):
    tr=Trail(); qs=[Var() for _ in range(N)]
    in_domain(qs, 1, N, tr)
    if not all_different(qs, tr): return None
    for i in range(N):
        for j in range(i+1, N):
            if not fd_ne(Add(left=qs[i], right=j-i), qs[j], tr): return None
            if not fd_ne(Sub(left=qs[i], right=j-i), qs[j], tr): return None
    for _ in label(qs, tr):
        return [deref(q) for q in qs]
    return None

def nqueens_z3(N):
    tr=Trail(); qs=[Var() for _ in range(N)]
    in_z3(qs, 1, N, tr)
    if not all_different_z3(qs, tr): return None
    for i in range(N):
        for j in range(i+1, N):
            if not z3_ne(Add(left=qs[i], right=j-i), qs[j], tr): return None
            if not z3_ne(Sub(left=qs[i], right=j-i), qs[j], tr): return None
    for _ in label_z3(qs, tr):
        return [deref(q) for q in qs]
    return None

for N in (8, 12, 16, 20):
    t0=time.perf_counter(); a=nqueens_clpfd(N); d1=time.perf_counter()-t0
    t0=time.perf_counter(); b=nqueens_z3(N);   d2=time.perf_counter()-t0
    print(f"{N}-queens   CLP(Z) {d1*1e3:9.1f} ms {'sol' if a else 'NONE'}    "
          f"Z3 {d2*1e3:9.1f} ms {'sol' if b else 'NONE'}    Z3/CLP(Z) {d2/d1:6.2f}x")
