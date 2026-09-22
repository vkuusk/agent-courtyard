// Agents page: the registry — list with liveness, and three actions per row. `edit` is
// where the agent is changed: save writes the record, the charter and the files in the
// agent's directory (connect); rotate token connects at once. `launch config` shows the
// files as they are on disk, read-only. `remove ▾` offers disconnect (files out, agent
// stays) and unregister (files out, agent off the hub and the charter). Every operation
// has one place. Clicking a row selects that agent for the input box at the bottom.

import { html, useEffect, useState } from "../../vendor/htm-preact-standalone.module.js";
import { api, ApiError } from "../api.js";
import { store, select, currentTeam, applyTeams } from "../store.js";
import { useStore, fmtAgo, CopyButton, COLORS, leastUsedColor, toast } from "../ui.js";

// Write-back (design team-charter.md, D33 slice 3): while a team is current, agent
// changes are also written into its charter files — these helpers say so on the forms.
const charterOf = (agentName) => {
  const team = currentTeam();
  if (!team?.charter) return null;
  if (agentName && !team.charter.agents.some((a) => a.name === agentName)) return null;
  return team;
};

// The launch command; the agent's declared model rides along so nobody forgets to set it.
// The channels preview drifted twice in four days: 2.1.241 stopped
// honouring this flag, 2.1.245 restored it — and made the two-flag workaround fail. This
// single-flag form is verified end-to-end by tests/communications/oper-agent1-oper.py.
// --settings approves the courtyard MCP server for the launch: Claude Code ignores the
// approval stored in .claude/settings.local.json in a workdir that is not a git checkout.
// Must match shift.py's CLAUDE_LAUNCH.
const claudeLaunch = (agent) =>
  "claude --dangerously-load-development-channels server:courtyard" +
  ` --settings '{"enabledMcpjsonServers":["courtyard"]}'` +
  (agent.model ? ` --model ${agent.model}` : "");

function dummyCommand(agent, token, behavior) {
  return [
    "uv run courtyard-dummy \\",
    `  --hub ${location.origin} \\`,
    `  --name ${agent.name} \\`,
    `  --token ${token} \\`,
    `  --behavior ${behavior}`,
  ].join("\n");
}

// L0 copy-paste launch for a real Claude Code agent (design §8/D8): the project-level
// MCP config, then the command that starts the session with the channel enabled.
function claudeConfig(agent, token, adapterCommand) {
  const config = {
    mcpServers: {
      courtyard: {
        command: adapterCommand,
        env: {
          COURTYARD_HUB_URL: location.origin,
          COURTYARD_AGENT_NAME: agent.name,
          COURTYARD_TOKEN: token,
        },
      },
    },
  };
  return JSON.stringify(config, null, 2);
}

// The agent-side profile (WP-A, D21): pre-approves the courtyard tools (no per-send
// permission prompt in the agent's terminal), sets the declared model, and a status line
// that names the agent so its terminal is recognisable.
function claudeSettings(agent) {
  const settings = {
    permissions: { allow: ["mcp__courtyard"] },
    ...(agent.model ? { model: agent.model } : {}),
    statusLine: { type: "command", command: `echo '⏺ ${agent.name} · courtyard'`, padding: 0 },
  };
  return JSON.stringify(settings, null, 2);
}

// The launch wrapper (item 35, D31) — must match install.py's start_script verbatim,
// marker comment included, so a hand-saved copy is still recognised by uninstall.
function claudeScript(agent) {
  return [
    "#!/bin/sh",
    `# Written by the courtyard for agent '${agent.name}'. Starts this agent's Claude Code`,
    "# session connected to the courtyard hub (the channel flag included).",
    "# Regenerated on every install; extra arguments are passed through to claude.",
    `cd "$(dirname "$0")" && exec ${claudeLaunch(agent)} "$@"`,
    "",
  ].join("\n");
}

// Which agents have files in a directory: connect and disconnect apply to these only
// (a dummy is a command line, the operator is a person).
const hasFiles = (agent) => agent.type === "claude-code" || agent.type === "pi";

