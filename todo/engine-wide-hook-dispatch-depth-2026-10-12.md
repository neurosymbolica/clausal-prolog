# An engine-wide hook-dispatch depth, beside the per-trail Trail.hooks_running (2026-10-12)

`Trail.hooks_running` (a750f58c) counts hook dispatch PER TRAIL. A hook body that builds a fresh
`Trail()` and drives goals or calls a library on it sees 0, so the library thinks it is at a goal. The
CLP(Q) port's fail-closed refusals (R30) and its queue trigger (R28c) are bypassed that way, and the
hook gets a wrong answer silently. `docs/coroutining.md` allows a driver on a fresh trail inside a hook.

Fix: a process-wide (thread-local) dispatch depth, raised and lowered in `fire_wakeups` next to the
per-trail counter, exposed as a function. Libraries refuse or queue on either counter. Alternatively,
forbid a fresh-trail driver inside a hook, which may be too strong.

The port pins the current limit with a test that flips when this lands.
Good to ride the catch/3 transparency engine candidate.
