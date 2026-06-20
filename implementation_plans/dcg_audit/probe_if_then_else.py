import tempfile,os
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
def load(s,n):
    d=tempfile.mkdtemp(); p=os.path.join(d,n+".clausal"); open(p,"w").write(s); return _load_module(n,p).__dict__["$module"]
def gen(m,t):
    o=Var(); r=[]
    for _ in call("phrase", t, o, module=m): r.append([deref(x) for x in deref(o)])
    return r
try:
    m=load('a >> (["A"])\nb >> (["B"])\nx >> (If(a, b, b))\n',"ite1")
    print("nonterminal branches:", gen(m, m.module_dict["x"]))
except Exception as e: print("nonterminal branches ERR:", str(e).splitlines()[0][:70])
try:
    m=load('-module(x,[g(S0,S),done,empty])\ng >> (If([done], [done], [empty]))\n',"ite2")
    print("terminal branches:", gen(m, m.module_dict["g"]))
except Exception as e: print("terminal branches ERR:", str(e).splitlines()[0][:70])
