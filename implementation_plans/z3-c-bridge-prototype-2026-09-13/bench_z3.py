import time, z3
from z3 import z3core as C
from z3.z3types import Ast

N = 20000

def timeit(f, reps=3):
    best = 1e9
    for _ in range(reps):
        t = time.perf_counter(); f(); best = min(best, time.perf_counter()-t)
    return best

# ---- Level 1: the full Python API (ExprRef objects + operator overloading) ----
def level1():
    x = z3.Int('x')
    acc = x
    for i in range(N):
        acc = acc + i
    return acc == 0

# ---- Level 2: raw ctypes into Z3_mk_* -- no ExprRef wrappers, no overloading ----
def level2():
    ctx = C.Z3_mk_context(C.Z3_mk_config())
    isort = C.Z3_mk_int_sort(ctx)
    sym = C.Z3_mk_string_symbol(ctx, 'x')
    acc = C.Z3_mk_const(ctx, sym, isort)
    for i in range(N):
        lit = C.Z3_mk_int(ctx, i, isort)
        acc = C.Z3_mk_add(ctx, 2, (Ast * 2)(acc, lit))
    zero = C.Z3_mk_int(ctx, 0, isort)
    return C.Z3_mk_eq(ctx, acc, zero)

# ---- Level 3 proxy: pure ctypes call overhead, cheapest possible libz3 call ----
def level3_ctypes_floor():
    ctx = C.Z3_mk_context(C.Z3_mk_config())
    isort = C.Z3_mk_int_sort(ctx)
    for i in range(N):
        C.Z3_mk_int(ctx, i, isort)     # one ctypes crossing, trivial work inside

t1 = timeit(level1); t2 = timeit(level2); t3 = timeit(level3_ctypes_floor)
print(f"N = {N} AST nodes")
print(f"  L1 full Python API      {t1*1e3:8.1f} ms   {t1/N*1e6:7.2f} us/node")
print(f"  L2 raw ctypes Z3_mk_*   {t2*1e3:8.1f} ms   {t2/N*1e6:7.2f} us/node   ({t1/t2:.2f}x faster than L1)")
print(f"  L3 ctypes call floor    {t3*1e3:8.1f} ms   {t3/N*1e6:7.2f} us/node   (1 crossing/node)")
print()
print(f"  Python-wrapper tax (L1-L2): {(t1-t2)*1e3:7.1f} ms = {(t1-t2)/t1*100:4.1f}% of today's cost")
print(f"  ctypes tax still in L2     : {t3*1e3:7.1f} ms  -- a C ext pays ~0 of this")
