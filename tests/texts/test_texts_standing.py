"""Golden: the standing texts (membership block, instructions, pi skill, tool definitions)."""

from __future__ import annotations

import json

from texts_golden import blocks, check

from courtyard.adapters.claude_code.mcp_server import INSTRUCTIONS, TOOLS
from courtyard.common import session_context
from courtyard.hub.core.install import pi_skill

HUB = "http://127.0.0.1:2626"


def test_membership_block():
    entries = [
        (
            f"{host}, {'with' if team else 'without'} a team name",
            session_context.render("agent-x", HUB, team, host),
        )
        for host in ("claude-code", "pi")
        for team in ("team-y", None)
    ]
    check("membership_block", blocks(entries))


def test_claude_code_instructions():
    check("claude_code_instructions", INSTRUCTIONS)


def test_pi_skill():
    check("pi_skill", pi_skill("agent-x"))


def test_claude_code_tool_definitions():
    check("claude_code_tools", json.dumps(TOOLS, indent=2, ensure_ascii=False) + "\n")
