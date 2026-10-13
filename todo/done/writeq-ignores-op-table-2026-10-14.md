# writeq/write/write_term ignore the operator table in force (2026-10-14)

The ISO writers (`writeq/1`, `write/1`, `writeln/1`, `write_term/2`,
`format/1,2`'s `~w`/`~q`, `write_to_string/2`) printed with a frozen copy of
Scryer's default table, `_WQ_OPS` in `clausal/terms.py`. Reading follows
`op/3`, writing did not. So after an `op/3` the text could differ from what
Scryer prints, and often did not read back under the table that produced it:

| op/3 in force | term | Scryer / Ulrich | engine before |
|---|---|---|---|
| `op(700, xfx, -)` | `-(-(1,2),3)` | `(1-2)-3` | `1-2-3` (syntax error under xfx) |
| `op(200, xfx, ^)` | `2^(3^4)` | `2^(3^4)` | `2^3^4` |
| `op(200, fx, -)` | `-(-(a))` | `- (-a)` | `- -a` |
| `op(0, fy, +)` | `+(1)` | `+(1)` | `+1` (syntax error, #67) |
| `op(0, fy, -)` | `-(1)` | `-(1)` (#136) | `- (1)` |
| `op(9, fy, fy), op(9, yf, yf)` | `yf(fy(1))` | `(fy 1)yf` (#150) | `yf(fy(1))` |

Ulrich rows failing then: #136, #149–#156, #319, #201, #207/#209/#256,
#215/#248/#249, #234, #251–#255, #266/#267, #274, #304, #355, plus #132,
#133, #169, #181, #208, #290, #333, #336, #341.

## Resolved

`clausal/terms.py`:

- `term_write(..., ops=table)` writes with an explicit `OperatorTable`. It
  defaults to `_WQ_OPS`, and the table in force is held in the `_WQ_TABLE`
  contextvar while a term is written.
- Operators are written with the brackets that priority and associativity
  need. Postfix operators (`xf`, `yf`) are written too.
- A prefix or infix term whose last operand would take in a following
  operator of equal priority is bracketed on the left: `(fy 1)yf`,
  `(1 xfy 2)yf`.
- An operator atom used as an operand is bracketed, postfix ones included:
  `('.')'.'`.
- Layout goes between two quoted tokens (`' op' '1'`) and between `0` and a
  quote (`0 'f '`). `- (1 yf)` gets brackets, as Scryer writes it.
- An operator that `op(0, …)` removed is written in canonical form.
- `write_canonical/1` and `ignore_ops(true)` still ignore operators.
- **The seam:** `writer_op_table()` is the one place the ISO writers get
  their table. It reads `clausal.tools.prolog_operators.runtime_op_table()`
  by name and uses `runtime_op_table_is_default()` as the fast path. That
  interface belongs to the `op/3`-as-a-goal work. Until it lands, the
  writers print with the default table, exactly as before.
  `_format_term_iso` (`clausal/logic/builtins/io.py`) passes the seam's
  table to `term_write`.
- With the default table the output is byte for byte what it was: 80,000
  renderings were identical at base and head. A user-defined alphabetic
  infix operator gets Scryer's layout (`(fy 1)yfx 2`). A default one keeps
  its old spacing (`(1+2) mod 3`) under any table. That old spacing is
  Fable review finding F7, still open.

Tests: `tests/test_writeq_op_table.py`. It covers:

- the Ulrich rows and the review's op/3 cases, run with explicit tables,
  through the native `.pl` front end and the seam, and against live Scryer;
- the seam itself;
- `ignore_ops`;
- default-table identity;
- a round trip under 4,500 random op tables (write, then read back under the
  same table).

Still open, in the native reader rather than the writer: `b++ ++` with
`yf` and `b yf-1.5` with `xf` do not read back, though Scryer reads both
(Ulrich #160 and #335 too). The round-trip test sends those texts to
Scryer instead.
