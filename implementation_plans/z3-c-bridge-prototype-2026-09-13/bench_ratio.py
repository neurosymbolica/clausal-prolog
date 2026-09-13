import time, z3

def phase(build, n_label):
    t0=time.perf_counter(); s, cons = build(); t1=time.perf_counter()
    for c in cons: s.add(c)
    t2=time.perf_counter(); r=s.check(); t3=time.perf_counter()
    m=(t1-t0)+(t2-t1); solve=t3-t2
    print(f"{n_label:32} marshal {m*1e3:8.1f} ms   solve {solve*1e3:8.1f} ms   "
          f"marshal={m/(m+solve)*100:5.1f}%  ({r})")

# A: many simple LINEAR constraints -- the shape a legal rulebase actually emits
def linear(nv=2000):
    def b():
        xs=[z3.Int(f'x{i}') for i in range(nv)]
        cons=[]
        for i in range(nv-1):
            cons.append(xs[i] + xs[i+1] >= i)
            cons.append(xs[i] <= 1000)
        return z3.Solver(), cons
    return b

# B: few but HARD constraints -- solver-dominated
def hard(n=60):
    def b():
        xs=[z3.Int(f'y{i}') for i in range(n)]
        cons=[z3.Distinct(xs)]
        for x in xs: cons.append(z3.And(x>=0, x<n))
        # pigeonhole-ish extra structure
        for i in range(n-1): cons.append(xs[i]+xs[i+1] != n)
        return z3.Solver(), cons
    return b

phase(linear(2000), "A: 4000 linear constraints")
phase(hard(60),     "B: 60 vars, distinct + arith")
