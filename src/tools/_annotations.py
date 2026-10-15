"""MCP tool annotations: what a tool may do to the data behind it.

Clients read these hints to decide what needs the user's approval; a tool
without them counts as destructive. Pick by the worst thing the tool can do:

- READ_ONLY: only reads.
- ADDITIVE: creates something new and changes nothing that already exists.
- DESTRUCTIVE: changes or removes something that already exists.

No write promises that repeating it is harmless (idempotentHint stays False),
and every tool talks to one fixed system, never the open web (openWorldHint
False). tests/test_tool_annotations.py holds the per-tool classification.
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)
