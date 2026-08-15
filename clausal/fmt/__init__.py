"""``clausal-fmt`` -- a comment-preserving formatter for ``.clausal`` source.

Three layers share one comment side-table:

1. **capture** (:mod:`clausal.fmt.comments`) -- :mod:`tokenize` harvests the
   comments, the attachment convention files them per node;
2. **transform** (optional) -- an ``ast.NodeTransformer`` whose replacements
   must declare what happens to the replaced node's comments;
3. **emission** (:mod:`clausal.fmt.emit`) -- a style-authoritative emitter that
   never consults source positions and hard-errors on any comment it did not
   emit.
"""

from clausal.fmt.comments import CommentLeakError, CommentTable, attachment_nodes
from clausal.fmt.emit import ArrowRenderError, Emitter, format_source, format_tree
from clausal.fmt.transform import ClausalTransformer

__all__ = [
    "ArrowRenderError",
    "ClausalTransformer",
    "CommentLeakError",
    "CommentTable",
    "Emitter",
    "attachment_nodes",
    "format_source",
    "format_tree",
]
