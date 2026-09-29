# W4's Python boundary — what to build, from the 2026-09-22 rulings

**Rulings (operator, 2026-09-22):** a module-level predicate name becomes the
MODULE-QUALIFIED atom (the `-hide` mangling, `m<US>pred`); the engine
demangles it so a held handle resolves with no `module=`; and `--` should
work ANYWHERE, so a hold-and-call site migrates by wrapping `handle(X)` as
`--handle(X)`, not by rewriting to a tuple.

**Measured 2026-09-22 (main 05ebcd91), which settles "what am I missing":**

    h = w4lib.pred ; --h(X)      ->  ('pred', X)          WORKS TODAY: the seam
                                     resolves the NAME `h` to its bound value,
                                     a CLASS, and reads the functor spelling
                                     off the class; the module is DROPPED
    --w4lib.pred(X) (hosted)     ->  AttributeError in seam.dotted()   (todo filed)
    --(++h)(X)                   ->  TypeError: unary + on the class   (no computed
                                     functor form; not needed, see below)

So `--` already reaches a held handle by NAME. Nothing is missing on the
surface; what changes at W4 is what the name is bound TO.

## The pieces, in order (each TDD, each gated twice, none needs the head channel)

1. **Seam functor slot: a name bound to an ATOM value.** `seam.build`'s
   class-binding branch reads the functor off a bound class; add the branch
   for a bound `str` atom (plain or mangled): the cell's functor is that
   spelling, arity as written. After W4 `h` is bound to `m<US>pred`, so
   `--h(X)` builds `('m<US>pred', X)` and the module TRAVELS.
2. **Demangle at the three entry points**, by normalising to the qualified
   form the engine already resolves (`cells.resolve_qualified_goal_cell`,
   the `(":", M, G)` cell): a cell whose functor `is_mangled` becomes
   `(":", <module by name>, (name, *args))` in `solve`'s `_term_to_goal` /
   `_module_for_moduleless_solve`, in `higher_order._resolve_named_goal`
   (`call/N`), and in `_dispatch_at`'s atom branch (a bare mangled atom is an
   arity-0 goal in its module). No demangling exists on any of these paths
   today (grepped).
3. **Fix the hosted dotted-base seam** (todo filed) so `--m.pred(X)` works in
   a `.clausal` host as it does in Python-hosted code.
4. **W4 proper, after the head channel:** the module attribute for a
   predicate becomes the mangled atom; `make_predicate` and the class go.
   Until then, 1–3 are ADDITIVE: a class-bound name keeps working exactly as
   now, so they can land ahead of the class removal and the 31 downstream
   sites can migrate to `--handle(X)` early, against either binding.

## What the downstream migration is, once 1–3 land

    handle(X)  (Python call, lambda body / argument / comprehension)
      ->  --handle(X)          the seam builds the goal cell from the handle's
                               spelling; the module rides in the mangled atom
    tables of (name, handle), handles passed as arguments: UNCHANGED

Values come back through whichever run path the body already uses; the
two-out-paths note (`todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md`)
still applies to a body that MIXES `--` runs with `solve` runs.

## LANDED — pieces 1 and 2, main `f73ccc65` (2026-09-22, operator: "go for both")

Two commits (3108a41f, f73ccc65 as cherry-picked onto main; gated as
2dc84e40 + acb2877e with code trees byte-identical): the seam's functor
slot accepts a name bound to a MANGLED atom; `cells.qualify_mangled_goal`
turns a mangled functor whose module is LOADED into the `(":", M, G)` form
at `solve`, `call` by name, `call/N` and `_dispatch_at` (row first, then the
module namespace so imports resolve; indicator `M:(name/N)`). The handle's
module half is the IMPORT name; a `-hide` data atom (bare declared name)
is not a handle and keeps its old error. Review round: roborev 82, four
findings fixed, three not reproduced and pinned. Gates NEW 0 / GONE 0 both
ways. Piece 3 (hosted dotted-base seam) NOT done; W4 proper (mint handles
with the import name; the head channel; the class) not started.

## The seam gap (2026-09-22, found by the downstream lane) — built on feat/seam-local-handle-2026-09-22, not yet landed

My "``h = m.pred; --h(X)`` works today" held only for a MODULE-LEVEL binding.
The seam resolved functor names against module globals, so a handle in a
function local, a parameter, a lambda parameter or a comprehension target
raised ``NameError`` (and under ``-implicit_functors`` silently built a cell
named after the VARIABLE). Fixed: the seam-mode term transformer hands such a
name to the seam as a thunk of its VALUE; the cell's functor is read off the
value. **A HANDLE CARRIES ITS MODULE**: a class-built handle cell is the
module-qualified goal ``(":", <the class's module>, (name, args...))``, a
mangled-atom handle says the same in one spelling. Goal position
(``for``/``if``/comprehension iterable) builds the goal through the seam
builder first, since it is solved in the HOST module. Also fixed:
``seam.dotted()`` (``.object``, not ``.value``), piece 3.

### THE MIGRATION RULE for the downstream hold-and-call sites (measured by
### the downstream lane on 7d843d35): WRAP THE CALL, NEVER THE ITERABLE

    handle(X)                       ->  --handle(X)          a VALUE: the qualified goal cell
    solve(cell, module=m)           ->  solve(cell)          module= now redundant, harmless
    for K in --handle(K, V): ...    ->  DO NOT WRITE THIS in a body that also solves

``--handle(...)`` built and handed to ``solve()`` stays on the solve path:
plain ``str`` atoms, carrier tuples for strings, no ``export()``. The
ITERABLE / test form is goal position and EXPORTS (``atom``-tagged atoms,
plain-str strings) — the exact mix the all-solve ruling forbids. Until the
two-out-paths question (``todo/two-out-paths-disagree-about-atom-tagging-
2026-09-22.md``) is ruled, this is a discipline. The operator's word to put
``--`` back at those 31 sites must reach the downstream lane directly.

## RULED 2026-09-22 (operator, evening) — the 31 hold-and-call sites: LITERAL TUPLES NOW, a dated exception

Options put to the operator with the measurement that the attribute-backed
form ``(m.thing, K, V)`` does NOT run before W4 (the slot holds a CLASS and
the goal compiler refuses it; only ``("thing", K, V)`` with ``module=`` runs
today). Ruled: **write the literal tuples now** — ``("thing", K, V)`` solved
with ``module=`` explicit, tables of names, handles passed as names.

This is a KNOWING, DATED EXCEPTION to the 2026-09-21 spec's "no term space
in hand-written source" (docs/superpowers/specs/2026-09-21-python-boundary-
atom-and-string-design.md), taken because: the sites' bodies already run
the all-solve convention; no engine change is needed; the seam form is
parked (todo/seam-handle-form-for-hold-and-call-sites-parked-2026-09-22.md).
The cost the spec names is real (the atoms-flip sweep) and is accepted for
these 31 sites in 5 bodies. At W4 landing the same sites may move to
``(m.thing, K, V)`` (no literal, no ``module=``) — the todo says when to
look. The downstream lane holds a downstream-body edit that reverses a spec
until the operator confirms it to them DIRECTLY; that confirmation is theirs
to give, not this file's.
