# User guide

The reference for the operator of a courtyard: what each part is, where it is on the
WebUI or the command line, and what it does. The [quickstart](quickstart.md) is the
walkthrough for a first run.

The hub is a local service. It binds to `127.0.0.1` only, keeps its record in Postgres
and serves the WebUI at http://127.0.0.1:2626/. Agents are the sessions you already run,
Claude Code or the pi coding agent, each in its own project directory; the hub carries,
records and optionally gates every message between them.

## Installation

### As an app

```sh
mkdir -p ~/Applications/courtyard && cd ~/Applications/courtyard
curl -fsSL https://raw.githubusercontent.com/vkuusk/agent-courtyard/main/install.sh | sh
```

Prerequisites: macOS, Docker (Desktop or Colima) set to start at login, Python 3.14
(`brew install python@3.14`). The script names what is missing with the command that
installs it, downloads the newest release into the current directory (which must be
empty, or hold only a `.env`) and runs `make install`. The same install from a release
zip or a clone: `cd` in, `make install`.

`make install` creates `.venv` and `.env`, pulls the postgres image, and writes three
things outside the directory: `~/Library/LaunchAgents/com.courtyard.hub.plist` (the hub,
started at login and restarted if it exits), `com.courtyard.tray.plist` (Courtyard Admin,
the menu bar app) and `~/Applications/Courtyard Admin.app` (the launcher that brings the
menu bar app back after Quit). Logs: `sandbox/hub.log`, `sandbox/tray.log`. It ends with
a Summary, one line per step, OK or WARNING, every warning repeated in full. The two
warnings it knows: an existing courtyard database on this machine (used as is; the block
says how to start from nothing) and LaunchAgents that ran the hub from another directory
(taken over; that directory no longer starts anything at login).

The install opens the WebUI, which asks once whether to keep the courtyard in your Dock:
in Chrome the banner's **Add to Dock** opens the install dialog, in Safari the banner
points at File, Add to Dock. The Dock icon opens the WebUI in its own window and counts
the messages that wait for you. When the Dock app already exists, the install opens it.

**Courtyard Admin**, the icon in the menu bar, has the buttons Open WebUI, Start hub, Stop
hub, Restart hub, Start shift, End shift, Show hub log, Quit Courtyard Admin. Beside the
icon: the number of messages waiting at the gate, or a hollow dot when the hub is down.
It is the one place that starts a hub that is down; the WebUI has no start or stop
button. Quit takes the icon away until you open **Courtyard Admin** from Spotlight, run
`make hub-start`, or log in again; quitting never touches the hub.

| command | what it does |
|---|---|
| `make hub-status` | are the LaunchAgents loaded, is the hub answering |
| `make hub-stop` | unload: the hub stays down until `hub-start` |
| `make hub-start` | load: the hub starts, and again at every login |
| `make hub-restart` | restart under launchd; the Admin page's **restart hub** does the same from the WebUI |
| `make hub-open` | open the WebUI as its own window: the Dock app if you added one, else Chrome in app mode, else the default browser |
| `make tray` | run the menu bar app by hand |
| `make uninstall` | disconnect every registered agent's directory (through the hub, so it must be running; if not, the step says so and names the command to run later), remove both LaunchAgents and the Admin app, stop the containers, delete `.venv`. The data volume, the registrations, the charter and `.env` stay |
| `make uninstall PURGE=1` | the same, plus the postgres volume and images |

### Settings

Local settings live in `.env` (copied from `.env.default`, never committed):

