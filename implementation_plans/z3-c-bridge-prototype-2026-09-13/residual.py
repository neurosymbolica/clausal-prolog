from clausal.logic.variables import Trail, Var, deref
from clausal.logic.clpq import in_q, q_ge, dump_q
from clausal.logic.clpz3 import in_z3, z3_ge, z3_check, get_z3_state
from clausal.pythonic_ast.nodes import Add

# under-determined: X + Y >= 10, nothing else
tr=Trail(); X,Y=Var(),Var()
in_q(X,None,None,tr); in_q(Y,None,None,tr)
q_ge(Add(left=X,right=Y), 10, tr)
print("CLP(Q) answer :", dump_q([X,Y], tr), "   X bound?", deref(X) is not X)

tr2=Trail(); A,B=Var(),Var()
in_z3(A,-10**6,10**6,tr2); in_z3(B,-10**6,10**6,tr2)
z3_ge(Add(left=A,right=B), 10, tr2)
sat = z3_check(tr2)
st = get_z3_state(tr2)
m = st.solver.model() if sat else None
print("Z3 answer     : sat =", sat, "| model =", {str(d): str(m[d]) for d in m} if m else None)