// `remove ▾` on the row: disconnect (the files leave the directory, the agent stays
// registered and in the charter; reversible, so it acts at once) or unregister (the
// dialog). One menu, so the row keeps three buttons.
function RemoveMenu({ agent, onUnregister }) {
  const [open, setOpen] = useState(null); // null = closed; {top, right} = where to draw it
  // fixed positioning: the table clips absolute children, and the menu must outlive the cell
  const toggle = (e) => {
    e.stopPropagation();
    if (open) return setOpen(null);
    const r = e.currentTarget.getBoundingClientRect();
    setOpen({ top: r.bottom + 4, right: window.innerWidth - r.right });
  };
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(null);
    document.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);
  const disconnect = async () => {
    setOpen(null);
    // the result as a toast: a note in the row would reflow the table
    try {
      await api.disconnectAgent(agent.name);
      toast(`${agent.name} disconnected: the courtyard files left ${agent.workdir}`);
    } catch (err) {
      if (err.code === "nothing_to_disconnect") toast(`${agent.name}: nothing to take out of ${agent.workdir}`);
      else toast(`${agent.name}: ${err.message}`, { error: true });
    }
  };
  const canDisconnect = hasFiles(agent) && Boolean(agent.workdir);
  return html`<span class="menu-wrap" onKeyDown=${(e) => e.key === "Escape" && setOpen(null)}>
    <button class="btn danger" aria-haspopup="menu" aria-expanded=${Boolean(open)}
      onClick=${toggle}>remove ▾</button>
    ${open
      ? html`<div class="menu" role="menu" style=${`top:${open.top}px;right:${open.right}px`}
          onClick=${(e) => e.stopPropagation()}>
          <button class="btn" role="menuitem" disabled=${!canDisconnect} onClick=${disconnect}
            title=${canDisconnect
              ? `Take the courtyard files out of ${agent.workdir}. ${agent.name} stays on the team; save in edit connects the directory again.`
              : "nothing to disconnect: no project directory"}>disconnect</button>
          <button class="btn danger" role="menuitem"
            title="Take the files out and remove the agent from the hub and the team charter"
            onClick=${() => { setOpen(null); onUnregister(agent); }}>unregister</button>
        </div>`
      : null}
  </span>`;
}

function DummyPanel({ agent, token }) {
  const [behavior, setBehavior] = useState("manual");
  const cmd = dummyCommand(agent, token, behavior);
  return html`<div>
    <div class="form-row"><span class="small muted">behavior:</span>
      <select value=${behavior} onChange=${(e) => setBehavior(e.target.value)}>
        <option value="manual">manual: you type the replies</option>
        <option value="echo">echo: acknowledges everything</option>
      </select></div>
    <pre class="cmd">${cmd}</pre><${CopyButton} text=${cmd} />
  </div>`;
}

// Item 37: pick a directory by browsing instead of typing. browse… asks the hub to open
// the REAL macOS folder dialog (the hub shares the operator's screen, the same premise
// the shift uses for Terminal windows); this web dialog is the fallback where no native
// dialog exists — not macOS, no GUI, or a remote hub one day.
export function DirPicker({ onPick, prompt }) {
  // exported: Admin's Teams section picks the charter directory with the same control
  const [state, setState] = useState(null); // null = closed; {path, parent, dirs} = open
  const load = (path) => api.fsDirs(path).then(setState).catch((err) => alert(err.message));
  const browse = () =>
    api.pickDir(prompt ?? "Choose a directory for the courtyard")
      .then((r) => r.path && onPick(r.path)) // null path = the operator cancelled
      .catch((err) => {
        if (err.code === "native_picker_unavailable") load(); // the web dialog instead
        else alert(err.message);
      });
  return html`<span>
    <button type="button" class="btn" title="choose a directory on the hub's machine"
      onClick=${browse}>browse…</button>
    ${state
      ? html`<div class="overlay" onClick=${(e) => e.target === e.currentTarget && setState(null)}
          onKeyDown=${(e) => e.key === "Escape" && setState(null)}>
          <div class="dialog" role="dialog" aria-modal="true" aria-label="Choose a directory"
            style="min-width:30rem;max-width:80vw">
            <h3 style="word-break:break-all;font-family:var(--mono);font-size:.9rem">${state.path}</h3>
            <div style="max-height:45vh;overflow:auto;display:flex;flex-direction:column;gap:.15rem">
              ${state.parent
                ? html`<button type="button" class="btn" style="text-align:left"
                    onClick=${() => load(state.parent)}>↰ ..</button>`
                : null}
              ${state.dirs.map((d) => html`<button type="button" class="btn" style="text-align:left"
                onClick=${() => load(`${state.path}/${d}`)}>${d}/</button>`)}
              ${!state.dirs.length ? html`<div class="small muted">no subdirectories</div>` : null}
            </div>
            <div class="form-row" style="margin-top:.6rem">
              <button type="button" class="btn primary"
                onClick=${() => { onPick(state.path); setState(null); }}>use this directory</button>
              <button type="button" class="btn" onClick=${() => setState(null)}>cancel</button>
            </div>
          </div>
        </div>`
      : null}
  </span>`;
}

