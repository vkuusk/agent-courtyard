"""What a courtyard tool returns to the model that called it (design
communication-protocols.md section 3.3), worded by the hub.

The adapters forward these texts verbatim, the way they forward the envelope and the
peers listing (D14): a tool result can state what only the hub knows, and one wording
serves every adapter. The texts live in `courtyard/texts/results.yml`; this module
decides which one applies.
"""

from __future__ import annotations

from courtyard import texts
from courtyard.common.models import Message


def send(message: Message, to: str) -> str:
    """The outcome of a send, from the status the hub gave the message. `to` is the
    recipient as the sender named it."""
    if message.status == "pending_gate":
        outcome = "held"
    elif message.recipient_type == "human" and message.reply_to is None:
        # a report to the operator: delivered, and nothing is waited for (section 7.5)
        outcome = "to_operator"
    else:
        outcome = "delivered" if message.status == "delivered" else "accepted"
        if message.reply_to is not None:
            # an answer leaves nobody waiting on this line: say so (section 3.3)
            outcome += "_answer"
    return texts.render(f"results.send.{outcome}", seq=message.seq, to=to)


def close(peer: str) -> str:
    return texts.render("results.close", peer=peer)


def ack(confirmed: bool) -> str:
    return texts.render("results.ack.confirmed" if confirmed else "results.ack.closed")


def refusal(code: str, message: str) -> str:
    """A refused call, as the model reads it: the machine-readable code, then the
    message written for the model. Never softened: a turn violation is backpressure
    the model has to be able to reason about (design §5.4)."""
    return texts.render("results.refused", code=code, message=message)
