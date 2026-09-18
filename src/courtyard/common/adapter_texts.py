"""What an adapter needs from the texts package (design communication-protocols.md
section 8): its tool definitions, its standing instructions, and the few texts it words
on its own side of the connection (the hub cannot say "the hub is unreachable").

The hub serves this bundle at session start; an adapter that gets no answer uses the
copy packaged with it, which is this same function run locally (Claude Code) or its
output rendered into the extension at install (pi)."""

from __future__ import annotations

from typing import Any

from courtyard import texts

# The texts an adapter words itself, by the key it looks them up with.
LOCAL = (
    "results.inbox_empty",
    "results.noted",
    "results.refused",
    "results.unreachable",
    "results.tool_failed",
    "results.unknown_tool",
    "results.required.to_and_message",
    "results.required.peer",
    "results.required.body",
    "results.required.token",
    "results.bad_limit",
)


def _adapter(agent_type: str) -> str:
    return "pi" if agent_type == "pi" else "claude_code"


def tools(agent_type: str) -> list[dict[str, Any]]:
    """The tool definitions in the shape the agent's host takes them: MCP `tools/list`
    entries for Claude Code, `registerTool` fields for pi."""
    declared = texts.section(f"tools.adapter.{_adapter(agent_type)}")
    out = []
    for d in texts.get("tools.definitions"):
        description = d["description"].format(**declared)
        if _adapter(agent_type) == "pi":
            entry = {"name": d["name"], "label": d["label"], "description": description}
            if d.get("guidelines"):
                entry["promptGuidelines"] = d["guidelines"]
            entry["parameters"] = d["parameters"]
        else:
            entry = {
                "name": d["name"],
                "description": description,
                "inputSchema": d["parameters"],
            }
        out.append(entry)
    return out


def etiquette(agent_type: str) -> str:
    """The etiquette: one content for every adapter, with the adapter's declared
    differences filled in (how deliveries arrive, which tools need no approval)."""
    return texts.render(
        "etiquette.body", **texts.section(f"etiquette.adapter.{_adapter(agent_type)}")
    )


def bundle(agent_type: str) -> dict[str, Any]:
    instructions = None
    if _adapter(agent_type) == "claude_code":  # pi reads the etiquette as a skill on disk
        instructions = etiquette(agent_type)
    return {
        "tools": tools(agent_type),
        "instructions": instructions,
        "local": {key: texts.get(key) for key in LOCAL},
    }


def fill(template: str, **values: Any) -> str:
    """A fetched template with its variables filled in, the way the pi extension fills
    them: plain `{name}` placeholders only."""
    return template.format(**values)
