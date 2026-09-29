% A package facade: module/2 re-exports what it imports from its submodule.
% The atom entry class_comparison (D11(a)) imports nothing; the facade
% USES the atom, so it is auto-declared here, and a seam importer can name it.
:- module(s3pkg, [classify/2, pt/2, origin/1]).
:- use_module(s3pkg/kinds, [classify/2, class_comparison, pt/2, origin/1]).
