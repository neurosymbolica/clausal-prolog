"""The comment-repair pass: its prompt, and the fence around its output.

Conservation is mechanical; placement is not.  The formatter guarantees that
every comment survives, and nothing more -- a goal that moved takes its anchor
comment with it whether or not the comment still reads correctly in its new
company, and a rewrite that folded two goals into one leaves a paragraph that
describes a shape the file no longer has.

Fixing that is a reading job, so it goes to a model: hand it the before/after
diff and the file, and let it re-place and re-word.  Ideally the same model
that authored the file, while the subject matter is still in its context.

Nothing here runs the pass.  This module builds the prompt and guards the
result: :func:`accept_repair` takes a pass wholesale or not at all.  Partial
acceptance would mean deciding which of the model's edits were comment edits,
which is the judgement call the fence exists to avoid.
"""

from __future__ import annotations

from clausal.fmt.verify import comments_only_change, unified_diff

INSTRUCTIONS = """\
The file above was reformatted (and possibly rewritten) by clausal-fmt.  Every
comment in it survived the change, but a surviving comment is not necessarily a
correct one: an anchor may now sit above a different goal than the one it
describes, a paragraph may describe a shape the code no longer has, and a group
that was split across a rearrangement may need rejoining or rewording.

Read the diff, then edit {path} in place so its comments read correctly against
the code as it now stands.  Move them, merge them, split them, reword them,
delete the ones that are now false.

Change comments only.  Do not touch code -- not a goal, not an argument, not a
name, not the layout.  The result is re-parsed and compared against the tree you
were given, and a pass that changed anything else is rejected in full, including
the comment work you did in the same edit.
"""


class RepairRejected(Exception):
    """The repair pass touched more than comments; the whole pass is discarded."""

    def __init__(self, diff: str):
        self.diff = diff
        super().__init__(
            "the comment-repair pass changed code or layout and was rejected in "
            f"full:\n{diff}"
        )


def build_repair_prompt(path: str, before: str, after: str) -> str:
    """The prompt for a comment-repair pass over one file."""
    diff = unified_diff(before, after, f"{path} (before)", f"{path} (after)")
    return f"{diff}\n{INSTRUCTIONS.format(path=path)}"


def accept_repair(pre_pass: str, post_pass: str) -> str:
    """Return the repaired source, or raise -- the pass is all or nothing."""
    if not comments_only_change(pre_pass, post_pass):
        raise RepairRejected(
            unified_diff(pre_pass, post_pass, "before repair", "after repair")
        )
    return post_pass