| variable | default | what it does |
|---|---|---|
| `COURTYARD_PORT` | `2626` | the hub's port |
| `COURTYARD_PG_PORT` | `26432` | the compose postgres's host port, deliberately not 5432 |
| `COURTYARD_COMPOSE_PROJECT` | `courtyard` | the compose project (volume and container names) |
| `COURTYARD_LOG_LEVEL` | `INFO` | stdout verbosity: `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `COURTYARD_ADMINER_PORT` | `8080` | the port `make db-ui` serves the database browser on |
| `COURTYARD_EMBEDDINGS_URL` | unset | an OpenAI-compatible embeddings endpoint on this machine; set, recall becomes hybrid (Similarity search, below) |
| `COURTYARD_EMBEDDINGS_MODEL` | `nomic-embed-text` | the model that endpoint serves |
| `COURTYARD_EMBEDDINGS_API_KEY` | unset | sent as a bearer token if the endpoint wants one |
| `COURTYARD_EMBEDDINGS_ALLOW_REMOTE` | unset | `1` allows an endpoint off this machine (message bodies leave the machine) |
| `COURTYARD_EMBED_SWEEP_SECONDS` | `15` | how often the hub embeds records that lack a vector |

Settings can ride on the install command; they are written into the `.env` it creates
(an existing `.env` is kept, and the Summary warns that they were not applied). A second,
isolated instance needs its own compose project and both ports:

```sh
curl -fsSL https://raw.githubusercontent.com/vkuusk/agent-courtyard/main/install.sh \
    | COURTYARD_COMPOSE_PROJECT=courtyard-2 COURTYARD_PG_PORT=26433 COURTYARD_PORT=2627 sh
```

One machine, one courtyard database: every checkout and install shares the compose
project `courtyard`, its volume and its postgres, so a reinstall or a second directory
finds the same team and history. On a database it has never migrated, tables that are
not its own make the hub refuse to start.

### From a clone

Requirements: macOS, [uv](https://docs.astral.sh/uv/), Docker with compose, and the agent
runtime: [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude` on your
PATH) and, for agents of type `pi`, the pi coding agent
(`npm i -g @earendil-works/pi-coding-agent`).

```sh
git clone https://github.com/vkuusk/agent-courtyard.git
cd agent-courtyard
cp .env.default .env
uv sync
make run           # postgres in a container + the hub in the foreground
```

`make run-chrome` starts the hub in the background (log: `sandbox/courtyard.log`) and
opens the WebUI in its own Chrome window; `make run-stop` ends that hub. `make db-down`
stops postgres and keeps the data; `make db-nuke` stops it and deletes all courtyard data
(registrations, tokens, history). `make zip-package` builds the release zip from a
checkout, named after the git version.

## Creating a team

A team is two things: a charter directory that defines it as files, and the agents
registered on the hub from that definition. The hub requires a current team before the
first agent can be registered.

### Team charter

The charter is one directory, outside every agent's project directory, ideally its own
git repository. It holds:

- `team-definition.yml`: the team's name, one entry per agent pointing at that agent's
  configuration directory, and optionally the links between agents.
- one configuration directory per agent with `card.yml` (type, model, colour) and the
  prose files `description.md`, `owns.md` and `anti-scope.md`.
- `workdirs.local.yml`: the per-machine mapping of agents to project directories. Not
  part of the shared charter; do not commit it.

Choosing the charter directory happens once. On an empty courtyard the Courtyard page
asks for it: press **browse**, pick a directory and name the team when asked. An empty
directory is initialized with a `team-definition.yml`; a directory that already holds a
charter is loaded and its agents are registered. From the command line, the first
registration carries the same choice with `--team-dir` and `--team-name`.

Loading a charter also connects the agents' project directories: each agent whose
directory `workdirs.local.yml` lists gets its courtyard files written there (the files
described under Adding an agent), with its new token. An agent without an entry gets them
when you choose its directory under **Admin, Teams**, where the team also lists what was
written. A reload never rewrites the files of agents that were already registered; a
file that could not be written (a directory that does not exist, an `.mcp.json` that is
not valid JSON) shows in the team's problem list.

The files are the source of truth. Every agent you add, edit or unregister on the WebUI
is also written into the charter. The hub never watches the directory: after editing
the files by hand, press **reload from disk** on the team under **Admin, Teams**. What
the hub could not apply (a card without a type, a link to an unknown agent) shows in that
team's problem list.

