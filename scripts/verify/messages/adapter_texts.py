"""Verification: the texts an adapter fetches at session start (design
communication-protocols.md section 8).

An adapter asks the hub for its tool definitions, its standing instructions and the few
texts it words on its own side, and falls back to the copy packaged with it. This script
asks the way an adapter does and prints what comes back:

  1. The bundle for a Claude Code agent: MCP tool entries and the instructions.
  2. The bundle for a pi agent: the same tools in pi's shape, labels and guidelines
     included, and no instructions (pi's etiquette is a skill on disk).
  3. The declared differences between the two, and nothing else differing.
  4. The fallback: what the Claude Code adapter uses when no hub answers.

Changes no courtyard-wide setting; its two throwaway agents are removed at the end.
Run against a hub started with `make run`:
    uv run python scripts/verify/messages/adapter_texts.py
"""

import difflib
import os
import time

import httpx

from courtyard.adapters.claude_code import mcp_server
from courtyard.common.client import HubClient

HUB = os.environ.get("COURTYARD_HUB_URL", "http://127.0.0.1:2626")


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


admin = HubClient(HUB)
stamp = str(time.time_ns())[-7:]
names = {"claude-code": f"txt-cc-{stamp}", "pi": f"txt-pi-{stamp}"}
for agent_type, name in names.items():
    admin.register_agent(name, agent_type, "verify throwaway")
print(f"registered throwaway agents {', '.join(names.values())}")

try:
    bundles = {
        t: httpx.get(f"{HUB}/api/agents/{n}/texts", timeout=5).json() for t, n in names.items()
    }

    hr("1. CLAUDE CODE  (MCP tool entries + the instructions)")
    cc = bundles["claude-code"]
    print("tools       :", ", ".join(t["name"] for t in cc["tools"]))
    print("entry keys  :", sorted(cc["tools"][0]))
    print("instructions:", cc["instructions"][:110].replace("\n", " ") + "...")

    hr("2. PI  (the same tools in pi's shape; no instructions)")
    pi = bundles["pi"]
    print("tools       :", ", ".join(t["name"] for t in pi["tools"]))
    print("entry keys  :", sorted(pi["tools"][0]))
    print("guidelines  :", pi["tools"][0].get("promptGuidelines"))
    print("instructions:", pi["instructions"])

    hr("3. WHAT DIFFERS BETWEEN THE TWO  (only the declared variables)")
    for c, p in zip(cc["tools"], pi["tools"], strict=True):
        assert c["inputSchema"] == p["parameters"]
        if c["description"] != p["description"]:
            words = difflib.ndiff(p["description"].split(), c["description"].split())
            extra = " ".join(w[2:] for w in words if w.startswith("+ "))
            print(f"{c['name']}: Claude Code adds: {extra}")
    print("own texts identical:", cc["local"] == pi["local"], f"({len(cc['local'])} texts)")
    for key, template in cc["local"].items():
        print(f"  {key}: {template}")

    hr("4. THE FALLBACK  (no hub answers: the packaged copy)")
    fallback = mcp_server.fetch_texts("http://127.0.0.1:9", names["claude-code"])
    print("packaged copy used      :", fallback is mcp_server.PACKAGED)
    print("same wording as the hub :", fallback == cc)
finally:
    for name in names.values():
        admin._call("DELETE", f"/api/agents/{name}")
    admin.close()
    print("\n(cleaned up the throwaway agents.)")
