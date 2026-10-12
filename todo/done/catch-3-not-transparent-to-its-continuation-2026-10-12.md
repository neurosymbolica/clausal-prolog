# catch/3 is not transparent to the goals after it (both strategies)

Found 2026-10-12 by the review of the inline-goal drain candidate. It reproduces on main a3fbb271 in
both compile strategies.

```seam
chk(Y) <- ...                      # throws `later` when Y is unbound
w5(Y) <- (catch(true, E, Y is E), chk(Y))
```

This gives `['later']`: the catcher catches a ball thrown by `chk(Y)`, which runs AFTER `catch/3` has
succeeded. ISO 7.8.9 and Scryer let that ball escape: catch/3 only protects its Goal argument.

**Cause:** the lowering's `try` wraps the continuation `k` as well as the goal. In a generator-based
lowering, the continuation runs while the `try` frame is still active.

**Related:**
- Since the inline-comparison drain, `nc2(Y) <- (catch(freeze(X, throw(oops)), _, Y is caught), X == 3)`
  catches under shallow, where the base raised (correctly). The woken goal now runs at the comparison,
  and the comparison sits inside the `try`. That is the same root cause reaching one more shape.
- Scryer and ISO raise `oops` there.

**Fix direction:**
- Mark the dynamic extent of the Goal, e.g. a flag on the catch frame that is set while the goal runs
  and cleared around each yield to the continuation.
- The except clause re-raises when the flag is clear.
- Change both strategies' lowerings and the C drive loop where it handles catch frames.
- Tests: w5, nc2, nested catches, and a ball from a goal after the catch inside findall/forall/once.

**Fixed 2026-10-12** on fix/catch-transparency-and-hook-depth-2026-10-12: a flag on the catch frame, set while
the Goal runs and cleared around the continuation, in both strategies (`_compile_catch`); the handler re-raises
when it is clear. No drive-loop change: the C and Python twins only throw into the catcher chain, and a frame
that re-raises passes the ball up. Tests: `tests/test_catch_is_transparent_to_its_continuation.py`.
