% clausal: no-collect
% Constants prelude for TREALLA PROLOG.
%
% Expands the `:- constant_number_units(Name, Number, Units)` directives the
% exporter emits for an `expansion` dialect into facts carrying the declaring
% MODULE -- the same compile-time module insertion the Clausal engine performs,
% done here at load time instead.
%
% LOAD IT WITH `:- ensure_loaded(...)`, NOT `use_module`, and note this file has
% NO `:- module(...)` declaration. Both are load-bearing, measured 2026-09-13:
%
%   * Trealla's `prolog_load_context(module, M)` inside a `user:term_expansion`
%     clause reports the module where the HOOK IS DEFINED, not the file being
%     loaded. With the hook in a named prelude module it answered `cc_trealla`
%     for every file. With no module declaration the hook lives in `user` and it
%     answers the consuming module correctly.
%   * the expansion emits facts under the PUBLIC predicate names directly, so
%     nothing is read across a module boundary. An earlier version kept the
%     facts in `user:` and read them from accessors here, which worked for a
%     file with no module declaration and silently found nothing inside a named
%     module -- i.e. on every real exported file.
%
% A consuming file needs `:- discontiguous` for the two predicates if its
% declarations are not contiguous.
%
% WHY THERE ARE TWO PRELUDES, one per system: Scryer and Trealla want opposite
% things. Scryer fires an UNQUALIFIED imported `term_expansion/2`, refuses a
% `user:`-qualified clause head, and rejects `ensure_loaded/1` as a directive.
% Trealla will not fire an unqualified imported hook at all. That divergence is
% the argument for the per-dialect `constants` capability rather than one
% emitter.
%
% `prolog_load_context/2` is NOT ISO -- which is why this sits behind the
% `expansion` capability; the `iso` dialect needs no prelude, because the
% exporter fills the module in itself.
%
% See docs/superpowers/specs/2026-09-13-exporter-option-3-design.md

user:term_expansion((:- constant_number_units(N, Num, U)),
                    [ constant_number_units(N, Num, U),
                      module_constant_units(M, N, Num, U) ]) :-
    prolog_load_context(module, M).
user:term_expansion((:- constant_value(N, V)),
                    [ constant_value(N, V), module_constant(M, N, V) ]) :-
    prolog_load_context(module, M).
