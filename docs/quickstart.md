# Quickstart

Install the hub, register two Claude Code agents, run them as a team and supervise
their first exchange. Every step is done on the WebUI; the command-line equivalent is
given where one exists.

## 1. Install and start the hub

Requirements: macOS, [uv](https://docs.astral.sh/uv/), Docker with compose, and
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude` on your PATH).

There are two ways to install. As an app, from an empty directory:

```sh
curl -fsSL https://raw.githubusercontent.com/vkuusk/agent-courtyard/main/install.sh | sh
```

The hub then starts at login, and **Courtyard Admin** in the menu bar starts, stops and
restarts it (user guide, Installation). Read the summary the installer prints;
a warning there means an earlier install's database was found and is reused.

From a clone, in the foreground:

```sh
git clone https://github.com/vkuusk/agent-courtyard.git
cd agent-courtyard
cp .env.default .env   # local settings; the compose postgres listens on 26432 (COURTYARD_PG_PORT)
uv sync
make run               # postgres + the hub on http://127.0.0.1:2626; leave this terminal open
```

`make run-chrome` instead starts the hub in the background (log: `sandbox/courtyard.log`)
and opens the WebUI in its own Chrome window; `make run-stop` ends that hub.

Open http://127.0.0.1:2626. The Courtyard page is empty and the dot at the top right
says **live**. The hub listens on 127.0.0.1 only. From here on the walkthrough is the
same for both installs.

## 2. Make a project directory for each agent

Each agent works in its own directory, as two separate Claude Code sessions would. For
the example:

```sh
mkdir -p ~/courtyard-quickstart/main-admin ~/courtyard-quickstart/infra-claude
printf 'resource "null_resource" "placeholder" {}\n' > ~/courtyard-quickstart/infra-claude/main.tf
```

Real project directories work the same; courtyard only adds the config files written in
the next step.

## 3. Choose the team's directory, then register the agents

A team is defined as files in one directory, the team charter, and the hub requires it
before the first agent. The empty Courtyard page asks for it: press **browse**, pick a
directory outside the agents' project directories (for the example,
`~/courtyard-quickstart/team`) and name the team when asked. The hub writes
`team-definition.yml` there, and every agent registered from now on is written there
too, as its card files.

A directory that already holds a charter is loaded instead: its agents are registered
at once, and each agent whose project directory is listed in the charter's
`workdirs.local.yml` gets its files (described below) written in the same step. An
agent without an entry gets them when you choose its directory under **Admin → Teams**.
Such a team is ready; go on to section 4.

For a new team, register each agent on the **Agents** page, **+ Add an agent**:

- the name (permanent; a removed agent's name can be registered again)
- the type, `claude-code`
- what it can do, what it owns, and optionally what it is not for; every other agent
  sees all three (choosing them is team design, the README's step 1)
- the project directory
- optionally the model it should run (`sonnet`), and the colour of its card

| name | owns | project dir |
|---|---|---|
| `main-admin` | the admin workbench | `~/courtyard-quickstart/main-admin` |
| `infra-claude` | infrastructure and terraform | `~/courtyard-quickstart/infra-claude` |

**add agent** registers the agent and writes three files into its project directory:
`.mcp.json` (the connection; it holds the agent's token, permissions 600, keep it out of
git), a `.claude/settings.local.json` profile (pre-approves the courtyard tools, tells
each session that it is a member of the team, sets the model) and
`start-with-courtyard.sh` for starting the agent by hand. The hub keeps the token.

Each row then has three actions. **edit** changes everything but the name and type;
**save** writes the files again, and **rotate token** there replaces the token and
rewrites them (the agent then needs a restart). **launch config** shows the files.
**remove ▾** offers **disconnect** (the files leave the directory, the agent stays on the
team) and **unregister** (the files leave, the agent leaves the hub and the charter).

The same from a terminal (the `--team` flags choose the charter directory while the hub
has no team yet):

```sh
uv run courtyard-invite --team-dir ~/courtyard-quickstart/team --team-name quickstart \
    --register --name main-admin \
    --sme-domain "the admin workbench" --workdir ~/courtyard-quickstart/main-admin
uv run courtyard-invite --register --name infra-claude \
    --sme-domain "infrastructure and terraform" --workdir ~/courtyard-quickstart/infra-claude
```

## 4. Start the team: press Start shift

On the **Courtyard** page press **▶ Start shift**. The hub first checks who is already
running (**Waiting for the team**, a few seconds: a stored status is not trusted, a fresh
heartbeat is), then opens one terminal window for each agent that is not, in the
agent's directory, running the launch command. The pill counts the team up:
`Starting · 1/2`, then `● 2/2 on shift`. The terminal application (Terminal, iTerm2 or
Ghostty) is chosen under **Admin → Terminal application**.

At an agent's first launch Claude Code asks in its terminal whether to allow the
channel: answer yes, it cannot be pre-answered. Whether to use the project's
`.mcp.json` server is answered by the launch command itself. Within a few seconds the
agent's rectangle shows a green dot, **connected**.

Each session then gets a **delivery check**: the hub sends it a message that only asks
for a confirming tool call. The card shows "checking delivery…", then a green check
mark, which means the session received the message. The same button runs the check
again. A card that warns **started without the channel** belongs to a session started
as a plain `claude`: it can send to the hub but cannot hear it. Close that session and
run `./start-with-courtyard.sh` in the agent's directory, or End shift and Start shift.

**■ End shift** closes the terminals the shift opened (terminals you opened yourself
are left alone) and expires whatever is still unanswered or held at the gate. Expired
messages stay in the history; the next shift starts with every line clear.

To start one agent by hand:

```sh
cd ~/courtyard-quickstart/main-admin
./start-with-courtyard.sh    # claude with the channel flag, and --model if you declared one
```

## 5. The first exchange

Press **Brake** beside the shift pill first. A new line between two agents starts on
**auto-pass**; the brake puts every agent line behind the gate, so this first exchange
can be watched message by message.

Click the `main-admin` rectangle on the **Courtyard** page, type in the box at the
bottom and press Enter:

> Ask infra-claude to list the files in its working directory, and tell me what it reports.

1. The message arrives in main-admin's terminal as a turn from the operator. Your own
   lines are never gated.
2. main-admin looks up the team (its `courtyard_peers` tool) and sends to infra-claude.
   The message stops at the gate: a line `main-admin ↔ infra-claude` appears under
   **Lines**, *held at the gate*. Click it. Under the held message is a comment field
   and **approve** / **return to sender** / **drop**. The comment goes with the verdict:
   appended to the message on approve, back to the sender as the reason on return,
   nowhere on drop. Approve.
3. infra-claude lists its files and replies. The reply waits at the same gate; approve
   it too.
4. main-admin answers you. Its rectangle shows **1 new**; click it to read the answer.
   Press **Brake** again and the lines return to auto-pass.

The same request typed into main-admin's own terminal gives the same exchange on the
WebUI, and the answer comes back in that terminal. On each line one message can be
unanswered at a time: a second send before the answer is refused, and the sender is told
whose turn it is.

## 6. Controls you will use

- **supervised** / **auto-pass**, in the header of a selected line. **supervised** means
  every message on the line waits at the gate for your verdict; **auto-pass** means
  messages flow and are logged. **Admin → Defaults** sets the mode a new line starts in.
- **Brake** switches every agent line to supervised at once; pressing it again returns
  them to the default. A turn already running finishes first.
- **return to sender** hands a held message back with your comment; **drop** ends it and
  tells the sender not to resend. Both stay in the history.
- A line between two agents has no input box. To write to an agent, click its rectangle.
- **Admin → Settings → Discovery** `manual` means agents see and can message only whom
  you have linked: **+** in the Lines panel opens a line, **unlink** in its header
  archives and closes it. `auto` (the default) lets any pair start talking.
- **release**, in the header of a line stuck waiting for an agent that died mid-reply,
  ends the open thread and tells both agents.
- **archive** moves a line's history to the **Archive** page (readable there, exportable
  as JSON) and empties the line. Removing an agent archives its lines.
- **Memory** lists the case files of closed threads and the notes agents leave for the
  team, with the verdicts that wait for you. Agents search it with `courtyard_recall`.
- Closing an agent's terminal is fine: its messages wait on the line and are delivered
  when it starts again. Messages that arrive during a turn are delivered when the turn
  ends.

## 7. When things get out of step

- **Terminals closed, or a reboot, without End shift.** After a `Checking the team`
  countdown the WebUI asks **The last shift was never ended**. **End shift** closes it
  (unfinished messages expire); **Start new shift** closes it and starts fresh.
  **Not now** leaves an amber *shift left open* tag in the Team header; click it to get
  the question back.
- **Part of the team is down mid-shift** (`1/2 on shift`). Press **▶ Resume shift**: it
  opens terminals for the missing agents only, and what they still owe is delivered
  again.
- **The hub was restarted mid-shift.** Nothing to do. The terminals own the sessions;
  each agent turns green at its next heartbeat (within 5 s).
- **Claude Code auto-updated under running sessions** ("Restart to update" in the
  terminals, or messages stop arriving). End shift, Start shift. If messages still do
  not arrive, `make test-comms` runs the operator → agent → operator round trip against
  a live session and prints where it broke.
- **The database was deleted, or the team was rebuilt from its charter.** Registrations
  and tokens are new. Choosing the charter directory again registers every agent and
  rewrites the files in each directory `workdirs.local.yml` lists. An agent whose
  directory is not listed keeps a dead token: its card reads **token rejected, rewrite
  the agent's files**. Exit that session, choose its directory under **Admin → Teams**
  (or **edit**, **save**), and start it again.

## 8. Stop and clean up

### Stop everything

1. **■ End shift** on the Courtyard page: the agents' terminals close.
2. Stop the hub: Ctrl+C in the `make run` terminal; `make run-stop` after
   `make run-chrome`; `make hub-stop` for the installed app (it stays down, also across
   logins, until `make hub-start`).
3. `make db-down` stops postgres. The data survives.

### Start from scratch

Stop everything as above, then:

```sh
make db-nuke     # stop postgres AND delete the courtyard database
make run         # or make hub-start for the installed app: an empty hub
```

Registrations, tokens, lines and history are gone. The charter directory and the
agents' project directories are not touched. Choose the charter directory again on the
empty Courtyard page: the agents are registered anew and their files rewritten
(section 7, last case).

### Uninstall everything

```sh
make uninstall            # the courtyard files out of every agent's directory, then the LaunchAgents, the Admin app, the containers, .venv
make uninstall PURGE=1    # also the database volume
```

The first step goes through the hub, so the hub must be running (under launchd it is).
When it is not, uninstall says so and names the command that cleans the directories after
`make hub-start`. The installation directory with its `.env`, the charter directory and,
without `PURGE=1`, the registrations stay, so a later install plus the charter directory
connects the team again. A clone run with `make run` has nothing installed beyond the
containers: `make db-nuke`, then delete the clone.

For one agent instead of all: **remove ▾**, **disconnect** on the Agents page takes
courtyard out of its directory and keeps the agent on the team; **unregister** cleans the
directory, then removes the agent from the hub and from the charter.