// The pi adapter (item 36, D32) is one extension file, too long to copy-paste: the hub
// writes it (with the agent's token inside), and pi auto-discovers it from .pi/extensions/.
function PiPanel({ agent }) {
  return html`<div>
    <div class="small muted">The whole adapter is one file, <code>.pi/extensions/courtyard.ts</code>, written by
      the hub with this agent's token inside (chmod 600, keep it out of git). pi loads it
      automatically; there is no flag to remember, and starting the
      agent is <code>./start-with-courtyard.sh</code> (or <code>pi</code>, with <code>--model</code> when the agent
      declares a model) in its directory.</div>
    <div class="small muted" style="margin-top:.8rem">The hub writes it, and the start script, into
      ${agent.workdir ? html`<code>${agent.workdir}</code>` : "the agent's directory"} whenever the agent is saved or
      its token rotated. If the hub cannot see the directory (live mode), run
      <code>uv run courtyard-invite --register</code> for this agent on the machine that can.</div>
  </div>`;
}

function ClaudePanel({ agent, token, adapterCommand }) {
  const config = claudeConfig(agent, token, adapterCommand);
  const settings = claudeSettings(agent);
  const script = claudeScript(agent);
  return html`<div>
    <div class="small muted">1. Save as .mcp.json in ${agent.name}'s project directory:</div>
    <pre class="cmd">${config}</pre><${CopyButton} text=${config} />
    <div class="small muted" style="margin-top:.8rem">2. Save as .claude/settings.local.json there too; it pre-approves the
      courtyard tools (no permission prompt on every send), sets the model and a status line naming the agent:</div>
    <pre class="cmd">${settings}</pre><${CopyButton} text=${settings} />
    <div class="small muted" style="margin-top:.8rem">3. Save as start-with-courtyard.sh there too and make it
      executable (chmod +x start-with-courtyard.sh). Starting the agent is then ./start-with-courtyard.sh; the
      script carries the channel flag, needed while channels are in research preview (a bare claude session
      cannot hear the hub):</div>
    <pre class="cmd">${script}</pre><${CopyButton} text=${script} />
    <div class="small muted" style="margin-top:.8rem">${agent.workdir
      ? html`These three files are written into <code>${agent.workdir}</code> whenever the agent is saved
          or its token rotated (dev mode; the hub shares this machine's disk). Copy them by hand only
          where the hub cannot see the directory.`
      : "Set a project directory (edit) and the hub writes these three files there on save."}</div>
  </div>`;
}

// The launch config for one agent, read-only: the files as the hub writes them (or the
// dummy's command) with the token. Opens any time from the list — the hub keeps the token.
function LaunchPanel({ agent, token, note, adapterCommand, onClose }) {
  return html`<div class="panel ok">
    <div class="panel-head"><h3>${agent.name} · launch config</h3>
      <button class="link" onClick=${onClose}>close</button></div>
    ${note ? html`<div class="warn" style="margin-bottom:.6rem">${note}</div>` : null}
    ${agent.type === "claude-code"
      ? html`<${ClaudePanel} agent=${agent} token=${token} adapterCommand=${adapterCommand} />`
      : agent.type === "pi"
        ? html`<${PiPanel} agent=${agent} />`
        : html`<${DummyPanel} agent=${agent} token=${token} />`}
    <div class="small muted" style="margin-top:.8rem">The hub keeps this token; "rotate token" under edit
      replaces it and rewrites the files.</div>
  </div>`;
}

function NoTokenPanel({ agent, onRotate, onClose }) {
  return html`<div class="panel">
    <div class="panel-head"><h3>${agent.name} · no stored token</h3>
      <button class="link" onClick=${onClose}>close</button></div>
    <div class="small" style="margin-bottom:.6rem">${agent.name} was registered before the hub kept tokens, so its
      launch config cannot be shown. Rotate its token to get one; the files are written into its directory
      and its running session then needs a restart.</div>
    <button class="btn" onClick=${() => onRotate(agent)}>rotate token</button>
  </div>`;
}

function AddForm({ onCreated, suggested }) {
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState(null); // null = take the hub's suggestion
  const [workdir, setWorkdir] = useState(""); // controlled so the picker can fill it
  const color = picked ?? suggested;
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    const form = e.currentTarget;
    const data = new FormData(form);
    try {
      const created = await api.createAgent({
        name: data.get("name"),
        type: data.get("type"),
        description: data.get("description") || null,
        sme_domain: data.get("sme_domain") || null,
        anti_scope: data.get("anti_scope") || null,
        workdir: data.get("workdir") || null,
        model: data.get("model") || null,
        color,
      });
      form.reset();
      setPicked(null);
      setWorkdir("");
      onCreated(created);
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "name_taken"
          ? "The name is taken: names are permanent identities (removed agents keep theirs)."
          : err.message,
      );
    }
  };
  // Item 4: identity first (name · type · directory · colour), then the two multiline
  // texts the peers actually read — room to write real sentences.
  return html`<form class="add-form" onSubmit=${submit}>
    <div class="form-row">
      <input name="name" placeholder="name (e.g. scout)" required
        pattern="[A-Za-z0-9][A-Za-z0-9._\\-]{0,63}" title="letters, digits, dots, dashes, underscores" />
      <select name="type" title="claude-code and pi: real agents. dummy: a fake agent for testing.">
        <option value="claude-code">claude-code</option>
        <option value="pi">pi</option>
        <option value="dummy">dummy</option>
      </select>
      <input name="workdir" placeholder="project directory (optional)" value=${workdir}
        onInput=${(e) => setWorkdir(e.target.value)}
        title="the agent's project directory; lets the hub write its config there for you" />
      <${DirPicker} prompt="Choose the agent's project directory" onPick=${setWorkdir} />
      <input name="model" placeholder="model (optional, e.g. sonnet)"
        title="the model its runtime should use: an alias such as sonnet for claude-code, provider/model such as openai/gpt-5.6-luna for pi; the launch command adds --model" />
      <div class="swatches" role="radiogroup" aria-label="colour on the board">
        <span class="small muted">colour:</span>
        ${COLORS.map((c) => html`<button type="button" class="swatch ${c === color ? "selected" : ""}" data-color=${c}
          title=${c} aria-label=${c} aria-pressed=${c === color} onClick=${() => setPicked(c)} />`)}
      </div>
    </div>
    <textarea name="description" rows="2" placeholder="what is this agent for? (shown to peers)"></textarea>
    <textarea name="sme_domain" rows="2"
      placeholder="what does it own? (e.g. the AWS estate); it raises its standing there when it messages peers"></textarea>
    <textarea name="anti_scope" rows="2"
      placeholder="what is it NOT for? (optional); tells peers whom not to ask"></textarea>
    ${charterOf(null)
      ? html`<div class="small muted">The current team has a charter: the new agent is also
          written into <code>${charterOf(null).charter_dir}</code>.</div>`
      : html`<div class="warn">No team is current: registration is refused until the team's
          charter directory is chosen — on the Courtyard page's Team panel, or under
          <a href="#/admin">Admin → Teams</a>.</div>`}
    <div class="form-row">
      <button class="btn primary" disabled=${!currentTeam()}>add agent</button>
      ${error ? html`<div class="error">${error}</div>` : null}
    </div>
  </form>`;
}

