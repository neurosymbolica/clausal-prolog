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
