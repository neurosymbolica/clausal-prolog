"""Is `Compound` needed once functor-first tuples are the representation?

Compound is a dataclass {functor: str|Var, args: tuple, _position}. A
functor-first tuple covers {str functor, args}. So the question reduces to the
two things a tuple structurally cannot carry:

  1. a VARIABLE in functor position  -- Compound(functor_var, args)
  2. _position source metadata

Tested directly, with controls.
"""
from clausal.terms import Compound
from clausal.logic.variables import Var, unify, Trail, deref

print("== 1. can a functor-first TUPLE hold a Var in slot 0? ==")
F = Var()
t = Trail()
# control: the ordinary str-functor tuple path must work
ok = unify(("f", 1, Var()), ("f", 1, 2), t)
print(f"   control, ('f',1,X) vs ('f',1,2)          unify -> {ok}   (expect True)")

t2 = Trail()
try:
    r = unify((F, 1), ("f", 1), t2)
    print(f"   (F, 1) vs ('f', 1)                      unify -> {r}")
    print(f"   F bound to                              {deref(F)!r}")
except Exception as exc:
    print(f"   (F, 1) vs ('f', 1)                      RAISED {type(exc).__name__}: {exc}")

print("\n== and what Compound does with the same case ==")
G = Var()
t3 = Trail()
try:
    r = unify(Compound(G, (1,)), Compound("f", (1,)), t3)
    print(f"   Compound(G,(1,)) vs Compound('f',(1,))  unify -> {r}")
    print(f"   G bound to                              {deref(G)!r}")
except Exception as exc:
    print(f"   RAISED {type(exc).__name__}: {exc}")

print("\n== 2. does a BOUND var functor work on each side? ==")
H = Var(); t4 = Trail()
unify(H, "f", t4)
print(f"   H bound to 'f' first, then:")
t5 = Trail()
print(f"   Compound(H,(1,)) vs Compound('f',(1,))  unify -> "
      f"{unify(Compound(H,(1,)), Compound('f',(1,)), t5)}")
t6 = Trail()
try:
    print(f"   (H, 1) vs ('f', 1)                      unify -> {unify((H,1), ('f',1), t6)}")
except Exception as exc:
    print(f"   (H, 1) vs ('f', 1)                      RAISED {type(exc).__name__}")

print("\n== 3. do a Compound and the equivalent tuple unify with each other? ==")
t7 = Trail()
print(f"   Compound('f',(1,2)) vs ('f',1,2)        unify -> "
      f"{unify(Compound('f',(1,2)), ('f',1,2), t7)}")