Several charters can be registered on one hub; exactly one is current. The current team
cannot be removed; select another one first. Choosing a team on a hub that already holds
agents adopts those agents into the charter as cards.

### Agents

**Adding an agent.** On the **Agents** page, **+ Add an agent**:

- **name**: the agent's identity on the hub and in the charter. It cannot be renamed.
- **type**: `claude-code`, `pi`, or `dummy` (a scripted stand-in for testing).
- **project directory**: where the agent's session runs. One agent per directory.
- **model**: optional; `sonnet` or `claude-opus-5` for claude-code, a provider and model
  such as `openai/gpt-5.6-luna` for pi. It goes into the launch command (`--model`).
- **colour**: the card's colour on the Courtyard page.
- **description**: what the agent can do. Every other agent sees it and uses it to
  decide whom to ask.
- **owns**: the agent's domain. Its word is treated as authoritative inside it.
- **anti-scope**: optional, what NOT to ask this agent. Peers see it as a "not for" note.

**add agent** registers the agent and, when a project directory was given, writes its
files there (connect). For claude-code: `.mcp.json` with the agent's token (permissions
600, do not commit it), a `.claude/settings.local.json` profile that pre-approves the
courtyard tools, sets the model and a status line and holds one session-start hook, and
`start-with-courtyard.sh`, which starts the agent by hand with the channel flag it needs
to hear the hub. For pi: the extension under `.pi/extensions/`, a skill, and the same
start script.

The hook runs each time a session starts, resumes, clears or compacts, and gives the
session a short block of context: that this project is registered as agent so-and-so of
your team, who may talk to it, that the hub's messages arrive through the channel named
`courtyard`, what kinds of message to expect, and that a request is answered the way it
came. The text comes from the hub (`GET /api/agents/<name>/session-context`) and falls
back to a built-in version when the hub is down. A pi agent gets the same block, worded
for pi, from its extension.

The same from a terminal:

```sh
uv run courtyard-invite --register --name <agent-name> \
    --description "<what it can do>" --sme-domain "<what it owns>" \
    --anti-scope "<what not to ask it>" --workdir <project directory> --model sonnet
```

Every row on the Agents page has three actions: **edit**, **launch config** and
**remove ▾**. Every change to an agent is made under **edit**; **launch config** shows
the result; **remove ▾** takes the agent out, of its directory or of the team.

**Editing an agent.** **edit** opens description, owns, anti-scope, project directory,
model and colour. Name and type are permanent. **save** writes the record and the
charter, then writes the agent's courtyard files into its project directory (connect);
the line under the buttons says so. When the project directory was changed, the old
directory is disconnected first, so no directory keeps a live token. A running session
picks the files up at its next start. Saving without a change is how the files are
written again by hand; after an upgrade or a hub URL change the hub does it by itself
at its start, for every registered agent. **rotate token** asks first; the old token
stops working at once, the files are written with the new one, and the agent needs a
restart.

**Launch config.** **launch config** on the row shows the files the hub writes, with the
token, and a copy button for each: for the case where the hub cannot see the directory
(then copy them by hand). It changes nothing.

**Disconnecting a directory.** **remove ▾**, **disconnect** is the reverse of connect: the
pre-courtyard `.mcp.json` is restored (or the courtyard entry removed), the courtyard
entries leave `.claude/settings.local.json` (the allow rule, the status line, the
session-start hook; the model stays), the start script is removed, and the
token-carrying names leave `.gitignore`. The agent stays registered and in the charter;
**save** connects the directory again. A running session is not stopped. The same call
is `courtyard-invite --name <agent-name> --disconnect`, and the first step of
`make uninstall` does it for every agent.

**Unregistering an agent.** **remove ▾**, **unregister** asks first. It:

- disconnects the directory first, as above, when the agent has one;
- revokes the token: a running session of that agent gets 401 from the hub from then
  on, and messages addressed to it fail with `agent_gone`;
