% Constants prelude for TREALLA PROLOG -- INCOMPLETE, see below.
%
% !!! KNOWN GAP, measured 2026-09-13: this works for a file with NO
% !!! `:- module(...)` declaration and DOES NOT WORK inside a named module --
% !!! which is what the exporter emits for every real file. So it is not yet
% !!! usable. Shipped with the measurement rather than withheld, because the
% !!! next person should start from what was established, not from zero.
%
% WHY it fails: the expansion output must be UNQUALIFIED (a `:`-qualified term
% inside the expansion list is a type_error(callable) here), so inside
% `:- module(m, ...)` the fact lands in `m`, while these accessors read `user:`
% and find nothing. Making the accessors unqualified does not help either: they
% live in THIS module, so they would read this module rather than `m`.
%
% Two routes not yet tried, for whoever takes it:
%   * have the expansion emit the ACCESSOR clauses into the consuming module
%     alongside the fact, so nothing is read across a module boundary at all
%     (needs "emit the accessors once per file", i.e. some load-time state);
%   * find whether Trealla has a multifile/global declaration that lets one
%     predicate collect clauses from every module.
%
% An `assertz` directive in the expansion output was tried and is WORSE -- it
% fails in both systems.
%
% Expands the `:- constant_number_units(Name, Number, Units)` directives the
% exporter emits for an `expansion` dialect into facts carrying the declaring
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

:- module(cc_trealla, [constant_value/2, constant_number_units/3,
                       module_constant/3, module_constant_units/4]).
:- dynamic(user:module_constant_units/4).
:- dynamic(user:module_constant/3).

user:term_expansion((:- constant_number_units(N, Num, U)),
                    [module_constant_units(M, N, Num, U)]) :-
    prolog_load_context(module, M).
user:term_expansion((:- constant_value(N, V)), [module_constant(M, N, V)]) :-
    prolog_load_context(module, M).

module_constant_units(M, N, Num, U) :- user:module_constant_units(M, N, Num, U).
constant_number_units(N, Num, U) :- user:module_constant_units(_, N, Num, U).
module_constant(M, N, V) :- user:module_constant(M, N, V).
constant_value(N, V) :- user:module_constant(_, N, V).