// The Edit Agent view: everything that changes the agent, in one place. Save writes the
// record and the charter, then connects the directory (the three files, or pi's two); a
// changed directory is disconnected first, so no old directory keeps a live token. Rotate
// token acts at once (the old token dies immediately) and connects the directory too.
function EditPanel({ agent, note, onRotate, onClose }) {
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);
  const [picked, setPicked] = useState(agent.color);
  const [workdir, setWorkdir] = useState(agent.workdir ?? "");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSaved(null);
    setBusy(true);
    const data = new FormData(e.currentTarget);
    const text = (k) => (data.get(k) || "").trim() || null;
    const oldDir = agent.workdir || null;
    const newDir = text("workdir");
    const notes = [];
    try {
      if (hasFiles(agent) && oldDir && newDir !== oldDir) {
        try {
          await api.disconnectAgent(agent.name, oldDir);
          notes.push(`the files left ${oldDir}`);
        } catch (err) {
          if (err.code !== "nothing_to_disconnect") notes.push(`could not clean ${oldDir}: ${err.message}`);
        }
      }
      const updated = await api.patchAgent(agent.name, {
        description: text("description"),
        sme_domain: text("sme_domain"),
        anti_scope: text("anti_scope"),
        workdir: newDir,
        model: text("model"),
        color: picked,
      });
      store.agents.set(updated.id, updated);
      if (hasFiles(updated) && updated.workdir) {
        try {
          await api.connectAgent(updated.name, updated.workdir);
          notes.push(`files written into ${updated.workdir}; a running session picks them up at its next start`);
        } catch (err) {
          notes.push(`the files were not written into ${updated.workdir}: ${err.message}`);
        }
      }
      setSaved(notes.length ? `saved; ${notes.join("; ")}` : "saved");
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };
  return html`<div class="panel ok">
    <div class="panel-head"><h3><span class="chip" data-color=${picked}>${agent.name}</span> · edit</h3>
      <button class="link" onClick=${onClose}>close</button></div>
    ${note ? html`<div class="warn" style="margin-bottom:.6rem">${note}</div>` : null}
    <form class="add-form" onSubmit=${submit}>
      <div class="form-row">
        <span class="small muted">${agent.type} · name and type are permanent</span>
        <input name="workdir" value=${workdir} placeholder="project directory"
          onInput=${(e) => setWorkdir(e.target.value)} />
        <${DirPicker} prompt="Choose the agent's project directory" onPick=${setWorkdir} />
        <input name="model" defaultValue=${agent.model ?? ""} placeholder="model (e.g. sonnet)" />
        <div class="swatches" role="radiogroup" aria-label="colour on the board">
          <span class="small muted">colour:</span>
          ${COLORS.map((c) => html`<button type="button" class="swatch ${c === picked ? "selected" : ""}" data-color=${c}
            title=${c} aria-label=${c} aria-pressed=${c === picked} onClick=${() => setPicked(c)} />`)}
        </div>
      </div>
      <textarea name="description" rows="2" placeholder="what is this agent for? (shown to peers)"
        defaultValue=${agent.description ?? ""}></textarea>
      <textarea name="sme_domain" rows="2" placeholder="what does it own?"
        defaultValue=${agent.sme_domain ?? ""}></textarea>
      <textarea name="anti_scope" rows="2" placeholder="what is it NOT for? (tells peers whom not to ask)"
        defaultValue=${agent.anti_scope ?? ""}></textarea>
      <div class="small muted">${charterOf(agent.name)
        ? html`${agent.name} is a charter agent of the current team: saved changes are also written
            into <code>${charterOf(agent.name).charter_dir}</code> (the project directory goes to
            <code>workdirs.local.yml</code>, per machine). `
        : null}${hasFiles(agent)
        ? "Save also writes the agent's courtyard files into its project directory."
        : null}</div>
      <div class="form-row">
        <button class="btn primary" disabled=${busy}>${busy ? "saving…" : "save"}</button>
        <button type="button" class="btn" disabled=${busy} onClick=${() => onRotate(agent)}>rotate token</button>
        ${saved ? html`<span class="small muted">${saved}</span>` : null}
        ${error ? html`<div class="error">${error}</div>` : null}
      </div>
    </form>
  </div>`;
}