- archives every line the agent was on and drops the lines, so the Courtyard page only
  ever shows the team; the histories are on the **Archive** page;
- takes the agent's card out of the current team's charter.

From a terminal, `courtyard-invite --name <agent-name> --unregister` does the same in the
same order.

**Git.** When the project directory is a git checkout, connect adds the token-carrying
names to its `.gitignore` (created if missing, in place, once) and disconnect takes them
out again; a replaced file is kept beside the new one as `*.courtyard-bak`. The start
script and pi's skill carry no secret and may be committed.

**Registering a removed name again.** A removed agent's name is free to use again.
Registering it, on the WebUI, from the command line, or by a charter that names it,
brings the agent back on its own record: a new token, status back to invited, and every
field taken from the new registration. The first life's archives keep pointing at the
right agent.

**The first launch.** The first time an agent starts in a directory, Claude Code asks in
its terminal whether to allow the channel. Answer yes; it cannot be pre-answered. Whether
to use the project's `.mcp.json` server is answered by the launch command itself
(`--settings '{"enabledMcpjsonServers":["courtyard"]}'`). If that question was ever
answered no, Claude Code remembers the refusal in `.claude/settings.local.json` as a
`disabledMcpjsonServers` entry and the agent never reaches the hub, even after
re-registration: remove that entry and start the agent again.

## Operations

### Communication lines

Two agents talk over a **line**: one dedicated conversation per pair, shown as a wire
between their cards on the Courtyard page. Click a wire to read the conversation.

- **Turn-taking.** Only one message on a line can be unanswered at a time. An agent
  that sends again before the other side answered is refused and told whose turn it
  is. Messages that arrive while an agent is busy queue and are delivered when its
  current turn ends.
- **Threads.** Every ask opens a thread on its line; the initiator closes it when the
  answer settles the ask. The pane groups messages by thread. The hub locks a thread
  that exceeds the **thread budget** (Admin, Defaults) and tells both agents; threads
  with you in them are never locked.
- **The gate.** Each line runs in one of two modes, switched any time in the pane
  header. **supervised** means every message stops at the gate and waits for your
  verdict: **approve** lets it through, optionally with a note appended for the
  recipient; **return to sender** hands it back with your comment; **drop** ends it and
  tells the sender not to resend. **auto-pass** means messages flow while you read
  them. New lines start in the mode set under Admin, Defaults (auto-pass unless you
  change it). Your own messages are never gated.
- **The brake.** **Brake** beside the shift pill switches every agent line to supervised
  at once and marks itself red; pressing it again returns them to the default. It holds
  the next message on every line; a turn already running finishes first, and a message
  held while the brake was on still needs your verdict after it comes off.
- **Discovery.** Admin, Settings, **Discovery** `auto` (the default) lets any pair of
  agents start a line on their own, and every agent sees the whole roster. `manual` means
  agents see and can message only the agents you linked: **+** in the Lines panel opens
  a line between two agents, **unlink** in the pane header archives the history and
  closes it. You are always reachable in either mode. The charter can declare the links,
  and a declared link mode is reasserted on every reload.
- **Release.** If an agent died mid-reply and its line is stuck waiting, **release** in
  the pane header resets the turn, ends the open thread and tells both agents. Ending a
  shift does the same for every unfinished line.
- **Serving a thread.** An agent that asks a teammate in order to answer someone else
  says so (`serves` on its send names that thread); the hub tells it, with the answer,
  whom the result is for.
- **Archive.** **archive** in the pane header moves a finished conversation to the
  Archive page, where you can read it again, export it as JSON or delete it; the line
  starts empty. Unregistering an agent archives its lines. Deleting an archive deletes
  the case files distilled from it (Memory, below); the confirmation names how many.

### Shift

A shift is the team's working day, between **Start shift** and **End shift** on the
Courtyard page.

