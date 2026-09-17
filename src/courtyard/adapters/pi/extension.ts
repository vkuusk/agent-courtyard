/**
 * Written by the courtyard for agent '__COURTYARD_AGENT_NAME__' — the pi adapter
 * (design §7.1/§7.3, item 36). One extension per agent, regenerated on every
 * install. Do NOT commit this file: it carries the agent's hub token (chmod 600).
 *
 * It is four things at once, mirroring the Claude Code adapter and its hook:
 *  - a channel: the hub pushes each message to a local endpoint, and this
 *    extension injects it into the session via pi.sendMessage (triggerTurn wakes
 *    an idle session; deliverAs "followUp" queues politely on a busy one);
 *  - a toolbox: courtyard_send / courtyard_close_thread / courtyard_inbox /
 *    courtyard_peers / courtyard_recall / courtyard_note / courtyard_ack, registered natively
 *    at session start with the definitions the hub serves;
 *  - a hub adapter: attaches with a channel endpoint, heartbeats, detaches at
 *    session end. Attach retries forever, so hub/agent launch order is free;
 *  - the membership context (D40): the block naming this agent and its team,
 *    stored in the session at its start and again after compaction.
 *
 * Deliberately thin (D14): the authority envelope and the peers listing arrive
 * rendered by the hub and are forwarded verbatim, never re-derived here.
 */
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";
import { appendFileSync, mkdirSync } from "node:fs";

const HUB_URL = "__COURTYARD_HUB_URL__";
const AGENT_NAME = "__COURTYARD_AGENT_NAME__";
const TOKEN = "__COURTYARD_TOKEN__";
const HEARTBEAT_SECONDS = 5; // match the hub (D23/D28)
const LOG_DIR = ".courtyard"; // runtime artifacts only; pi runs in the project dir
const CONTEXT_TYPE = "courtyard-context"; // the membership block's customType (D40)
const CONTEXT_TIMEOUT_MS = 2000; // as the Claude Code hook: a session start never waits long
// The membership block as install rendered it, without the team's name: stored when the
// hub does not answer at session start.
const CONTEXT_FALLBACK = __COURTYARD_CONTEXT__;
// The tool definitions and this extension's own texts as install rendered them
// (courtyard/texts): used when the hub does not answer at session start.
const TEXTS_FALLBACK = __COURTYARD_TEXTS__;

