# Recursion through an if-then-else condition, once/1, or a cutting catch/3 Recovery is bounded by the Python stack

**Status: OPEN.** Found by the final review of the `.pl` cut series (I-1, 2026-10-16). Documented in docs/importing_prolog.md; the current behaviour is pinned in `tests/iso_l3/test_l3_ite.py`.

## What happens

Each of these runs its goal in a nested Python generator (`_ite_cond`, `_once_gen`, the Recovery sub-generator), which calls the next level through `$tramp_call`. Recursion THROUGH one of them nests Python frames, so it stops at about 330-400 levels at the default `sys.getrecursionlimit()` of 1000. Scryer runs every row below.

```prolog
all_pos([]).
all_pos([X|Xs]) :- ( X > 0, all_pos(Xs) -> true ; fail ).
% length 400:   ( all_pos(L) -> R = yes ; R = no )
%   error(resource_error(stack), _)   (was a raw Python RecursionError)
% length 1000:  ( catch(all_pos(L), _, fail) -> R = yes ; R = no )
%   R = no, silently                  Scryer: R = yes
o(0).
o(N) :- N > 0, N1 is N-1, once(o(N1)).
%  o(2000): 'RecursionError'(...)     Scryer: true
rec(0).
rec(N) :- N > 0, N1 is N-1, catch(throw(x), x, (!, rec(N1))).
%  rec(2000): 'RecursionError'(...)   Scryer: true
```

These are NOT limited (2000 levels measured): cut-free `catch/3`; a `catch/3` whose Goal cuts (`catch((r(N1), !), _, true)`); a cut-free Recovery.

## What was done in the series

The if-then-else lowering catches `RecursionError` at the condition's boundary and throws `error(resource_error(stack), _)` (`exceptions.ite_condition_overflow`). The `try` costs nothing until something raises. once/1's lowering is shared with cut-free code, whose codegen is pinned byte-identical (`tests/test_cut_codegen.py`), so once/1 and the Recovery still surface the Python error.

## To do

1. Lower an if-then-else condition, and once/1's goal, through the trampoline (a StepGenerator the drive loop runs, as the cutting catch/3 Goal already is), so the depth is the heap's, not Python's stack's.
2. Until then, decide whether a stray `RecursionError` should be `error(resource_error(stack), _)` everywhere. The cheap place is `exceptions.python_error_term`, but that is a global change of the `'RecursionError'(Message)` term shape, which `.clausal` code and downstream trees may match.
