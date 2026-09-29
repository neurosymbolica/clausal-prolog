# Implement Prolog's `format/2` (`~` directives) — 2026-09-07

**Context.** The strings program (spec `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md`) made `write/1`, `writeq/1`, `write_canonical/1` and `write_term/2` follow ISO exactly (operator ruling 2026-09-07): a string prints as the char list it is, `[a,b,c]`. Clausal's text-printing convenience (a string as its text, atoms bare) moved to `write_text/1`, `writeln_text/1`, `write_text_to_string/2`, which is where f-strings go (`writeln_text(f"X is {X}")`). That leaves the standard Prolog way of printing text — `format/2` with `~s`, `~a`, `~w`, `~q`, `~d`, `~n`, `~p`, column/padding directives — unimplemented.

**Ask.** `format/1,2` (and `format/3` once streams exist) per the de-facto standard (SWI/Scryer `library(format)`): `~w` write, `~q` writeq, `~a` atom, `~s` string/char list as text, `~d` integer (with `~Nd` grouping), `~f`/`~e`/`~g` floats, `~n` newline, `~c` char code, `~e`, `~t~|` column stops and padding, `~*c` argument-taken counts, `~~` literal, `~i` ignore. Errors per Scryer (`format_error`/`type_error` on a bad directive or argument). Also `format_to_string`/`with_output_to` equivalents once decided.

**Interplay.** f-strings stay (they are valuable and typed); `format/2` is for ISO-style programs and for the translator (`.pl` imports that use `format/2` currently fail). `write_text/1` remains the cheap path; `format("~s", ["abc"])` and `write_text("abc")` print the same.

**Scryer reference.** `/workspace/scryer-prolog/target/release/scryer-prolog`, `library(format)` — verify directive-by-directive against it, as the strings program did for the writers (`implementation_plans/scryer-comparison-queries-2026-09-07.md` shows the method).

## Closed 2026-09-30

Implemented on fix/todo-batch-4-2026-09-30 as a port of Scryer's
`library(format)` (src/lib/format.pl), since Scryer is the reference: ~w ~q
~a ~s ~d ~Nd ~ND ~NU ~NL ~f ~Nf ~r ~Nr ~R ~NR ~n ~Nn ~i ~~ ~t ~`Ct ~| ~N| ~N+
and ~* for any N, with Scryer's cell/glue layout and its errors (context
format_//2). Scryer does NOT support ~c, ~e, ~g or ~p -- they are
domain_error(format_string, _) here too; add them only with a ruling (SWI has
them). format/3 and format_to_string wait for streams. `format_to_text` is the
pure text form. Pinned by tests/test_format_scryer.py (42 rows vs Scryer).
