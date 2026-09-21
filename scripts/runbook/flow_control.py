"""Runbook check: message transfer control after communication-protocols.md section 7.

  1. Default: a new agent line starts on auto-pass; the first message goes through.
  2. A report to the operator awaits nothing: the line stays idle, its thread ends at
     once, and a second report follows without a turn violation.
  3. A release ends the open thread as `locked` and tells both agents.
  4. `serves`: an ask made on behalf of an open thread carries the link, and the answer
     names whom the result is for; a declaration with no such thread is refused.
  5. The team-wide brake: every agent line to supervised, a new line starts supervised,
     and back to the default.

FLIPS THE BRAKE (courtyard-wide): run it on its own throwaway hub.
    uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name flow
    COURTYARD_HUB_URL=<printed url> uv run python scripts/runbook/flow_control.py
    uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py stop --name flow
"""

import os
import time

from courtyard.common.client import HubClient, HubError

HUB = os.environ.get("COURTYARD_HUB_URL", "http://127.0.0.1:2626")


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def footer(rendered: str) -> str:
    return rendered.rsplit("────\n", 1)[1].replace("</courtyard-message>", "").rstrip()


admin = HubClient(HUB)
stamp = str(time.time_ns())[-7:]
names = {k: f"flow-{k}-{stamp}" for k in ("lead", "helper", "third")}
tokens = {k: admin.register_agent(n, "dummy", "runbook")[1] for k, n in names.items()}
lead, helper, third = (HubClient(HUB, name=names[k], token=tokens[k]) for k in names)
print("registered throwaway dummies", ", ".join(names.values()))

try:
    hr("1. DEFAULT: A NEW AGENT LINE STARTS ON AUTO-PASS")
    print("settings.default_line_mode:", admin.settings()["default_line_mode"])
    ask = lead.send(names["helper"], "which port is staging on?")
    print("first message status     :", ask.status, "|", ask.result)

    hr("2. A REPORT TO THE OPERATOR AWAITS NOTHING")
    report = lead.send("operator", "started on the staging inventory")
    print("result :", report.result)
    line = next(ln for ln in admin.lines() if ln.id == report.line_id)
    print("line   :", line.state, "| open thread:", line.open_thread)
    print("threads:", [t.state for t in admin.line_threads(report.line_id)])
    again = lead.send("operator", "still going")
    print("second report:", again.status, "(no turn violation)")

    hr("3. RELEASE ENDS THE THREAD AS LOCKED AND TELLS BOTH AGENTS")
    helper.inbox()  # the ask from step 1 is now delivered and unanswered
    admin.release(ask.line_id)
    print("threads:", [t.state for t in admin.line_threads(ask.line_id)])
    for who, client in (("lead", lead), ("helper", helper)):
        for m in client.inbox():
            if m.kind == "system":
                print(f"{who} was told: {m.body}")

    hr("4. SERVES: THE ANSWER NAMES WHOM THE RESULT IS FOR")
    admin._call("POST", "/api/operator/send", {"to": names["lead"], "body": "how many nodes?"})
    lead.inbox()
    lead.send(names["helper"], "how many nodes are in the inventory?", serves="operator")
    helper.inbox()
    helper.send(names["lead"], "12 nodes")
    (answer,) = [m for m in lead.inbox() if m.kind == "message"]
    print(footer(answer.rendered).splitlines()[-2:])
    try:
        third.send(names["helper"], "x", serves=names["lead"])
    except HubError as exc:
        print("a declaration with no such open thread:", exc.rendered)

    hr("5. THE TEAM-WIDE BRAKE")
    admin.set_mode(ask.line_id, "auto_pass")
    result = admin._call("POST", "/api/lines/brake", {"on": True})
    print(
        "brake on : changed",
        len(result["changed"]),
        "line(s) ->",
        sorted(
            {
                ln.mode
                for ln in admin.lines()
                if "operator" not in (ln.agent_a_name, ln.agent_b_name)
            }
        ),
    )
    held = third.send(names["lead"], "a new line while braked")
    print(
        "new line while braked:",
        held.status,
        "|",
        next(ln.mode for ln in admin.lines() if ln.id == held.line_id),
    )
    admin.decide(held.id, "drop")
    result = admin._call("POST", "/api/lines/brake", {"on": False})
    print(
        "brake off: changed",
        len(result["changed"]),
        "line(s) ->",
        sorted(
            {
                ln.mode
                for ln in admin.lines()
                if "operator" not in (ln.agent_a_name, ln.agent_b_name)
            }
        ),
    )
    print("settings.brake:", admin.settings()["brake"])
finally:
    for client, name in ((lead, names["lead"]), (helper, names["helper"]), (third, names["third"])):
        client.close()
        admin._call("DELETE", f"/api/agents/{name}")
    admin.close()
    print("\n(cleaned up the throwaway dummies; their lines went to the archive.)")
