# Agent Courtyard

A local communication hub for a team of long-lived AI agents. It carries the messages
between your agents, lets you watch and control them, and keeps them as the team's memory.

If an AI agent is setting this up for you, point it at [AGENTS.md](AGENTS.md).

This project is for you if you work with several specialized agents in separate terminal
windows, and sometimes need them to help each other on a task you gave one of them.

Before Courtyard I was the "human relay": I copied messages between two agents' terminals
while reviewing the design decisions they were trying to make between themselves. With
Courtyard the messages go between the agents without me, and I can still inspect them and
intervene. Agent discovery, an audit trail and a team memory come with it.

`<add-diagram-with-communication-flow-before-and-after>`

`<add-video-with-one-request-crossing-two-agents>`

## Getting started

### 1. Design a team of two

Courtyard has nothing to show until your agents have a reason to talk. Before installing,
decide who does what. Start with two agents and write down, for each one, "What it can do"
and "What it owns". Registration asks for exactly these two fields.

| Agent | What it can do | What it owns |
|---|---|---|
| `tf-developer` | writes and reviews Terraform modules | the Terraform modules repository |
| `infra-agent` | deploys AWS resources, reads the state of the account | the AWS account and its deployments |

- **What it can do** is shown to every other agent. It is how they decide whom to ask.
- **What it owns** marks the agent's word as authoritative in that area.

Draw the boundary so that crossing it is a question to the other agent: the agent that
deploys does not edit the modules, it asks. Give each agent standing approval for the
read-only tools its area needs, so a peer's question does not stop at a permission prompt
in a terminal nobody is watching.

More on team design:
[quickstart, section 3](docs/quickstart.md#3-choose-the-teams-directory-then-register-the-agents).

### 2. Install

Prerequisites:

- macOS. Currently macOS only: starting a shift opens Terminal, iTerm2 or Ghostty windows.
- [uv](https://docs.astral.sh/uv/)
- Docker with compose
- One supported coding agent: [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  or the [pi coding agent](https://github.com/earendil-works/pi)

From an empty directory:

```sh
curl -fsSL https://raw.githubusercontent.com/vkuusk/agent-courtyard/main/install.sh | sh
```

The script names any missing prerequisite with the command that installs it, downloads the
latest release and runs `make install`. It ends with a summary of its steps; read any
warning there.

The hub is installed as a macOS app: it starts at login, and **Courtyard Admin** in the
menu bar starts, stops and restarts it.

`<add-screenshot-with-courtyard-admin-menu>`

The install starts the hub and opens the WebUI: in Chrome as its own window, otherwise in
your default browser. The address is http://127.0.0.1:2626.

`<add-screenshot-with-empty-courtyard-page>`

### 3. Register your agents

The empty Courtyard page asks for the team's directory. The team's definition is stored
there as files. Choose a directory outside the agents' project directories; an empty one
is initialized after you name the team.

`<add-screenshot-with-team-directory-dialog>`

Then, for each agent:

1. **Agents** page → **+ Add an agent**: a name (permanent, so choose it once), the type
   (`claude-code` or `pi`), the project directory the agent works in, and the two
   descriptions from step 1.

   `<add-screenshot-with-add-agent-form>`

2. **add agent** registers it and writes its files into that directory. For a Claude
   Code agent these are three: `.mcp.json` (the connection; it holds the agent's token,
   keep it out of git), a `.claude/settings.local.json` profile that pre-approves the
   courtyard tools, and `start-with-courtyard.sh` for starting the agent by hand. A pi
   agent gets its extension and a skill under `.pi/` instead, and the same start script.
   **launch config** on the agent's row shows them.

   `<add-screenshot-with-launch-config>`

### 4. Run the team in shifts

The team's working day is a **shift**. **▶ Start shift** on the Courtyard page starts
everyone. An agent that is already running is only checked for its heartbeat. For each of
the others the hub opens a terminal in the agent's directory and starts the agent there.

At a Claude Code agent's first launch, allow the channel when it asks in its terminal.

As each session comes up, the hub sends it a test message. A green check mark on the
agent's card means the session received it. The same button runs the check again.

`<add-screenshot-with-team-on-shift>`

**■ End shift** ends the day. It closes the terminals the shift opened, and leaves alone
the ones you opened yourself. A conversation still waiting on a reply, or a message held
at the gate, is marked expired, and the next shift starts with every line clear.

To start one agent by hand, run the script that registration wrote:

```sh
cd <the agent's directory>
./start-with-courtyard.sh
```

A plain `claude` session in the same directory can send to the hub but cannot hear it.
The WebUI warns you when that happens.

### 5. Work with the team

- In any agent's terminal, work as usual. The agent knows its team: ask it to ask
  another agent for something, and the answer comes back to that terminal.
- On the WebUI, click an agent's rectangle on the Courtyard page and write to it in the
  box at the bottom.

Every message between the agents appears on the WebUI as it happens.

`<add-screenshot-with-conversation-between-two-agents>`

The same flow in full detail: [docs/quickstart.md](docs/quickstart.md). The reference,
part by part: [docs/user-guide.md](docs/user-guide.md).

### Uninstall

```sh
cd <installation-directory>
make uninstall            # the app, the containers and .venv
make uninstall PURGE=1    # also the database volume
```

The directory itself and its `.env` stay. So do the files in the agents' directories;
the [user guide](docs/user-guide.md) says how to remove them.

## More documentation

All of it is listed in [docs/README.md](docs/README.md).
