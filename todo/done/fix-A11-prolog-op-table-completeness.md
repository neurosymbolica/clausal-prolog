# fix(A11-F026/F027/F041): operator tables missing ISO + SWI entries

- F026: ISO Table 7 ops absent from every table: `700 xfx @< @> @=< @>=`,
  `200 xfy ^`, `400 yfx div` — `bagof(X, Y^p(X,Y), L)` cannot parse at all
  (`^` is advertised by BUILTIN_NAME_MAP itself).
- F027: SWI prefix directives (`1150 fx dynamic discontiguous table multifile
  initialization …`) absent — documented `:- dynamic p/1.` is a ParseError
  (paren form works). importing_prolog.md:136 lists dynamic as supported.
- F041: `*->`, SWI body `|`, `=@=`/`\=@=` absent — the standing contract says
  `(*->)/2` is "rejected by design (clear error)"; users get generic token
  soup. Add the ops so the PARSER produces the AST and prolog_to_clausal
  rejects with the designed message.

**File**: tools/prolog_operators.py (_load_iso :111-148, _load_swi :152-158).
**Tests**: test_F026, test_F027 (+guard), test_F041 (xfail).