export default function (pi) {
  const channelToken = randomBytes(24).toString("base64url");
  let server = null;
  let endpoint = null;
  let beatTimer = null;
  let stopped = false;
  let ui = null; // captured from session_start; every use is best-effort
  let hubDown = false;
  let texts = TEXTS_FALLBACK; // replaced by the hub's current wording at session start

  // A text this extension words on its own side of the connection: a fetched
  // template with plain {name} placeholders.
  const local = (key, values = {}) =>
    String(texts.local[key] || TEXTS_FALLBACK.local[key] || key).replace(
      /\{(\w+)\}/g,
      (_, name) => String(values[name]),
    );

  // The delivery trail (`.courtyard/adapter.log`): the same ground truth the Claude
  // Code adapter keeps on stderr — what cracked the silent-loss incidents there.
  function log(line) {
    try {
      mkdirSync(LOG_DIR, { recursive: true }); // the membership context logs before boot
      appendFileSync(`${LOG_DIR}/adapter.log`, `${new Date().toISOString()} ${line}\n`);
    } catch {
      /* logging must never break delivery */
    }
  }

  // Footer status: the pi equivalent of the claude-code status line (item 2), live.
  function status(text) {
    try {
      if (ui) ui.setStatus("courtyard", `⏺ ${AGENT_NAME} · courtyard · ${text}`);
    } catch {
      /* no UI in json/print modes */
    }
  }

  function notify(text, level) {
    try {
      if (ui) ui.notify(text, level);
    } catch {
      /* no UI in json/print modes */
    }
  }

  async function api(method, path, body) {
    const resp = await fetch(HUB_URL + path, {
      method,
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = resp.status === 204 ? null : await resp.json().catch(() => null);
    if (!resp.ok) {
      const detail = (data && data.error) || {};
      // Surfaced verbatim, in the hub's wording: turn violations and gate errors
      // are written to be read by the model, and softening them would defeat the
      // backpressure. An error the hub did not word gets the same frame here.
      const err = new Error(
        detail.rendered ||
          local("results.refused", {
            code: detail.code || "http_error",
            message: detail.message || resp.statusText,
          }),
      );
      err.code = detail.code;
      throw err;
    }
    return data;
  }

  const present = (message) => (message && message.rendered) || (message && message.body) || "";

  function deliver(message) {
    // The hub-rendered envelope, injected as a courtyard message — never as the
    // user (item 36: a peer's message must not impersonate the operator).
    pi.sendMessage(
      {
        customType: "courtyard",
        content: present(message),
        display: true,
        details: {
          from: (message && message.sender_name) || "hub",
          kind: message && message.kind,
          seq: message && message.seq,
        },
      },
      { triggerTurn: true, deliverAs: "followUp" },
    );
    log(`delivered kind=${message && message.kind} seq=${message && message.seq} id=${message && message.id}`);
  }

  async function attach() {
    return api("POST", `/api/agents/${AGENT_NAME}/attach`, {
      endpoint,
      channel_token: channelToken,
      channel_flag: "present", // this extension IS the channel; there is no flag to forget
    });
  }

  async function collectQueued() {
    const messages = await api("GET", `/api/agents/${AGENT_NAME}/inbox`);
    for (const message of messages) deliver(message);
  }

  function startServer() {
    return new Promise((resolve) => {
      server = createServer((req, res) => {
        if (req.method !== "POST" || req.headers["x-courtyard-channel-token"] !== channelToken) {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end('{"error":"bad channel token"}');
          return;
        }
        let raw = "";
        req.on("data", (chunk) => (raw += chunk));
        req.on("end", () => {
          try {
            deliver(JSON.parse(raw).message);
          } catch (exc) {
            res.writeHead(500, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: String(exc) }));
            return;
          }
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end('{"ok":true}');
        });
      });
      server.listen(0, "127.0.0.1", () => {
        endpoint = `http://127.0.0.1:${server.address().port}/`;
        resolve();
      });
    });
  }

  async function boot() {
    try {
      mkdirSync(LOG_DIR, { recursive: true });
    } catch {
      /* read-only dir: the log is optional */
    }
    await startServer();
    status("connecting…");
    // Attach retries forever, every 2 s (feedback item 12): the operator's habit
    // is agents first, hub second, and a session must never need relaunching
    // just because it won the race.
    let attempt = 0;
    while (!stopped) {
      try {
        await attach();
        break;
      } catch (exc) {
        attempt += 1;
        if (exc?.code === "invalid_token") {
          // The token in this workdir's files is not the hub's token for this agent
          // (database rebuilt, or token rotated, after they were written): retrying
          // cannot fix it. Said once, then about once a minute.
          if (attempt === 1 || attempt % 30 === 0) {
            console.error(
              "courtyard: the hub rejected this agent's token; rewrite the agent's files" +
                " from the WebUI (Agents, edit, launch config, write both files) and restart",
            );
          }
          status("token rejected");
        } else if (attempt === 1) {
          console.error("courtyard: hub not reachable yet, retrying every 2s");
          status("hub unreachable");
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
    if (stopped) return;
    status("connected");
    log(`attached as ${AGENT_NAME} (endpoint ${endpoint})`);
    beatTimer = setInterval(async () => {
      try {
        const beat = await api("POST", `/api/agents/${AGENT_NAME}/heartbeat`);
        if (hubDown) {
          hubDown = false;
          status("connected");
          notify("courtyard: hub connection restored", "info");
          log("hub connection restored");
        }
        if (beat && beat.queued) await collectQueued(); // a push failed; the pull path recovers it
      } catch (exc) {
        if (exc.code === "not_attached") {
          // hub restarted, or our channel was replaced — re-attach
          try {
            await attach();
          } catch {
            /* next beat retries */
          }
        } else if (!hubDown) {
          hubDown = true;
          status("hub unreachable");
          notify("courtyard: hub connection lost", "warning");
          log("hub connection lost");
        }
      }
    }, HEARTBEAT_SECONDS * 1000);
  }

  // D40 on pi: the membership context. Claude Code gets it from a SessionStart hook;
  // here the extension stores the hub-rendered block as a custom message (no turn)
  // before it attaches, so the first delivery already finds it, and stores it again
  // once compaction has summarized it away. A resumed, forked or reloaded session that
  // still holds it is left alone. before_agent_start is no use for this: pi fires it
  // only for a typed prompt, never for a turn our own delivery starts.
  async function membershipText() {
    try {
      const resp = await fetch(`${HUB_URL}/api/agents/${AGENT_NAME}/session-context`, {
        signal: AbortSignal.timeout(CONTEXT_TIMEOUT_MS),
      });
      const data = resp.ok ? await resp.json() : null;
      if (data && data.text) return data.text;
    } catch {
      /* the hub is down or slow: the built-in text, without the team's name */
    }
    return CONTEXT_FALLBACK;
  }

  function holdsMembership(ctx) {
    try {
      return ctx.sessionManager
        .buildContextEntries()
        .some((entry) => entry && entry.type === "custom_message" && entry.customType === CONTEXT_TYPE);
    } catch {
      return false; // no session state to ask: store it
    }
  }

  async function addMembership(ctx) {
    if (holdsMembership(ctx)) return;
    pi.sendMessage({ customType: CONTEXT_TYPE, content: await membershipText(), display: true });
    log("membership context added");
  }

  pi.on("session_start", async (_event, ctx) => {
    ui = ctx && ctx.ui ? ctx.ui : null;
    await registerTools().catch((exc) => console.error(`courtyard: tools failed to register: ${exc}`));
    await addMembership(ctx).catch((exc) => console.error(`courtyard: membership context failed: ${exc}`));
    boot().catch((exc) => console.error(`courtyard: adapter failed to start: ${exc}`));
  });

  pi.on("session_compact", async (_event, ctx) => {
    await addMembership(ctx).catch((exc) => console.error(`courtyard: membership context failed: ${exc}`));
  });

  pi.on("session_shutdown", async () => {
    stopped = true;
    if (beatTimer) clearInterval(beatTimer);
    if (server) server.close();
    try {
      await api("POST", `/api/agents/${AGENT_NAME}/detach`);
      log("detached");
    } catch {
      /* the liveness sweep covers an unclean exit */
    }
  });

  // /courtyard in the TUI: connection state and queue at a glance, no LLM involved.
  pi.registerCommand("courtyard", {
    description: "Show this agent's courtyard connection and queued messages",
    handler: async (_args, ctx) => {
      try {
        const beat = await api("POST", `/api/agents/${AGENT_NAME}/heartbeat`);
        ctx.ui.notify(
          `courtyard: connected as ${AGENT_NAME} · ${beat.queued || 0} queued`,
          "info",
        );
      } catch (exc) {
        ctx.ui.notify(`courtyard: hub unreachable (${exc.message || exc})`, "warning");
      }
    },
  });

  // TUI rendering of courtyard messages: display-only — the model receives the
  // exact envelope either way. pi-tui resolves only inside pi; anywhere else
  // (the bare-node test harness) the import fails and default rendering stands.
  (async () => {
    try {
      const { Box, Text } = await import("@earendil-works/pi-tui");
      pi.registerMessageRenderer("courtyard", (message, { expanded, outputPad }, theme) => {
        const details = message.details || {};
        const head = theme.fg(
          "success",
          `✉ courtyard · from ${details.from || "hub"} · ${details.kind || "message"}`,
        );
        const body = expanded
          ? message.content
          : message.content.split("\n").slice(0, 12).join("\n");
        const box = new Box(outputPad, 1, (t) => theme.bg("customMessageBg", t));
        box.addChild(new Text(`${head}\n${body}`, 0, 0));
        return box;
      });
    } catch {
      /* not running inside pi: keep the default rendering */
    }
  })();

  // -- the toolbox -------------------------------------------------------------------
  // What each tool does lives here; how it is described to the model (name, label,
  // description, parameters, guidelines) comes from the hub, the same definitions the
  // Claude Code adapter lists (design communication-protocols.md section 8).

  const text = (value) => ({ content: [{ type: "text", text: value }], details: {} });

  const EXECUTE = {
    async courtyard_send(params) {
      const to = (params.to || "").trim();
      const body = params.message || "";
      if (!to || !body.trim()) throw new Error(local("results.required.to_and_message"));
      const message = await api("POST", "/api/lines/send", {
        to,
        body,
        new_thread: Boolean(params.new_thread),
      });
      // worded by the hub (D14), like the envelope and the peers listing
      return text(message.result || message.status);
    },

    async courtyard_close_thread(params) {
      const peer = (params.peer || "").trim();
      if (!peer) throw new Error(local("results.required.peer"));
      const thread = await api("POST", "/api/lines/close-thread", { peer });
      return text(thread.result || thread.state);
    },

    async courtyard_inbox() {
      const messages = await api("GET", `/api/agents/${AGENT_NAME}/inbox`);
      if (!messages.length) return text(local("results.inbox_empty"));
      return text(messages.map(present).join("\n"));
    },

    async courtyard_peers() {
      const peers = await api("GET", `/api/agents/${AGENT_NAME}/peers`);
      return text(peers.rendered);
    },

    async courtyard_recall(params) {
      // Rendered by the hub: trimmed, bounded and filtered to what this agent may see.
      const caseId = (params.case || "").trim();
      if (caseId) {
        const record = await api("GET", `/api/agents/${AGENT_NAME}/recall/${encodeURIComponent(caseId)}`);
        return text(record.rendered || "");
      }
      const query = new URLSearchParams({ q: (params.question || "").trim() });
      if (params.limit) query.set("limit", String(params.limit));
      const view = await api("GET", `/api/agents/${AGENT_NAME}/recall?${query}`);
      return text(view.rendered);
    },

    async courtyard_note(params) {
      const body = (params.body || "").trim();
      if (!body) throw new Error(local("results.required.body"));
      const record = await api("POST", `/api/agents/${AGENT_NAME}/notes`, {
        body,
        peer: (params.peer || "").trim() || null,
        team_wide: Boolean(params.team_wide),
      });
      return text(record.rendered || local("results.noted", { id: record.id }));
    },

    async courtyard_ack(params) {
      const token = (params.token || "").trim();
      if (!token) throw new Error(local("results.required.token"));
      const result = await api("POST", `/api/agents/${AGENT_NAME}/ack`, { token });
      return text(result.result || (result.ok ? "confirmed" : "no open check"));
    },
  };

  async function fetchTexts() {
    try {
      const resp = await fetch(`${HUB_URL}/api/agents/${AGENT_NAME}/texts`, {
        signal: AbortSignal.timeout(CONTEXT_TIMEOUT_MS),
      });
      const data = resp.ok ? await resp.json() : null;
      if (data && Array.isArray(data.tools) && data.tools.length && data.local) return data;
    } catch {
      /* the hub is down or slow: the definitions install rendered */
    }
    return TEXTS_FALLBACK;
  }

  // pi awaits session_start handlers and activates a tool the moment it is registered,
  // so tools registered here are in the session's first request. Registering a name
  // again replaces its definition: a later session start picks up a new wording.
  async function registerTools() {
    texts = await fetchTexts();
    for (const definition of texts.tools) {
      const execute = EXECUTE[definition.name];
      if (!execute) continue; // a tool this extension does not know how to run
      pi.registerTool({ ...definition, execute: (_toolCallId, params) => execute(params || {}) });
    }
    log(`tools registered (${texts === TEXTS_FALLBACK ? "packaged" : "hub"} wording)`);
  }
}
