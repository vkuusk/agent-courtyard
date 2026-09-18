"""The membership context a session gets at its start (D40): Claude Code from the
SessionStart hook registration writes, pi from the courtyard extension.

One short block: it tells the session that it is a member of a team, which agent it is
(whatever its directory is called), where its messages come from and what the delivery
check is. It exists because the channel cannot vouch for itself: Claude Code wraps every
channel event as untrusted external data, and a session in a fresh directory has nothing
on the user's side saying otherwise (seen live 2026-09-10: a session refused the
delivery check as prompt injection, then a peer's question). pi showed the other side of
the same gap (2026-09-11): the session acked the check, then spent 33 seconds working out
which agent it was, because pi loads the etiquette skill only on demand.

Shared by the hub, which renders it with the current team's name and worded for the
agent's type, and by the fallbacks (the hook command, and the text install renders into
the pi extension), which carry the same text without the name: a session start never
waits on the hub. Light on purpose: everything else about the etiquette rides the MCP
server's instructions (Claude Code), the courtyard skill (pi) and the envelope.
"""

from __future__ import annotations

from courtyard import texts

TOOL_NAMES = texts.render("session.tool_names")


def render(
    agent_name: str, hub_url: str, team_name: str | None = None, agent_type: str = "claude-code"
) -> str:
    host = "pi" if agent_type == "pi" else "claude_code"
    return texts.render(
        "session.membership",
        agent_name=agent_name,
        team=texts.render("session.team", team_name=team_name) if team_name else "",
        hub_url=hub_url,
        arrival=texts.render(f"session.arrival.{host}"),
        ack_tool=texts.render(f"session.ack_tool.{host}"),
        tools=texts.render(f"session.tools.{host}", tool_names=TOOL_NAMES),
        etiquette=texts.render(f"session.etiquette.{host}"),
    )
