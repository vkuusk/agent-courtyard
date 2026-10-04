"""Who is on the current team (team-charter.md, "The current team is the courtyard").
Derived from the registered charters at call time; nothing is stored."""

from __future__ import annotations

from dataclasses import dataclass, field

from courtyard.common.models import Agent


@dataclass(frozen=True)
class Membership:
    team: str | None = None  # the current team's name; None before any team is chosen
    # the current charter's agent names; None = no loaded charter, nobody is hidden
    names: frozenset[str] | None = None
    # agent name -> team name over every registered charter (the current team wins)
    teams: dict[str, str] = field(default_factory=dict)

    def includes(self, agent: Agent) -> bool:
        """On the current team: the operator always, everyone while no charter is loaded."""
        return agent.type == "human" or self.names is None or agent.name in self.names

    def team_of(self, agent: Agent) -> str | None:
        return None if agent.type == "human" else self.teams.get(agent.name)

    def decorate(self, agent: Agent) -> Agent:
        """The agent as the API shows it: its team and whether it is on the current one."""
        return agent.model_copy(
            update={"team": self.team_of(agent), "on_team": self.includes(agent)}
        )


EVERYONE = Membership()
