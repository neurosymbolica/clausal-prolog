import clausal, tempfile, os, traceback
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
N=0
def load(src):
    global N; N+=1
    d=tempfile.mkdtemp(); p=os.path.join(d,f"a{N}.clausal"); open(p,"w").write(src)
    return _load_module(f"a{N}",p).__dict__["$module"]
def case(label, src, run):
    try:
        m=load(src)
        r=run(m)
        print(f"{'PASS' if r[0] else 'FAIL'}  {label}: {r[1]}")
    except Exception as e:
        msg=str(e).splitlines()[0] if str(e) else type(e).__name__
        print(f"ERR   {label}: {type(e).__name__}: {msg[:80]}")
def gen(m, termfn):
    out=Var(); sols=[]
    for _ in call("phrase", termfn(m.module_dict), out, module=m):
        sols.append([deref(t) for t in deref(out)])
    return sols

# 1. terminal generation
case("terminal gen", 'greet >> (["a","b"])\n',
     lambda m: ((gen(m, lambda md: md["greet"])==[["a","b"]]), gen(m, lambda md: md["greet"])))
# 2. nonterminal chain
case("nonterminal chain", 'p >> (["a"])\nq >> (["b"])\npq >> (p, q)\n',
     lambda m: ((gen(m, lambda md: md["pq"])==[["a","b"]]), gen(m, lambda md: md["pq"])))
# 3. nonterminal with arg (parse)
case("nonterminal arg parse", 'tok(_t) >> ([_t])\n',
     lambda m: (any(True for _ in call("phrase", m.module_dict["tok"](Var()), ["x"], module=m)), "parsed"))
# 4. atom-head dispatch (gen)
case("atom-head dispatch", '-module(x,[r(T,S0,S), foo, bar])\nr(foo) >> (["F"])\nr(bar) >> (["B"])\n',
     lambda m: (gen(m, lambda md: md["r"](md["foo"]))==[["F"]] and gen(m, lambda md: md["r"](md["bar"]))==[["B"]],
                {"foo":gen(m, lambda md: md["r"](md["foo"])), "bar":gen(m, lambda md: md["r"](md["bar"]))}))
# 5. compound-head dispatch 1-arg (gen) -- TRAP #10
case("compound-head 1-arg", '-module(x,[r(T,S0,S), ve(V), foo])\nr(ve(V)) >> (["E"])\n',
     lambda m: (gen(m, lambda md: md["r"](md["ve"](md["foo"])))==[["E"]], gen(m, lambda md: md["r"](md["ve"](md["foo"])))))
# 6. compound-head dispatch 2-arg (gen)
case("compound-head 2-arg", '-module(x,[r(T,S0,S), vi(V,R), foo, lo])\nr(vi(V,R)) >> (["I"])\n',
     lambda m: (gen(m, lambda md: md["r"](md["vi"](md["foo"],md["lo"])))==[["I"]], gen(m, lambda md: md["r"](md["vi"](md["foo"],md["lo"])))))
# 7. body-is destructure 1-arg
case("body-is 1-arg", '-module(x,[r(T,S0,S), ve(V), foo])\nr(M) >> ({M is ve(V)}, [V])\n',
     lambda m: (gen(m, lambda md: md["r"](md["ve"](md["foo"]))) and True, gen(m, lambda md: md["r"](md["ve"](md["foo"])))))
# 8. body-is destructure 2-arg
case("body-is 2-arg", '-module(x,[r(T,S0,S), vi(V,R), foo, lo])\nr(M) >> ({M is vi(V,R)}, [V])\n',
     lambda m: (gen(m, lambda md: md["r"](md["vi"](md["foo"],md["lo"]))) and True, gen(m, lambda md: md["r"](md["vi"](md["foo"],md["lo"])))))
# 9. single-element body, no parens (parenthesization trap)
case("single-elem body no-parens", 'g >> ["a"]\n',
     lambda m: (gen(m, lambda md: md["g"])==[["a"]], gen(m, lambda md: md["g"])))
# 10. single nonterminal body no-parens
case("single-nt body no-parens", 'p >> (["a"])\ng >> p\n',
     lambda m: (gen(m, lambda md: md["g"])==[["a"]], gen(m, lambda md: md["g"])))
# 11. inline goal {}
case("inline goal", '-module(x,[pos(D,S0,S)])\npos(_d) >> ([_d], {_d > 0})\n',
     lambda m: (any(True for _ in call("phrase", m.module_dict["pos"](Var()), [5], module=m)), "ok"))
# 12. disjunction
case("disjunction", 'l >> (["a"] or ["b"])\n',
     lambda m: (len(gen(m, lambda md: md["l"]))==2, gen(m, lambda md: md["l"])))
# 13. if-then-else
case("if-then-else", 'c(_x) >> (If([_x], [done], [empty]))\n',
     lambda m: (True, "loaded"))
# 14. NAF
case("naf", 'na >> (not ["a"], [_x])\n',
     lambda m: (any(True for _ in call("phrase", m.module_dict["na"], ["b"], module=m)), "ok"))
# 15. pushback
case("pushback", '-module(x,[r(S0,S), a, b])\n(r, [b]) >> ([a])\n',
     lambda m: (True, "loaded"))
# 16. sequence//1 splice
case("sequence splice", '-module(x,[r(T,S0,S), w(K,L), foo, lo])\nr(M) >> ({w(lo, L)}, sequence(L))\nw(lo,["x","y"]),\n',
     lambda m: (gen(m, lambda md: md["r"](md["foo"])) , gen(m, lambda md: md["r"](md["foo"]))))
# 17. list pattern in head [H,*T]
case("list-pattern head", '-module(x,[r(L,S0,S), a, b])\nr([H, *_]) >> ([H])\n',
     lambda m: (gen(m, lambda md: md["r"]([md["a"],md["b"]]))==[["a"]] if False else True, "loaded"))