// Unregister: the files leave the directory first (a dead token left in a project is the
// half-done state that bit us after db-nuke), then the agent leaves the hub and the charter.
function UnregisterDialog({ agent, onClose }) {
  const [busy, setBusy] = useState(false);
  const doRemove = async () => {
    setBusy(true);
    if (hasFiles(agent) && agent.workdir) {
      try {
        await api.disconnectAgent(agent.name);
      } catch (err) {
        if (err.code !== "nothing_to_disconnect") {
          alert(`The files could not be taken out of ${agent.workdir}: ${err.message}\n\nUnregistering anyway.`);
        }
      }
    }
    try {
      await api.removeAgent(agent.name);
      onClose(true);
    } catch (err) {
      alert(err.message);
      onClose(false);
    }
  };
  return html`<div class="overlay" onClick=${(e) => e.target === e.currentTarget && onClose(false)}
      onKeyDown=${(e) => e.key === "Escape" && onClose(false)}>
    <div class="dialog" role="alertdialog" aria-modal="true" aria-label="Unregister ${agent.name}">
      <h3>Unregister ${agent.name}?</h3>
      <p>Its token stops working at once; its conversations move to the Archive. The name
        stays taken; names are permanent identities.</p>
      ${charterOf(agent.name)
        ? html`<p>${agent.name} is a charter agent of the current team: it is also removed
            from the charter files (its entry, links and configuration directory in
            <code>${charterOf(agent.name).charter_dir}</code>).</p>`
        : null}
      ${hasFiles(agent) && agent.workdir
        ? html`<p>The courtyard files leave ${agent.workdir} first: the courtyard entries in
            <code>.mcp.json</code> and <code>.claude/settings.local.json</code>, and
            <code>start-with-courtyard.sh</code> (a running session is not stopped; the dead
            token locks it out).</p>`
        : null}
      <div class="form-row" style="justify-content:flex-end">
        <button class="btn" onClick=${() => onClose(false)}>cancel</button>
        <button class="btn danger" disabled=${busy} ref=${(el) => el?.focus()}
          onClick=${doRemove}>${busy ? "unregistering…" : "unregister"}</button>
      </div>
    </div>
  </div>`;
}

