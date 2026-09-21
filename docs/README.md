# Documentation

The root [README](../README.md) gets you running. This directory holds the rest.

## Manuals

| Doc | Short description |
|---|---|
| [quickstart.md](quickstart.md) | A first run with two agents, every screen described |
| [user-guide.md](user-guide.md) | The operator's reference: every feature, where it is and what it does |
| [development.md](development.md) | Development setup, conventions, releasing |
| [testing.md](testing.md) | How testing works, and the manual verification procedure of each feature |

## Design

| Doc | Short description |
|---|---|
| [architecture-v1.md](design/architecture-v1.md) | The full design: concepts, delivery, liveness, the shift, and a log of every decision with its reasons |
| [communication-protocols.md](design/communication-protocols.md) | How messages move: who sends to whom, what the hub adds, what each model is shown |
| [threads.md](design/threads.md) | A thread: one bounded exchange about one ask, its lifecycle and enforcement |
| [team-charter.md](design/team-charter.md) | The team defined as files: charter directory, agent cards, links |
| [hub-memory.md](design/hub-memory.md) | Team memory: case files, notes, recall, similarity search |
| [adapter-implementation.md](design/adapter-implementation.md) | Implementation decisions of the Claude Code adapter |
| [use-cases-explained.md](design/use-cases-explained.md) | "How does this actually work?" answers, one use case at a time |

`diagrams/` holds the pictures the documents use, with their sources. A worked example of a
team charter is in [`examples/team-charters/`](../examples/team-charters/).
