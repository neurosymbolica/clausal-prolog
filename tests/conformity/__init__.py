# ISO Prolog conformity tests ported to clausal.
#
# Source: https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing
#
# The original test suite contains 365 test cases evaluating conformance with
# ISO/IEC 13211-1:1995 (Prolog).  Since clausal uses Python syntax rather than
# Prolog syntax, the vast majority of those tests exercise Prolog-specific
# parsing and term-writing facilities that have no clausal equivalent.
#
# This package ports what is semantically applicable and documents the rest as
# not-applicable, giving a clear picture of the delta between clausal and ISO
# Prolog.