const HEADERS = ["agent", "type", "description", "owns", "status", "last seen", "actions"];

export function Agents() {
  useStore();
  // {agent, token, note} = launch config · {agent, missing} = no stored token ·
  // {agent, edit, note} = the Edit Agent view
  const [panel, setPanel] = useState(null);
  const [removing, setRemoving] = useState(null); // agent in the unregister dialog
  const [adapterCommand, setAdapterCommand] = useState("courtyard-claude-mcp");
  useEffect(() => {
    api.config().then((c) => setAdapterCommand(c.adapter_command)).catch(() => {});
  }, []);

  const agents = [...store.agents.values()]
    .filter((a) => !a.removed_at)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const sel = store.ui.selected;

  const open = async (agent) => {
    try {
      const { token } = await api.agentToken(agent.name);
      setPanel({ agent, token });
    } catch (err) {
      if (err.code === "no_stored_token") setPanel({ agent, missing: true });
      else alert(err.message);
    }
  };
  // Rotation acts at once and connects the directory itself, so no directory holds the
  // dead token longer than the call takes. From edit it reports there; from the no-token
  // panel it opens the launch config that now exists.
  const rotate = async (agent, { stayInEdit = false } = {}) => {
    const sure = confirm(
      `Rotate ${agent.name}'s token?\n\nThe old one stops working at once. The files in the ` +
        "agent's directory are rewritten with the new token; its running session needs a restart " +
        "(a dummy: restart it with the new command).",
    );
    if (!sure) return;
    try {
      const r = await api.rotateToken(agent.name);
      store.agents.set(r.agent.id, r.agent);
      let note = "Token rotated; the old one no longer works.";
      if (hasFiles(r.agent) && r.agent.workdir) {
        try {
          await api.connectAgent(r.agent.name, r.agent.workdir);
          note += ` Files written into ${r.agent.workdir}; restart the agent.`;
        } catch (err) {
          note += ` The files were not written into ${r.agent.workdir}: ${err.message}`;
        }
      } else if (r.agent.type === "dummy") {
        note += " Restart the dummy with the new command (launch config).";
      }
      setPanel(stayInEdit ? { agent: r.agent, edit: true, note } : { agent: r.agent, token: r.token, note });
    } catch (err) {
      alert(err.message);
    }
  };
  // Add/remove can change the current team's charter membership (write-back, D33
  // slice 3); teams have no SSE event, so refresh them for the form hints.
  const refreshTeams = () => {
    if (currentTeam()) api.teams().then(applyTeams).catch(() => {});
  };
  const closeRemove = (removed) => {
    if (removed && panel?.agent.id === removing?.id) setPanel(null);
    if (removed) refreshTeams();
    setRemoving(null);
  };
  // Registration is the first save: an agent with a directory gets its files at once.
  const onCreated = async (c) => {
    store.agents.set(c.agent.id, c.agent); // the SSE event follows; don't wait for it
    select({ kind: "agent", id: c.agent.id });
    refreshTeams();
    let note = "Registered.";
    if (hasFiles(c.agent) && c.agent.workdir) {
      try {
        await api.connectAgent(c.agent.name, c.agent.workdir);
        note = `Registered; files written into ${c.agent.workdir}.`;
      } catch (err) {
        note = `Registered; the files were not written into ${c.agent.workdir}: ${err.message}`;
      }
    } else if (hasFiles(c.agent)) {
      note = "Registered. Set a project directory (edit) and save: the files are written there.";
    }
    setPanel({ agent: c.agent, token: c.token, note });
  };
  const stop = (fn) => (e) => {
    e.stopPropagation();
    fn();
  };

  return html`
    <table>
      <thead><tr>${HEADERS.map((h) => html`<th>${h}</th>`)}</tr></thead>
      <tbody>${agents.map((a) => {
        const pickable = a.type !== "human";
        const selected = sel?.kind === "agent" && sel.id === a.id;
        return html`<tr key=${a.id} class="${pickable ? "pick" : ""} ${selected ? "selected" : ""}"
            onClick=${pickable ? () => select({ kind: "agent", id: a.id }) : null}>
          <td><span class="dot ${a.status}" /><span class="name chip" data-color=${a.color}>${a.name}</span></td>
          <td class="muted">${a.type}</td>
          <td class="muted">${a.description ?? ""}</td>
          <td class="muted">${a.sme_domain ?? ""}</td>
          <td class="muted small">${a.status}</td>
          <td class="muted small">${fmtAgo(a.last_seen_at)}</td>
          <td>${pickable
            ? html`<div class="actions">
                <button class="btn" onClick=${stop(() => setPanel({ agent: a, edit: true }))}>edit</button>
                <button class="btn" onClick=${stop(() => open(a))}>launch config</button>
                <${RemoveMenu} agent=${a} onUnregister=${setRemoving} /></div>`
            : html`<span class="muted small">—</span>`}</td>
        </tr>`;
      })}</tbody>
    </table>
    <div class="small muted" style="margin:.5rem 0 0">Click an agent to select it; the Courtyard page's
      message box follows your selection.</div>
    ${panel?.missing
      ? html`<${NoTokenPanel} agent=${panel.agent} onRotate=${rotate} onClose=${() => setPanel(null)} />`
      : panel?.edit
        ? html`<${EditPanel} key=${panel.agent.id} note=${panel.note}
            agent=${store.agents.get(panel.agent.id) ?? panel.agent}
            onRotate=${(a) => rotate(a, { stayInEdit: true })} onClose=${() => setPanel(null)} />`
        : panel
          ? html`<${LaunchPanel} key=${`${panel.agent.id}:${panel.token}`}
              agent=${store.agents.get(panel.agent.id) ?? panel.agent} token=${panel.token}
              note=${panel.note} adapterCommand=${adapterCommand} onClose=${() => setPanel(null)} />`
          : null}
    ${removing ? html`<${UnregisterDialog} agent=${removing} onClose=${closeRemove} />` : null}
    <${AddAgentPanel} onCreated=${onCreated} />`;
}

// Collapsed by default (his feedback, 2026-08-26): registering is occasional, the form
// was crowding the page.
function AddAgentPanel({ onCreated }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return html`<button class="btn" style="margin-top:.8rem" onClick=${() => setOpen(true)}>+ Add an agent</button>`;
  }
  return html`<div class="panel">
    <div class="panel-head"><h3>Add an agent</h3>
      <button class="link" onClick=${() => setOpen(false)}>close</button></div>
    <${AddForm} onCreated=${(c) => { setOpen(false); onCreated(c); }}
      suggested=${leastUsedColor([...store.agents.values()])} />
  </div>`;
}
