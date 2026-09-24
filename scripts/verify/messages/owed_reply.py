"""Verification: an answer says where its result belongs (design
communication-protocols.md sections 3.3 and 6.3).

The hub cannot see a terminal, so it cannot know that a user typed a request there. It
does know on which lines an agent is still awaited, and the footer of every answer says
so. This script plays both cases and prints what the asking agent reads:

  1. A request typed in the agent's terminal: the agent asks a peer, and the answer's
     footer says nobody on the board is waiting, so the result belongs in the terminal.
  2. A request from the operator on the board: the same ask, and the answer's footer
     names the operator as still owed a reply.
  3. The send results: an ask leaves the line awaiting a reply; an answer says that
     nobody owes a reply on that line.

Changes no courtyard-wide setting; its two throwaway dummies are removed at the end.
Run against a hub started with `make run`:
    uv run python scripts/verify/messages/owed_reply.py
"""

import os
import time

from courtyard.common.client import HubClient

HUB = os.environ.get("COURTYARD_HUB_URL", "http://127.0.0.1:2626")


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def footer(rendered: str) -> str:
    return rendered.rsplit("────\n", 1)[1].replace("</courtyard-message>", "").rstrip()


admin = HubClient(HUB)
stamp = str(time.time_ns())[-7:]
lead_name, helper_name = f"owed-lead-{stamp}", f"owed-helper-{stamp}"
_, lead_token = admin.register_agent(lead_name, "dummy", "verify lead")
_, helper_token = admin.register_agent(helper_name, "dummy", "verify helper")
lead = HubClient(HUB, name=lead_name, token=lead_token)
helper = HubClient(HUB, name=helper_name, token=helper_token)
line = admin.link(lead_name, helper_name)
admin.set_mode(line.id, "auto_pass")
print(f"registered throwaway dummies {lead_name} and {helper_name} (their line on auto-pass)")

try:
    hr("1. THE USER TYPED THE REQUEST IN THE LEAD'S TERMINAL  (the board holds no ask)")
    ask = lead.send(helper_name, "do you have any CSV files?")
    helper.inbox()
    answer = helper.send(lead_name, "no CSV files")
    (delivered,) = lead.inbox()
    print(footer(delivered.rendered))
    lead.close_thread(helper_name)

    hr("2. THE OPERATOR ASKED ON THE BOARD  (the lead owes the operator a reply)")
    admin._call("POST", "/api/operator/send", {"to": lead_name, "body": "any CSV files?"})
    lead.inbox()
    lead.send(helper_name, "do you have any CSV files?")
    helper.inbox()
    helper.send(lead_name, "no CSV files")
    (delivered,) = lead.inbox()
    print(footer(delivered.rendered))

    hr("3. THE SEND RESULTS  (what each sender was told)")
    print("the ask   :", ask.result)
    print("the answer:", answer.result)
finally:
    for client, name in ((lead, lead_name), (helper, helper_name)):
        client.close()
        admin._call("DELETE", f"/api/agents/{name}")
    admin.close()
    print("\n(cleaned up the throwaway dummies; their lines went to the archive.)")
