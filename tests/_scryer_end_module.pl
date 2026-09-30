% clausal: no-collect
% (Scryer-only oracle plumbing, not a Clausal test file.)
% Consulted by tests/_oracles.py AHEAD of a program that mentions
% end_module: Clausal accepts ISO 13211-2's `:- end_module(Name).`, Scryer
% refuses it (error(domain_error(directive,end_module/1),load/1)) and fails
% the whole file.  This drops the directive at load instead.
:- multifile(term_expansion/2).
term_expansion((:- end_module(_)), []).
