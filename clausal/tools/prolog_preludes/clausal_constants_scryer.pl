% clausal: no-collect
% Constants prelude for SCRYER PROLOG.
%
% Expands the `:- constant_number_units(Name, Number, Units)`,
% `:- constant_number_currency(Name, Number, Currency)` and
% `:- constant_value(Name, Value)` directives the exporter emits for an
% `expansion` dialect into the accessor fact and a fact carrying the declaring
% MODULE, obtained from `prolog_load_context/2` inside the hook -- the same
% compile-time module insertion the Clausal engine performs, done on this side.
%
% WHY THERE ARE TWO PRELUDES, one per system. Measured 2026-09-13 against both
% real binaries; a single portable file does not work, and the two want
% OPPOSITE things:
%
%   Scryer   an UNQUALIFIED `term_expansion/2` in an imported module FIRES for
%            the importing file, and unqualified expansion output resolves.
%            A `user:`-qualified clause head is REFUSED --
%            permission_error(modify, not_declared_multifile_or_discontiguous)
%            -- and a multifile declaration in this file does not authorise it.
%   Trealla  an unqualified imported hook does NOT fire (the directive is
%            executed instead: "unknown directive"). It needs `user:term_expansion`,
%            and the facts land in `user`, so the accessors must read `user:`.
%            But a `:`-qualified term INSIDE the expansion list is a
%            type_error(callable), so the output stays unqualified.
%
% `prolog_load_context/2` is NOT ISO. That is why this is behind the
% `expansion` dialect capability rather than in the emitter unconditionally;
% the `iso` dialect needs no prelude at all, because the exporter fills the
% module in itself.
%
% See docs/superpowers/specs/2026-09-13-exporter-option-3-design.md

:- module(cc_scryer, [module_constant/3, module_constant_units/4]).
:- dynamic(module_constant_units/4).
:- dynamic(module_constant/3).

% THE ACCESSORS ARE FACTS IN THE DECLARING MODULE, as in the Trealla prelude.
% `constant_number_units/3` and `constant_value/2` used to be rules HERE,
% reading this module's own (always empty) tables, while the expansion put the
% facts in the declaring module -- so a query from inside a named module, the
% normal use, answered false for every constant (measured 2026-10-22). The
% expansion now writes the accessor fact beside the module-carrying one, so
% each module answers for its own constants, as the engine's builtins do.
term_expansion((:- constant_number_units(N, Num, U)),
               [constant_number_units(N, Num, U),
                module_constant_units(M, N, Num, U)]) :-
    prolog_load_context(module, M).
% A currency constant is recorded exactly as a units one: the engine has no
% constant_number_currency/3 predicate, and `constant_number_units/3` answers
% a -constant_number_currency declaration. Without this clause Scryer refused
% the directive -- domain_error(directive, constant_number_currency/3) -- and
% the rest of the module did not load.
term_expansion((:- constant_number_currency(N, Num, U)),
               [constant_number_units(N, Num, U),
                module_constant_units(M, N, Num, U)]) :-
    prolog_load_context(module, M).
term_expansion((:- constant_value(N, V)),
               [constant_value(N, V), module_constant(M, N, V)]) :-
    prolog_load_context(module, M).