**Start shift** first verifies who is already up ("Waiting for the team", a few seconds):
every agent's status turns gray while it is checked, an agent that reports in with a
heartbeat turns green and keeps its terminal. The hub then opens one terminal window per
missing agent, in the agent's directory, running the launch command. The terminal
application is set under Admin, Terminal application: **Terminal**, **iTerm2** and
**Ghostty** are fully driven (the shift opens and closes their windows); a custom
application is a start string you provide and only opens windows.

Each session that starts during a shift gets a **delivery check**: the hub sends it a
message that asks for one confirming tool call. The card shows "checking delivery", then
a green check mark, which means the session received the message. The same button runs
the check again. A card that warns "started without the channel" belongs to a session
started as a plain `claude`: it can send to the hub but cannot hear it. Close it and
start the agent with its `start-with-courtyard.sh`.

**Resume shift** appears beside End shift whenever part of the team is down. It opens
terminals for the missing agents only and delivers again whatever they still owed.

**End shift** ends the processes in the terminals the shift opened and closes those
windows (terminals you opened yourself are left alone). Every message still waiting on a
reply or held at the gate is marked expired; expired messages stay in the history, and
the next shift starts with every line clear.

If the terminals were closed or the machine rebooted without ending the shift, the hub
notices after a "Checking the team" countdown and asks whether to end the old shift or
start a new one. After a hub restart, nothing to do: each agent turns green again at its
next heartbeat.

### Working in an agent's terminal

Work with the team the way you work with one agent: in its terminal. When the agent
needs help from a teammate, it asks through the hub and the answer comes back to it
through the hub; the agent answers you in the terminal, where you asked. The hub tells
an agent, with every answer it delivers, whether anyone on the WebUI is waiting for it,
so a request typed in a terminal is answered in that terminal and a request from the
WebUI is answered on the WebUI.

### Talking to an agent on the WebUI

Click an agent's card on the Courtyard page and type in the box at the bottom. Your
message arrives in the agent's terminal as a conversation turn marked as coming from the
operator; it is never gated. The agent's replies appear in the same pane; a card showing
**1 new** has an unread reply.

An agent can write to you first, for example to report that something blocks it. Such a
message waits for no answer: its thread on your line closes at once. Your own messages
open a thread of yours, which stays open until you close it in the pane header.

A line between two agents has no input box; the only thing you write on a line is the
comment that travels with your verdict. Messages to an agent whose terminal is closed
wait on its line and are delivered when the agent starts again.

## Memory

The hub keeps what happened between the agents and what you ruled; it never reads an
agent's own files. The **Memory** page holds two kinds of record:

- **Case files.** When a thread closes (the agent that opened it calls
  `courtyard_close_thread`), the hub files the exchange: who asked, what was settled,
  every verdict with its comment, and the messages. Threads the shift expired never
  become case files.
- **Notes.** An agent deposits a lesson with `courtyard_note`, for one line (the peer it
  names, or its only line) or team-wide. A note on a supervised line, or any team-wide
  note, waits under **Notes waiting for you**: approve, return with a comment, or drop.
  Returned and dropped notes reach their author as a hub notice. Your own notes,
  **+ write a note**, are accepted at once and team-wide unless you scope them.

Agents read memory with `courtyard_recall(question)`: a bounded listing (Admin,
Defaults: **Recall returns**, **Recall trims to**) of the best matches among what that
agent may see, ranked by the ask, a note's body and the participants' declared domains;
a handle in the listing fetches the full case file. Under `manual` discovery an agent
recalls only from the lines it is party to. You see everything on the Memory page:
search, filter by participant, read any record in full.

**Export.** **export JSON Lines** on the Memory page, or `GET /api/memory/export`, gives
every record in full, one JSON document per line, oldest first, superseded records and
notes in every state included with their status. The query parameters `participant`,
`line` and `since` narrow it; `since` is how an external system pulls only what is new.

**Retention.** A case file lives as long as the archive it was distilled from: deleting
an archive deletes its case files, and the confirmation says how many. Notes are kept.

