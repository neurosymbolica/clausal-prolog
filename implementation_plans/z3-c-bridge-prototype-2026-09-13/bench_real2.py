import time, z3
from clausal.logic.variables import Trail, Var
from clausal.logic.clpz3 import clausal_to_z3, in_z3
from clausal.pythonic_ast.nodes import Add, GtE, LtE

NV = 2000
tr = Trail()
xs = [Var() for _ in range(NV)]
for v in xs: in_z3(v, -10**9, 10**9, tr)

# 4000 shallow constraints -- the same shape as the ratio benchmark
exprs = []
for i in range(NV-1):
    exprs.append(GtE(left=Add(left=xs[i], right=xs[i+1]), right=i))
    exprs.append(LtE(left=xs[i], right=1000))
nodes = sum(3 for _ in range(NV-1)) + sum(2 for _ in range(NV-1))   # approx AST nodes

t0=time.perf_counter()
zs=[clausal_to_z3(e, tr, z3.IntSort()) for e in exprs]
t1=time.perf_counter()
s=z3.Solver()
for z in zs: s.add(z)
t2=time.perf_counter(); r=s.check(); t3=time.perf_counter()

m=(t1-t0)+(t2-t1); solve=t3-t2
print(f"REAL clausal_to_z3 path, {len(exprs)} constraints (~{nodes} AST nodes)")
print(f"  marshal {m*1e3:8.1f} ms   solve {solve*1e3:8.1f} ms   marshal={m/(m+solve)*100:5.1f}%   ({r})")
print(f"  {m/nodes*1e6:6.2f} us per AST node through the real marshaller")
