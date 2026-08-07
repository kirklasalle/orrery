"""
Operator-facing command line tools.

These are deliberately separate from the library. A cycle engine should not carry the code
that mints keys and approves configurations, and the audit flagged `__main__` blocks inside
library modules as exactly the wrong place for this.
"""