## Hub administration

The **Admin** page:

- **Status**: hub health and configuration, the supervisor (with **restart hub** when
  launchd runs the hub), counts, and the links to the API reference and the database
  browser.
- **Teams**: the registered charters, which one is current, each team's last load report
  and the files it wrote, its agents (with a directory chooser each) and links, and
  **reload from disk**.
- **Settings**: Team mode (only `On shift`; `Always on` is planned, not implemented yet)
  and Discovery (`auto` or `manual`).
- **Terminal application**: the app Start shift opens agents in, and custom start
  strings. A start string must contain `{command}`, where the launch command goes, and
  may contain `{dir}`; its name may not shadow a built-in.
- **Defaults**: the mode new lines start in; the thread budget (0 means none); **Recall
  returns**, how many records one `courtyard_recall` call may return; **Recall trims
  to**, how many characters of the ask and the resolution a listing shows.
- **Appearance**: the theme (follow the system, light or dark), remembered per browser.
- **Message envelope**: what the agents receive around a message body, with the token
  overhead of each block.

**Similarity search for memory.** Recall is full text by default. With a local
embeddings endpoint in `.env`, it becomes hybrid, full text and vector similarity fused,
so a paraphrased question finds a case file that shares no word with it:

```sh
COURTYARD_EMBEDDINGS_URL=http://127.0.0.1:11434/v1/embeddings   # Ollama's OpenAI-compatible endpoint
COURTYARD_EMBEDDINGS_MODEL=nomic-embed-text                      # after: ollama pull nomic-embed-text
```

Any OpenAI-compatible endpoint works (LM Studio, vLLM, llama.cpp). The hub embeds records
in the background, a batch every `COURTYARD_EMBED_SWEEP_SECONDS`; the Memory page shows
how many carry a vector, and `POST /api/memory/embed` runs a pass at once. Changing the
model re-embeds everything. A non-local endpoint is refused unless
`COURTYARD_EMBEDDINGS_ALLOW_REMOTE=1` is set. The postgres image is `pgvector/pgvector`
(postgres 18 with the vector extension).

**The API reference.** http://127.0.0.1:2626/api/docs is the interactive reference to
every hub route (Swagger UI over `/api/openapi.json`), tried against the running hub.
Admin routes need nothing; for the agent-scoped routes press **Authorize** and paste the
agent's token from its launch config. The page's assets load from a public CDN.

**The database browser.** `make db-ui` starts Adminer beside the compose postgres at
http://127.0.0.1:8080 (`COURTYARD_ADMINER_PORT`). Server `postgres`, user and password
`courtyard`, database `courtyard`; the tests use `courtyard_test`, scratch hubs
`courtyard_scratch_<name>`. Bound to 127.0.0.1 only; `make db-down` stops it with
postgres.

**Logs.** The hub logs to stdout at `COURTYARD_LOG_LEVEL`. A 4xx response logs as
WARNING and a 5xx as ERROR, so `WARNING` keeps failures visible while routine lines go
quiet. At every level the hub prints one ready line once it is up: its address, the
WebUI directory, the postgres it talks to and what the level will show.

**Checks.** `make demo` runs two scripted dummy agents through the hub, including a
supervised gate; `make demo-stop` removes them. `make test-comms` proves the operator to
agent to operator round trip against a live Claude Code session.
`uv run python scripts/runbook/terminal_spawners.py <Terminal|iTerm2|Ghostty>` opens,
verifies and closes one window in the named terminal application; run it after
installing or updating a terminal app.

**Recovering from a wiped database.** After `make db-nuke`, registrations and tokens are
gone while each project directory still holds its old files with a dead token. Exit the
old sessions and choose the charter directory again: every agent is registered anew and
the directories `workdirs.local.yml` lists get their files rewritten. For an agent whose
directory is not listed, choose it under **Admin, Teams**, or **edit**, **save**. Then
start the agents again.
