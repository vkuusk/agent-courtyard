"""courtyard-claude-mcp — the Claude Code adapter (design §7.2, decision D-spike).

One stdio MCP server per agent, spawned by Claude Code from the agent's project
`.mcp.json`. It is three things at once:

* **a channel** — declares the `claude/channel` experimental capability, so a
  `notifications/claude/channel` event this server emits arrives in the session as a
  live conversation turn. This is how the hub's pushes reach a running agent.
* **a toolbox** — `courtyard_send` / `courtyard_close_thread` / `courtyard_inbox` /
  `courtyard_peers` / `courtyard_recall` / `courtyard_note`, the agent's side of the adapter contract (§7.1).
* **a hub adapter** — attaches with a channel endpoint + channel token, heartbeats, and
  detaches at session end, exactly like the dummy has done since step 2.

It is deliberately thin (D14): the authority-graded envelope and the peers listing are
rendered by the hub and arrive as text; this process forwards them and never re-derives
them. A new agent type ports the forwarding, not the judgement.

The MCP wire protocol is JSON-RPC 2.0 over newline-delimited stdio. It is implemented
here directly rather than through an SDK: the surface we need is five methods, and the
channel notification is a Claude-Code-specific extension that the typed SDK unions do
not model (the full reasoning: docs/design/adapter-implementation.md). **stdout carries protocol only** — all diagnostics go to stderr, where
Claude Code records them in `~/.claude/debug/<session-id>.txt`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import httpx

from courtyard.common import adapter_texts
from courtyard.common.client import DEFAULT_HUB_URL, ChannelReceiver, HubClient, HubError
from courtyard.common.models import Message

logger = logging.getLogger("courtyard.adapter")

REWRITE_FILES_HINT = (
    "the token in this workdir's .mcp.json is not the hub's token for this agent (the"
    " database was rebuilt or the token rotated after the file was written); on the WebUI"
    " open Agents, edit this agent, launch config, 'write both files', then restart this"
    " session"
)


def attach_failure(exc: Exception, attempt: int) -> tuple[int, str] | None:
    """What to log about a failed attach attempt: None to stay quiet (the first miss is
    reported, then about one in thirty, once a minute at the 2 s cadence). A hub that is not
    there yet is a warning, since it usually arrives. A 401 is named for what it is: the
    token is wrong, and retrying cannot fix it."""
    if attempt != 1 and attempt % 30 != 0:
        return None
    if isinstance(exc, HubError) and exc.code == "invalid_token":
        text = (
            f"attach attempt {attempt}: the hub rejected this agent's token ({exc}): "
            f"{REWRITE_FILES_HINT}. Retrying every 2s, which cannot succeed until then."
        )
        return logging.ERROR, text
    return (
        logging.WARNING,
        f"attach attempt {attempt} failed (hub not reachable yet? retrying every 2s): {exc}",
    )


SERVER_NAME = "courtyard"
SERVER_VERSION = version("courtyard")  # the package's, so it never drifts from pyproject
FALLBACK_PROTOCOL_VERSION = "2025-06-18"
CHANNEL_NOTIFICATION = "notifications/claude/channel"

# The copy of the texts packaged with this adapter (courtyard/texts): what a session
# gets when the hub does not answer at its start. The Admin page's preview reads these.
PACKAGED = adapter_texts.bundle("claude-code")
INSTRUCTIONS: str = PACKAGED["instructions"]
TOOLS: list[dict[str, Any]] = PACKAGED["tools"]
TEXTS_TIMEOUT = 2.0  # as the SessionStart hook: a session start never waits long


def fetch_texts(hub_url: str, agent: str) -> dict[str, Any]:
    """The tool definitions, the instructions and this adapter's own texts, in the hub's
    current wording (design communication-protocols.md section 8); the packaged copy
    when the hub does not answer. Fetched once: Claude Code asks for the instructions
    and the tool list at the start of a session."""
    try:
        resp = httpx.get(f"{hub_url}/api/agents/{agent}/texts", timeout=TEXTS_TIMEOUT)
        resp.raise_for_status()
        fetched = resp.json()
        if fetched.get("tools") and fetched.get("instructions") and fetched.get("local"):
            return fetched
    except Exception as exc:  # noqa: BLE001 - the hub being down is the case this covers
        logger.info("texts not fetched from the hub (%s): using the packaged copy", exc)
    return PACKAGED


CHANNELS_FLAG = "--dangerously-load-development-channels"


def judge_channel_flag(ancestor_cmdlines: list[str]) -> str:
    """Item 33 (D29): decide from this process's ancestry whether the claude session
    was launched with the channels flag. Without it, Claude Code attaches this server,
    serves its tools and ACKs pushes — and silently drops every channel event; the
    only deterministic tell is the launch command itself. Shell wrappers around this
    adapter are skipped (their command line names the adapter, not the session)."""
    for cmd in ancestor_cmdlines:
        if "courtyard-claude-mcp" in cmd:
            continue  # a wrapper spawning this adapter, not the claude session
        if CHANNELS_FLAG in cmd:
            return "present"
        if "claude" in cmd:
            return "absent"
    return "unknown"


def detect_channel_flag() -> str:
    """Walk up the process tree (at most 5 levels) collecting command lines, then
    judge. Anything unreadable stays `unknown` — only definite absence may warn."""
    cmdlines: list[str] = []
    pid = os.getppid()
    try:
        for _ in range(5):
            if pid <= 1:
                break
            out = subprocess.run(
                ["ps", "-o", "ppid=", "-o", "args=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            if not out:
                break
            parent, _, args = out.partition(" ")
            cmdlines.append(args.strip())
            pid = int(parent.strip() or 0)
    except Exception as exc:  # noqa: BLE001 - detection must never break the adapter
        logger.info("channel-flag detection stopped at pid %s: %s", pid, exc)
    return judge_channel_flag(cmdlines)


class ConfigError(Exception):
    """The adapter was started without the environment install writes into `.mcp.json`."""


@dataclass(frozen=True)
class AdapterConfig:
    hub_url: str
    agent: str  # name or uuid; the hub resolves either
    token: str
    heartbeat_seconds: float


def load_config(env: Mapping[str, str] | None = None) -> AdapterConfig:
    env = os.environ if env is None else env
    agent = env.get("COURTYARD_AGENT_NAME") or env.get("COURTYARD_AGENT_ID")
    token = env.get("COURTYARD_TOKEN")
    missing = [
        name
        for name, value in (
            ("COURTYARD_AGENT_NAME or COURTYARD_AGENT_ID", agent),
            ("COURTYARD_TOKEN", token),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "missing environment: " + ", ".join(missing) + ". The courtyard adapter is "
            "configured by `courtyard-invite` (or the WebUI's install button); run it in "
            "this project, or set the variables by hand."
        )
    return AdapterConfig(
        hub_url=env.get("COURTYARD_HUB_URL", DEFAULT_HUB_URL),
        agent=agent,
        token=token,
        heartbeat_seconds=float(
            env.get("COURTYARD_HEARTBEAT_SECONDS", "5")
        ),  # match the hub (D23; 15 -> 5 with D28)
    )


class StdioTransport:
    """Newline-delimited JSON-RPC over stdio. Writes are serialized: the channel push
    arrives on the receiver's HTTP thread while the reader thread may be answering a
    request, and two interleaved writes would corrupt the stream."""

    def __init__(self, stdin=None, stdout=None):
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._lock = threading.Lock()

    def read(self) -> Iterator[dict]:
        while True:
            line = self._stdin.readline()
            if not line:  # EOF: Claude Code closed the session
                return
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("ignoring malformed JSON-RPC line")

    def send(self, payload: dict) -> None:
        with self._lock:
            self._stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self._stdout.flush()


class CourtyardAdapter:
    def __init__(self, config: AdapterConfig, transport: StdioTransport | None = None):
        self._config = config
        self._transport = transport or StdioTransport()
        self._client = HubClient(config.hub_url, config.agent, config.token)
        self._texts = fetch_texts(config.hub_url, config.agent)
        self._receiver: ChannelReceiver | None = None
        self._attached = threading.Event()
        self._stop = threading.Event()
        # Item 33 (D29): detected once — the parent's launch command does not change.
        self._channel_flag = detect_channel_flag()
        if self._channel_flag == "absent":
            logger.warning(
                "the claude session was launched WITHOUT %s — channel events will be "
                "dropped; hub messages will not reach the model",
                CHANNELS_FLAG,
            )

    # -- lifecycle -------------------------------------------------------------------

    def run(self) -> None:
        for request in self._transport.read():
            try:
                self._dispatch(request)
            except Exception:  # one bad request must not kill the session
                logger.exception("error handling %s", request.get("method"))
        self.shutdown()

    def shutdown(self) -> None:
        self._stop.set()
        if self._attached.is_set():
            try:
                self._client.detach()
            except (HubError, httpx.HTTPError) as exc:
                logger.info("detach failed: %s", exc)
        if self._receiver is not None:
            self._receiver.stop()
        self._client.close()

    def _start_channel(self) -> None:
        """Attach after the MCP handshake completes: the hub pushes the queued backlog
        during attach, and a notification sent before initialization would be dropped.

        Retries forever, every 2s (feedback item 12): the operator's habit is agents
        first, hub second — a session must not need relaunching just because it won the
        race. The original five-attempts-then-give-up left agents permanently offline."""
        self._receiver = ChannelReceiver(self._on_delivery)
        attempt = 0
        while not self._stop.is_set():
            try:
                summary = self._client.attach(
                    self._receiver.endpoint, self._receiver.channel_token, self._channel_flag
                )
            except (HubError, httpx.HTTPError) as exc:
                attempt += 1
                report = attach_failure(exc, attempt)
                if report:
                    logger.log(*report)
                self._stop.wait(2.0)
                continue
            self._attached.set()
            logger.info(
                "attached to %s as %s — %d peer(s), %d queued",
                self._config.hub_url,
                summary.agent.name,
                len(summary.roster),
                summary.queued,
            )
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()
            return

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._config.heartbeat_seconds):
            try:
                beat = self._client.heartbeat()
            except HubError as exc:
                if exc.code == "not_attached":  # hub restarted, or our channel was replaced
                    logger.info("re-attaching: %s", exc)
                    self._reattach()
                else:
                    logger.warning("heartbeat refused: %s", exc)
                continue
            except httpx.HTTPError as exc:
                logger.info("heartbeat failed: %s", exc)
                continue
            if beat.get("queued"):
                # A push failed while we were unreachable; the pull path recovers it.
                self._collect_queued()

    def _reattach(self) -> None:
        if self._receiver is None:
            return
        try:
            self._client.attach(
                self._receiver.endpoint, self._receiver.channel_token, self._channel_flag
            )
        except (HubError, httpx.HTTPError) as exc:
            logger.warning("re-attach failed: %s", exc)

    def _collect_queued(self) -> None:
        try:
            for message in self._client.inbox():
                self._on_delivery(message)
        except (HubError, httpx.HTTPError) as exc:
            logger.info("inbox pull failed: %s", exc)

    # -- delivery: hub -> this session ------------------------------------------------

    def _on_delivery(self, message: Message) -> None:
        """Hand a message to the agent as a live conversation turn (D-spike). Called on
        the channel receiver's thread; must return quickly, and writing one line does."""
        self._transport.send(
            {
                "jsonrpc": "2.0",
                "method": CHANNEL_NOTIFICATION,
                "params": {
                    "content": _present(message),
                    # meta keys become <channel> attributes; identifiers only
                    "meta": {
                        "from": message.sender_name or "hub",
                        "kind": message.kind,
                        "seq": str(message.seq),
                    },
                },
            }
        )

    # -- MCP protocol -----------------------------------------------------------------

    def _dispatch(self, request: dict) -> None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            self._reply(request_id, self._initialize_result(request.get("params") or {}))
        elif method == "notifications/initialized":
            threading.Thread(target=self._start_channel, daemon=True).start()
        elif method == "tools/list":
            self._reply(request_id, {"tools": self._texts["tools"]})
        elif method == "tools/call":
            params = request.get("params") or {}
            self._reply(
                request_id,
                self._call_tool(params.get("name", ""), params.get("arguments") or {}),
            )
        elif method == "ping":
            self._reply(request_id, {})
        elif request_id is not None:
            self._reply_error(request_id, -32601, f"method not found: {method}")
        # any other notification is ignored, per JSON-RPC

    def _initialize_result(self, params: dict) -> dict:
        # Echo the client's protocol version: this server uses no version-specific
        # features, so agreeing with Claude Code is the most compatible answer.
        version = params.get("protocolVersion") or FALLBACK_PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {},
                # presence of this key is what registers the session's channel listener
                "experimental": {"claude/channel": {}},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": self._texts["instructions"],
        }

    def _reply(self, request_id: Any, result: dict) -> None:
        if request_id is None:  # it was a notification; nothing to answer
            return
        self._transport.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _reply_error(self, request_id: Any, code: int, message: str) -> None:
        self._transport.send(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        )

    # -- tools --------------------------------------------------------------------------

    def _local(self, key: str, **values: Any) -> str:
        """A text this adapter words on its own side of the connection."""
        return adapter_texts.fill(self._texts["local"][key], **values)

    def _call_tool(self, name: str, arguments: dict) -> dict:
        handlers = {
            "courtyard_send": self._tool_send,
            "courtyard_close_thread": self._tool_close_thread,
            "courtyard_inbox": self._tool_inbox,
            "courtyard_peers": self._tool_peers,
            "courtyard_recall": self._tool_recall,
            "courtyard_note": self._tool_note,
            "courtyard_ack": self._tool_ack,
        }
        handler = handlers.get(name)
        if handler is None:
            return _tool_result(self._local("results.unknown_tool", tool=name), is_error=True)
        try:
            return handler(arguments)
        except HubError as exc:
            # Surfaced verbatim, in the hub's wording: turn violations and gate errors are
            # written to be read by the model, and softening them would defeat the
            # backpressure (§5.4). An error the hub did not word (a validation error, a
            # proxy) gets the same frame here.
            return _tool_result(
                exc.rendered or self._local("results.refused", code=exc.code, message=exc.args[0]),
                is_error=True,
            )
        except httpx.HTTPError as exc:
            return _tool_result(
                self._local("results.unreachable", hub_url=self._config.hub_url, error=exc),
                is_error=True,
            )
        except Exception as exc:  # the call must get SOME reply
            # an exception past this point leaves the request without a JSON-RPC reply
            # and the session waiting on it; an error result at least says what happened
            logger.exception("tool %s failed", name)
            return _tool_result(
                self._local("results.tool_failed", tool=name, error=repr(exc)), is_error=True
            )

    def _tool_send(self, arguments: dict) -> dict:
        to = (arguments.get("to") or "").strip()
        body = arguments.get("message") or ""
        if not to or not body.strip():
            return _tool_result(self._local("results.required.to_and_message"), is_error=True)
        message = self._client.send(to, body, bool(arguments.get("new_thread")))
        return _tool_result(message.result or message.status)  # worded by the hub (D14)

    def _tool_close_thread(self, arguments: dict) -> dict:
        peer = (arguments.get("peer") or "").strip()
        if not peer:
            return _tool_result(self._local("results.required.peer"), is_error=True)
        thread = self._client.close_thread(peer)
        return _tool_result(thread.result or thread.state)  # worded by the hub (D14)

    def _tool_inbox(self, _arguments: dict) -> dict:
        messages = self._client.inbox()
        if not messages:
            return _tool_result(self._local("results.inbox_empty"))
        return _tool_result("\n".join(_present(m) for m in messages))

    def _tool_peers(self, _arguments: dict) -> dict:
        # Ranked, trimmed and worded by the hub (D14); shown to the model as-is.
        return _tool_result(self._client.peers().rendered)

    def _tool_recall(self, arguments: dict) -> dict:
        # Rendered by the hub (D14): trimmed, bounded and filtered to what this agent may see.
        case = (arguments.get("case") or "").strip()
        if case:
            return _tool_result(self._client.recall_case(case).rendered or "")
        question = (arguments.get("question") or "").strip()
        limit = arguments.get("limit")
        try:
            limit = int(limit) if limit not in (None, "") else None
        except (TypeError, ValueError):
            return _tool_result(self._local("results.bad_limit", limit=repr(limit)), is_error=True)
        return _tool_result(self._client.recall(question, limit).rendered)

    def _tool_note(self, arguments: dict) -> dict:
        body = (arguments.get("body") or "").strip()
        if not body:
            return _tool_result(self._local("results.required.body"), is_error=True)
        peer = (arguments.get("peer") or "").strip() or None
        record = self._client.note(body, peer, bool(arguments.get("team_wide")))
        return _tool_result(record.rendered or self._local("results.noted", id=record.id))

    def _tool_ack(self, arguments: dict) -> dict:
        token = (arguments.get("token") or "").strip()
        if not token:
            return _tool_result(self._local("results.required.token"), is_error=True)
        confirmed, result = self._client.ack_delivery(token)
        return _tool_result(result or ("confirmed" if confirmed else "no open check"))


def _present(message: Message) -> str:
    """What the model sees: the hub-rendered authority envelope (§7.5), verbatim.

    A message without one can only come from a hub older than this adapter; the bare body
    is then the lesser evil — a delivery is never dropped over framing.
    """
    if message.rendered is None:
        logger.warning("message %s arrived without a rendered envelope", message.id)
        return message.body
    return message.rendered


def _tool_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,  # stdout is the protocol channel and must stay clean
        format="courtyard-adapter %(levelname)s: %(message)s",
    )
    # Claude Code keeps this stderr per session; one line per heartbeat would bury the
    # entries that matter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"courtyard-adapter: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    CourtyardAdapter(config).run()


if __name__ == "__main__":
    cli()
