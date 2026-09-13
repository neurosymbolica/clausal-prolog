import time, z3, cvc5
from cvc5 import Kind

NV = 2000
def phase(name, marshal, solve):
    t0=time.perf_counter(); h=marshal(); t1=time.perf_counter()
    r=solve(h); t2=time.perf_counter()
    m, s = t1-t0, t2-t1
    print(f"{name:12} marshal {m*1e3:8.1f} ms  solve {s*1e3:8.1f} ms  total {(m+s)*1e3:8.1f} ms  ({r})")
    return m, s

def z3_marshal():
    xs=[z3.Int(f'x{i}') for i in range(NV)]; s=z3.Solver()
    for i in range(NV-1):
        s.add(xs[i]+xs[i+1] >= i); s.add(xs[i] <= 1000)
    return s
def cvc5_marshal():
    tm=cvc5.TermManager(); sv=cvc5.Solver(tm); sv.setOption('produce-models','true')
    I=tm.getIntegerSort(); xs=[tm.mkConst(I,f'x{i}') for i in range(NV)]
    for i in range(NV-1):
        sv.assertFormula(tm.mkTerm(Kind.GEQ, tm.mkTerm(Kind.ADD, xs[i], xs[i+1]), tm.mkInteger(i)))
        sv.assertFormula(tm.mkTerm(Kind.LEQ, xs[i], tm.mkInteger(1000)))
    return sv

print(f"LINEAR: {NV} vars, {2*(NV-1)} constraints")
mz,sz = phase("Z3",   z3_marshal,   lambda s: s.check())
mc,sc = phase("cvc5", cvc5_marshal, lambda s: s.checkSat())
print()
print(f"  marshal: cvc5 is {mz/mc:5.2f}x Z3's python path   solve: cvc5 is {sz/sc:5.2f}x Z3")
print(f"  total  : cvc5 is {(mz+sz)/(mc+sc):5.2f}x Z3")
