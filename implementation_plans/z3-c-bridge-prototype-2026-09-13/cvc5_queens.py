import time, z3, cvc5
from cvc5 import Kind

def z3_queens(N):
    qs=[z3.Int(f'q{i}') for i in range(N)]; s=z3.Solver()
    for q in qs: s.add(q>=1, q<=N)
    s.add(z3.Distinct(qs))
    for i in range(N):
        for j in range(i+1,N):
            s.add(qs[i]-qs[j] != j-i); s.add(qs[i]-qs[j] != i-j)
    return s.check()==z3.sat

def cvc5_queens(N):
    tm=cvc5.TermManager(); s=cvc5.Solver(tm); I=tm.getIntegerSort()
    qs=[tm.mkConst(I,f'q{i}') for i in range(N)]
    for q in qs:
        s.assertFormula(tm.mkTerm(Kind.GEQ,q,tm.mkInteger(1)))
        s.assertFormula(tm.mkTerm(Kind.LEQ,q,tm.mkInteger(N)))
    s.assertFormula(tm.mkTerm(Kind.DISTINCT,*qs))
    for i in range(N):
        for j in range(i+1,N):
            d=tm.mkTerm(Kind.SUB,qs[i],qs[j])
            s.assertFormula(tm.mkTerm(Kind.NOT,tm.mkTerm(Kind.EQUAL,d,tm.mkInteger(j-i))))
            s.assertFormula(tm.mkTerm(Kind.NOT,tm.mkTerm(Kind.EQUAL,d,tm.mkInteger(i-j))))
    return s.checkSat().isSat()

for N in (8,16,20):
    t0=time.perf_counter(); a=z3_queens(N);   d1=time.perf_counter()-t0
    t0=time.perf_counter(); b=cvc5_queens(N); d2=time.perf_counter()-t0
    print(f"{N:3}-queens   Z3 {d1*1e3:9.1f} ms ({a})   cvc5 {d2*1e3:9.1f} ms ({b})   cvc5/Z3 {d2/d1:6.2f}x")
