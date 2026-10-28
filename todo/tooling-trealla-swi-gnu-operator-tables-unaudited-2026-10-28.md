# The trealla (and swi, gprolog) tooling operator tables are not checked against the real systems

The `scryer` and ISO tables in `clausal/tools/prolog_operators.py` are now
pinned against Scryer's `current_op/3`
(`tests/test_operator_tables_vs_scryer.py`, 2026-10-28). The others are not.
Against Trealla (`tpl`, with
`:- use_module(library(clpz))` loaded), `trealla_default` lacks:

    op(100,fy,++) op(100,fy,--) op(100,fy,:) op(100,fy,@) op(1050,xfy,*->) op(1105,xfy,'|') op(1199,fx,attribute) op(150,fx,#) op(1,xfy,'$||') op(200,fy,+) op(400,yfx,rdiv) op(450,xfx,..) op(500,fx,?) op(700,xfx,as) op(700,xfx,in) op(700,xfx,ins) op(710,fy,#\) op(720,yfx,#/\) op(730,yfx,#\) op(740,yfx,#\/) op(750,xfy,#==>) op(750,yfx,#<==) op(760,yfx,#<==>) op(900,fx,$) op(900,fx,$-) op(950,fy,*) 

and has, beyond Trealla's own: nothing.

Some of these are Trealla internals (`'$||'` at 1, `attribute` at 1199, `$` and `$-` at 900) and
should stay out, as Scryer's `non_counted_backtracking` did. The rest
(`rdiv`, prefix `+`, the clpz set, `'|'` at 1105, `*->`, `as`)
should match. The fix is the same as for Scryer: dump `current_op/3` into a
fixture and pin the table to it. SWI and GNU Prolog are not installed on the
box, so their tables cannot be checked here.
