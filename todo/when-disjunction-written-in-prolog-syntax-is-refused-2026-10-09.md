# when/2 with a disjunction written in Prolog syntax is refused

Found 2026-10-09 on main 1a48d5a2:

```prolog
e(Y) :- when((nonvar(X) ; nonvar(Z)), member(Y, [1, 2])), X = go, Z = go.
```

    ValueError: Unsupported when condition: (';', ('nonvar', _), ('nonvar', _))

The compiler lowers a disjunction to `$install_when_disjunction` only when it
sees the seam `Or` node (`_compile_when` in
`clausal/logic/compiler/control_constructs.py`). A `.clausal`/`.pl` clause
reaches it as the cell `(';', C1, C2)`, which falls through to
`$install_when_condition`, and the runtime dispatcher
(`_install_when_condition` in `clausal/logic/coroutining.py`) has no `;`
arm. The conjunction arm has the same blind spot for `(',', C1, C2)` (it
accepts only a functor-less pair).

Fix: give the runtime dispatcher `;` and `,` cell arms (`;` →
`_install_when_disjunction`, `,` → the nested install), and check `when/2`
called through `call/N`.
