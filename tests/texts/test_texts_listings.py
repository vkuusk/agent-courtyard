"""Golden: the listings the hub composes (peers, recall, a case file, a note's result)."""

from __future__ import annotations

from texts_golden import blocks, check

from courtyard.common.models import PeerInfo
from courtyard.hub.core import memory, peers


def peer(name, status, **kw) -> PeerInfo:
    return PeerInfo(name=name, type=kw.pop("type", "claude-code"), status=status, **kw)


def test_peers_listing():
    roster = [
        peer(
            "infra-agent",
            "connected",
            description="deploys AWS resources",
            sme_domain="the AWS estate",
            anti_scope="it does not write\nterraform modules",
        ),
        peer("tf-agent", "stale", type="pi", sme_domain="terraform modules"),
        peer("operator", "invited", type="human", description="the human operator"),
    ]
    check(
        "peers",
        blocks(
            [
                ("alone, auto discovery", peers.render([], 0)),
                ("alone, manual discovery", peers.render([], 0, managed=True)),
                ("a roster", peers.render(roster, 0)),
                ("a trimmed roster, manual discovery", peers.render(roster, 4, managed=True)),
            ]
        ),
    )


def test_recall_and_notes():
    records = memory.sample_records()
    case, note = records
    case = case.model_copy(
        update={
            "document": {
                "closed_by": "infra-agent",
                "messages": [
                    {
                        "seq": 1,
                        "sender_name": "infra-agent",
                        "recipient_name": "tf-agent",
                        "kind": "message",
                        "body": "does the vpc module\nsupport ipv6?",
                        "gate_verdict": "return",
                        "gate_note": "say which module version",
                    },
                    {"seq": 2, "kind": "system", "body": "Your message (seq 1) was returned."},
                    {
                        "seq": 3,
                        "sender_name": "tf-agent",
                        "recipient_name": "infra-agent",
                        "kind": "message",
                        "body": "yes, since 4.2",
                        "gate_verdict": "approve",
                    },
                ],
            }
        }
    )
    pending = note.model_copy(update={"status": "pending", "scope": "team"})
    returned = note.model_copy(update={"status": "returned", "gate_note": "too vague"})
    check(
        "recall",
        blocks(
            [
                ("no searchable words", memory.render_listing("the a of", [], searchable=False)),
                ("nothing found", memory.render_listing("vpc ipv6", [])),
                ("a listing, best match first", memory.render_listing("vpc ipv6", records)),
                ("a listing, newest first", memory.render_listing("", [case])),
                ("a case file", memory.render_case(case)),
                ("a note", memory.render_case(note)),
                ("a returned note", memory.render_case(returned)),
                ("note result: accepted", memory.render_note_result(note)),
                ("note result: held", memory.render_note_result(pending)),
            ]
        ),
    )
