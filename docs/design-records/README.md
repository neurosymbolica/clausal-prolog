# Design records

Long-form design records, kept as HTML because they are read outside a terminal.

    terms-as-tuples.html    The representation change: functor-first tuples, retiring
                            PredicateMeta, and how one module reaches another.
                            Published at
                            https://claude.ai/code/artifact/deb7779b-2aa8-467c-8d92-3c72284ef111

    asyncio-and-tabling.html
                            Queries on Python's asyncio loop: the model, the greenlet
                            driver, the five rules that keep SLG tables sound when
                            queries interleave or die, and what the review rounds found.
                            Published at
                            https://claude.ai/artifact/TuWicpbxhA8mcJeKTbMsLg

**The file is the source; the URL is a rendering of it.** Edit the file, then republish to
the SAME url to keep the link stable — publishing without it creates a second artifact and
the link someone has bookmarked goes stale in place, which is worse than a dead one.

A record is a summary, not the authority. The authority is:

    docs/superpowers/specs/            the reasoning, the measurements, the rulings
    implementation_plans/SESSION-HANDOFF-*.md   what is landed, open, and next
    tools/predmeta_census/             the instruments, and their controls (deleted
                                       2026-09-26 with the class they measured;
                                       in the git history)

Keep the record's status line (branch, head, gate) current when you republish. A design
record that is four hours stale will mislead on exactly the things that changed.
