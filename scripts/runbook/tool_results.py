"""Runbook check: tool results worded by the hub (design communication-protocols.md
sections 3.3 and 8).

What a courtyard tool returns to a model is written by the hub and forwarded by the
adapter, so every adapter shows the same words. This script makes the calls an adapter
makes and prints what the hub answers:

  1. A send on a supervised line: held at the gate.
  2. A send on an auto-pass line to an agent that is not connected: accepted.
  3. A refusal (a second send before the answer), as the model reads it.
  4. A close by the initiator.
  5. A send to the operator: delivered.
  6. An acknowledgement with a token no check is waiting for.

Changes no courtyard-wide setting; its two throwaway dummies are removed at the end.
Run against a hub started with `make run`:
    uv run python scripts/runbook/tool_results.py
"""

import os
import time

from courtyard.common.client import HubClient, HubError

HUB = os.environ.get("COURTYARD_HUB_URL", "http://127.0.0.1:2626")
DEAD_ENDPOINT = "http://127.0.0.1:9/push"  # nothing listens: deliveries wait for the pull


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


admin = HubClient(HUB)
stamp = str(time.time_ns())[-7:]
a_name, b_name = f"res-a-{stamp}", f"res-b-{stamp}"
_, a_token = admin.register_agent(a_name, "dummy", "runbook sender")
_, b_token = admin.register_agent(b_name, "dummy", "runbook peer")
a = HubClient(HUB, name=a_name, token=a_token)
b = HubClient(HUB, name=b_name, token=b_token)
line = admin.link(a_name, b_name)
print(f"registered throwaway dummies {a_name} and {b_name}")

try:
    hr("1. HELD AT THE GATE  (supervised line)")
    admin.set_mode(line.id, "supervised")
    held = a.send(b_name, "may I restart the staging db?")
    print(held.result)
    admin.decide(held.id, "drop")

    hr("2. ACCEPTED  (auto-pass line, recipient not connected)")
    admin.set_mode(line.id, "auto_pass")
    print(a.send(b_name, "which port does the staging db use?").result)

    hr("3. A REFUSAL, AS THE MODEL READS IT  (a second send before the answer)")
    try:
        a.send(b_name, "hello?")
    except HubError as exc:
        print(exc.rendered)

    hr("4. CLOSE BY THE INITIATOR")
    b.inbox()
    b.send(a_name, "5433")
    print(a.close_thread(b_name).result)

    hr("5. DELIVERED  (the operator's end of a line is the WebUI)")
    print(a.send("operator", "staging db is on 5433").result)

    hr("6. AN ACKNOWLEDGEMENT NO CHECK IS WAITING FOR")
    a.attach(DEAD_ENDPOINT, "channel-token")
    print(a.ack_delivery("not-a-token")[1])
finally:
    for client, name in ((a, a_name), (b, b_name)):
        client.close()
        admin._call("DELETE", f"/api/agents/{name}")
    admin.close()
    print("\n(cleaned up the throwaway dummies; their lines went to the archive.)")
