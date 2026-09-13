import sys, time; sys.path.insert(0,'.')
import _z3bridge as B
from sys import intern

NV = 2000
B.init(NV)
GE, LE, ADD, V = intern('>='), intern('=<'), intern('+'), intern('v')

# identical shape to the real clausal_to_z3 benchmark
terms = []
for i in range(NV-1):
    terms.append((GE, (ADD, (V,i), (V,i+1)), i))
    terms.append((LE, (V,i), 1000))
nodes = 3*(NV-1) + 2*(NV-1)

best = 1e9
for _ in range(5):
    t0=time.perf_counter(); n=B.marshal_all(terms); d=time.perf_counter()-t0
    best=min(best,d)
assert n == len(terms), (n, len(terms))
print(f"C bridge: {len(terms)} constraints (~{nodes} nodes)")
print(f"  marshal {best*1e3:8.2f} ms    {best/nodes*1e6:6.3f} us/node")
print()
# LIKE-FOR-LIKE. The bridge builds ASTs and does NOT assert them into a solver,
# so it must be compared against clausal_to_z3's CONSTRUCTION phase alone
# (8.347 us/node), not against construction + solver.add (12.590), which would
# flatter the bridge by ~50%. See FINDINGS.md section 1.
CONSTRUCTION_ONLY = 8.347   # us/node, clausal_to_z3, measured by bench_real2.py
WITH_SOLVER_ADD   = 12.590  # us/node, the same run including solver.add
us = best/nodes*1e6
print(f"  clausal_to_z3 CONSTRUCTION only    : {CONSTRUCTION_ONLY:7.3f} us/node")
print(f"  LIKE-FOR-LIKE speedup              : {CONSTRUCTION_ONLY/us:7.1f}x   <- the honest number")
print()
print(f"  (for reference, construction+add   : {WITH_SOLVER_ADD:7.3f} us/node -> {WITH_SOLVER_ADD/us:.1f}x,")
print(f"   which is NOT a fair comparison -- the bridge does no solver.add)")
