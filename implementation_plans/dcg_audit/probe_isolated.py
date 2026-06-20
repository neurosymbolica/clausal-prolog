import clausal, tempfile, os, traceback
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
N=0
def load(src):
    global N; N+=1
    d=tempfile.mkdtemp(); p=os.path.join(d,f"c{N}.clausal"); open(p,"w").write(src)
    return _load_module(f"c{N}",p).__dict__["$module"]
def gen(m, termfn):
    out=Var(); sols=[]
    for _ in call("phrase", termfn(m.module_dict), out, module=m): sols.append([deref(t) for t in deref(out)])
    return sols
def run(label, fn):
    try: print(f"  {label}: {fn()}")
    except Exception as e: print(f"  {label}: ERR {type(e).__name__}: {str(e).splitlines()[0][:75]}")

# A plain-clause atom dispatch baseline
def A():
    m=load('-module(x,[r(T,O), foo, bar])\nr(foo, "F"),\nr(bar, "B"),\n')
    res={}
    for k in ("foo","bar"):
        out=Var(); s=[]
        for _ in call("r", m.module_dict[k], out, module=m): s.append(deref(out))
        res[k]=s
    return res
run("A plain atom dispatch", A)

# B DCG atom-head 2 clauses
def B():
    m=load('-module(x,[r(T,S0,S), foo, bar])\nr(foo) >> (["F"])\nr(bar) >> (["B"])\n')
    return {k: gen(m, lambda md,k=k: md["r"](md[k])) for k in ("foo","bar")}
run("B DCG atom-head", B)

# C mixed atom+compound
def C():
    m=load('-module(x,[r(T,S0,S), foo, ve(V)])\nr(foo) >> (["atom"])\nr(ve(V)) >> (["compound"])\n')
    return {"foo":gen(m, lambda md: md["r"](md["foo"])), "ve":gen(m, lambda md: md["r"](md["ve"](md["foo"])))}
run("C mixed heads", C)

# D if-then-else
def D():
    m=load('-module(x,[c(X,S0,S), done, empty])\nc(_x) >> (If([_x], [done], [empty]))\n')
    return gen(m, lambda md: md["c"](md["done"]))
run("D if-then-else", D)

# E phrase/3 residue
def E():
    m=load('ab >> (["a"])\n')
    rest=Var()
    for _ in call("phrase", m.module_dict["ab"], ["a","b"], rest, module=m): return deref(rest)
    return "no-parse"
run("E phrase/3 residue", E)

# F string terminal
def F():
    m=load('hi >> ("hello")\n'); return "loaded"
run("F string terminal '>>(\"hello\")'", F)

# G char-string terminal as list of chars
def G():
    m=load('hi >> (["h","i"])\n')
    return any(True for _ in call("phrase", m.module_dict["hi"], "hi", module=m))
run("G list-terminal vs string input", G)

# H call//1 (variable goal as nonterminal)
def H():
    m=load('-module(x,[run(G,S0,S)])\nrun(_g) >> (_g)\n'); return "loaded"
run("H call//1 (var nonterminal)", H)

# I push-back actually works
def I():
    m=load('-module(x,[r(S0,S), a, b])\n(r, [b]) >> ([a])\n')
    rest=Var()
    for _ in call("phrase", m.module_dict["r"], ["a"], rest, module=m): return deref(rest)
    return "no-parse"
run("I pushback residue (expect [b])", I)

# J backtracking multiple solutions
def J():
    m=load('-module(x,[ab(S0,S)])\nab >> (["a"])\nab >> (["a","b"])\n')
    out=Var(); rests=[]
    for _ in call("phrase", m.module_dict["ab"], ["a","b"], out, module=m): pass
    # use phrase/3 to collect residues
    r=Var(); res=[]
    for _ in call("phrase", m.module_dict["ab"], ["a","b"], r, module=m): res.append(deref(r))
    return res
run("J multi-solution residues", J)
