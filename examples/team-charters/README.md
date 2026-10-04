# Example team charters

A team charter is one directory of files that defines a team: who the agents
are, what each can and cannot be asked, and who may talk to whom. The format
is described in [docs/design/team-charter.md](../../docs/design/team-charter.md);
each subdirectory here is a complete, loadable example.

- `team1/`: the smallest team. `agent1` writes short texts, `agent2` reviews
  them; one line between them, on the hub's default gate mode. Its
  `workdirs.local.yml` points at the two directories under
  `sandbox/example-workdirs/team1` in this checkout, so the agents have a
  project directory the moment the charter is loaded. Each directory's README
  gives its agent a first task.

To try it: start the hub, open Admin, Teams, add this example's directory and
select it as the current team. The hub registers the agents, creates the line
and writes the agents' courtyard files into their directories (git ignores
everything there but the READMEs). **Start shift** opens one terminal per
agent; the task in each README is a first conversation to watch on the
Courtyard page.

To make it your own team, copy the charter directory anywhere, point its
`workdirs.local.yml` at your agents' real project directories (absolute paths,
or paths relative to the charter directory) and edit the cards. That file is
per machine and must never be committed with your paths. The files are the
source of truth: edit them (or `git pull` a newer version) and press "reload
from disk" in the Teams view. The hub never watches the filesystem.
