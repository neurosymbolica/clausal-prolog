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
print(f"  real clausal_to_z3 measured earlier:  12.590 us/node  (125.9 ms)")
print(f"  SPEEDUP on marshalling            :  {12.590/(best/nodes*1e6):8.1f}x")
