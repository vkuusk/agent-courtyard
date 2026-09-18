"""Peer discovery, hub-side (design §7.1, D14): who an agent can talk to, ranked and rendered.

The peers list is read by a model deciding whom to ask, so it is ordered by reachability
and trimmed — a long tail of long-dead registrations is noise the model pays context for.
Ranking, trimming and the model-facing wording live here, once; adapters forward the text.

Under manual discovery (design §5.8, D22) the callers pass `linked` — the ids sharing a
line with the caller — and the roster narrows to those plus the operator, who is always
reachable in either direction.
"""

from __future__ import annotations

from uuid import UUID

from courtyard import texts
from courtyard.common.models import Agent, PeerInfo, PeersView

PEER_LIMIT = 25  # a real courtyard holds a handful of agents; this only trims dev clutter
LIVENESS_ORDER = {"connected": 0, "stale": 1, "invited": 2, "gone": 3}


def roster(agents: list[Agent], me: Agent, linked: set[UUID] | None = None) -> list[PeerInfo]:
    """Every other live registration, reachable first, then by name. With `linked`
    (manual discovery), only the operator and the agents the caller shares a line with."""
    others = [a for a in agents if a.removed_at is None and a.id != me.id]
    if linked is not None:
        others = [a for a in others if a.type == "human" or a.id in linked]
    others.sort(key=lambda a: (LIVENESS_ORDER.get(a.status, 9), a.name))
    return [
        PeerInfo(
            name=a.name,
            type=a.type,
            description=a.description,
            sme_domain=a.sme_domain,
            anti_scope=a.anti_scope,
            status=a.status,
        )
        for a in others
    ]


def peers_view(agents: list[Agent], me: Agent, linked: set[UUID] | None = None) -> PeersView:
    everyone = roster(agents, me, linked)
    shown = everyone[:PEER_LIMIT]
    hidden = len(everyone) - len(shown)
    return PeersView(
        peers=shown, total=len(everyone), rendered=render(shown, hidden, managed=linked is not None)
    )


def render(peers: list[PeerInfo], hidden: int, managed: bool = False) -> str:
    if not peers:
        return texts.render("listings.peers.alone_managed" if managed else "listings.peers.alone")
    lines = []
    for p in peers:
        line = texts.render("listings.peers.entry", name=p.name, type=p.type, status=p.status)
        if p.sme_domain:
            line += texts.render("listings.peers.owns", domain=p.sme_domain)
        if p.description:
            line += texts.render("listings.peers.description", description=p.description)
        if p.anti_scope:
            # D33: whom NOT to ask, at the one moment it helps — choosing whom to ask.
            # Anti-scope prose comes from a wrapped .md file; collapse it to its one line.
            line += texts.render(
                "listings.peers.not_for", anti_scope=" ".join(p.anti_scope.split())
            )
        lines.append(line)
    if hidden:
        lines.append(texts.render("listings.peers.hidden", count=hidden))
    if managed:
        lines.append(texts.render("listings.peers.managed"))
    return texts.render("listings.peers.header") + "\n" + "\n".join(lines)
