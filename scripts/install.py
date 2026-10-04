#!/usr/bin/env python3
"""Install courtyard as a macOS app, and the commands the app and `make hub-*` share.

Standard library only, so it runs with whatever `python3` the machine has before the
project's own environment exists.

    make install                       # venv, .env, postgres image, a trial start, the app
    make install APP="Courtyard Dev"   # a second, named app for another directory
    make hub-start | hub-stop | hub-restart | hub-status | hub-open
    make uninstall                     # app, .venv and containers gone; data kept
    make uninstall PURGE=1             # ... and the postgres volume and image removed too
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "hub-launch.sh"
APP_SRC = ROOT / "app"
PREBUILT_APP = APP_SRC / "Courtyard.app"  # unpacked from a release by install.sh
SANDBOX = ROOT / "sandbox"
INSTANCE_FILE = SANDBOX / "app-instance"  # the name of the app that controls this directory
PID_FILE = SANDBOX / "hub.pid"  # the hub started without the app (make hub-start, Linux)
PID_LOG = SANDBOX / "hub.log"
DEFAULT_APP = "Courtyard"
REQUIRED_PYTHON = (3, 14)


def say(text: str) -> None:
    print(text, flush=True)


# -- the install summary: every step's verdict, warnings repeated in full at the end ------------

STEPS: list[tuple[str, str, list[str]]] = []  # (label, "OK" | "WARNING", detail lines)


def record(label: str, status: str = "OK", details: list[str] | None = None) -> None:
    STEPS.append((label, status, list(details or [])))


def format_summary(steps: list[tuple[str, str, list[str]]]) -> str:
    width = 60
    rule = "*" * width
    lines = [rule, (" Summary ").center(width, "*")]
    for i, (label, status, details) in enumerate(steps, 1):
        lines.append(f"{i}. {label} - {status}" + (":" if details else ""))
        if details:
            lines.append("--------")
            lines.extend("  " + d for d in details)
            lines.append("--------")
    warnings = sum(1 for _, status, _ in steps if status != "OK")
    lines.append(rule)
    lines.append("no warnings" if not warnings else f"{warnings} warning(s), see above")
    return "\n".join(lines)


def sh(
    cmd: list[str], check: bool = True, quiet: bool = False, **kw
) -> subprocess.CompletedProcess:
    if not quiet:
        say("  $ " + " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, **kw)


def read_env() -> dict[str, str]:
    """The few `.env` values this script needs; a missing file means the defaults."""
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def hub_url() -> str:
    return f"http://127.0.0.1:{read_env().get('COURTYARD_PORT', '2626')}"


def project_version() -> str:
    match = re.search(
        r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.MULTILINE
    )
    return match.group(1) if match else "?"


# -- the app instance: one app per courtyard directory, named at install ------------------------


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True)
class Instance:
    """Where a named app and its files live. "Courtyard" is the default; another name
    gives a second app (its own bundle id, config, socket, logs) for another directory."""

    name: str = DEFAULT_APP
    home: Path = field(default_factory=Path.home)

    @property
    def bundle_id(self) -> str:
        base = "com.courtyard.app"
        return base if self.name == DEFAULT_APP else f"{base}.{slug(self.name)}"

    @property
    def app(self) -> Path:
        return self.home / "Applications" / f"{self.name}.app"

    @property
    def support(self) -> Path:
        return self.home / "Library" / "Application Support" / self.name

    @property
    def config(self) -> Path:
        return self.support / "config.json"

    @property
    def socket(self) -> Path:
        return self.support / "control.sock"

    @property
    def logs(self) -> Path:
        return self.home / "Library" / "Logs" / self.name

    @property
    def hub_log(self) -> Path:
        return self.logs / "hub.log"


def instance(name: str | None = None) -> Instance:
    if name:
        return Instance(name)
    if INSTANCE_FILE.exists():
        return Instance(INSTANCE_FILE.read_text().strip() or DEFAULT_APP)
    return Instance()


def render_config(
    inst: Instance,
    root: Path = ROOT,
    start_hub_with_app: bool = False,
    start_at_login: bool = True,
    editor: str | None = None,
) -> dict:
    return {
        "directory": str(root),
        "start_hub_with_app": start_hub_with_app,
        "start_at_login": start_at_login,
        "editor": editor,
        "bundle_id": inst.bundle_id,
        "name": inst.name,
    }


def read_config(inst: Instance) -> dict:
    try:
        return json.loads(inst.config.read_text())
    except (OSError, ValueError):
        return {}


# -- the app over its control socket -----------------------------------------------------------


def app_call(inst: Instance, command: str, timeout: float = 5.0, **args) -> dict | None:
    """One JSON line to the running app, one back; None when no app answers."""
    if not inst.socket.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(inst.socket))
            s.sendall(json.dumps({"command": command, **args}).encode() + b"\n")
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        return json.loads(buf) if buf.strip() else None
    except (OSError, ValueError):
        return None


def app_owns_this_directory(inst: Instance) -> bool:
    """The running app controls THIS directory (not another checkout's)."""
    reply = app_call(inst, "status")
    if not reply:
        return False
    try:
        return Path(reply.get("directory", "")).resolve() == ROOT.resolve()
    except OSError:
        return False


def wait_for_app(inst: Instance, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if app_call(inst, "status"):
            return True
        time.sleep(0.5)
    return False


# -- the hub without the app: a pid file (make hub-start before an install, Linux) --------------


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(pid_file: Path = PID_FILE) -> int | None:
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None
    if pid_running(pid):
        return pid
    pid_file.unlink(missing_ok=True)
    return None


def pid_start(
    launcher: Path = LAUNCHER, log: Path = PID_LOG, pid_file: Path = PID_FILE, cwd: Path = ROOT
) -> int:
    """Start the launcher detached; it execs the hub, so the pid stays the hub's."""
    log.parent.mkdir(parents=True, exist_ok=True)
    launcher.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "COURTYARD_SUPERVISED"}
    with open(log, "ab") as out:
        proc = subprocess.Popen(
            ["/bin/sh", str(launcher)],
            cwd=cwd,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    pid_file.write_text(f"{proc.pid}\n")
    return proc.pid


def _reap(pid: int) -> None:
    """Collect the exit of a child of this process (a trial start); not ours: nothing."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


def pid_stop(pid_file: Path = PID_FILE, grace: float = 10.0) -> bool:
    """SIGTERM to the hub's process group, SIGKILL after the grace period."""
    pid = read_pid(pid_file)
    if pid is None:
        return False
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pid, sig)
        except PermissionError:
            os.kill(pid, sig)  # a group member we may not signal: the hub itself will do
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait
        _reap(pid)
        while time.monotonic() < deadline and pid_running(pid):
            time.sleep(0.2)
            _reap(pid)
        if not pid_running(pid):
            break
    pid_file.unlink(missing_ok=True)
    return True


# -- the hub's API ---------------------------------------------------------------------------


def health(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def get_json(path: str, timeout: float = 2.0):
    with urllib.request.urlopen(hub_url() + path, timeout=timeout) as resp:
        return json.loads(resp.read())


def post_json(path: str, body: dict | None = None, timeout: float = 30.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        hub_url() + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def _error_code(exc: urllib.error.HTTPError) -> str:
    """The hub's error code out of an HTTP error body, or the status when there is none."""
    try:
        return json.loads(exc.read())["error"]["code"]
    except (ValueError, KeyError, TypeError, OSError):
        return str(exc.code)


def wait_for_hub(seconds: float = 60.0) -> dict | None:
    url = hub_url()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        report = health(url)
        if report:
            return report
        time.sleep(1.0)
    return None


def wait_for_hub_down(seconds: float = 15.0) -> bool:
    url = hub_url()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if health(url) is None:
            return True
        time.sleep(0.5)
    return False


def hub_is_supervised(url: str, timeout: float = 2.0) -> bool | None:
    """Is the hub on `url` a supervised one (the app's), or some other hub on the same
    port? None when nothing answers."""
    try:
        with urllib.request.urlopen(url + "/api/config", timeout=timeout) as resp:
            return bool(json.loads(resp.read()).get("supervised"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def refuse_a_hub_already_on_the_port() -> None:
    """A hub that already answers on the port (a `make run` in some terminal, another
    directory's app) would make ours fail to bind; say so and stop instead."""
    url = hub_url()
    if health(url) is None:
        return
    sys.exit(
        f"a hub already answers at {url} (a `make run` ends with Ctrl+C, `make run-chrome`"
        " with `make run-stop`, an app's hub with its Stop hub). Stop it, or give this"
        " directory its own COURTYARD_PORT in .env, then run make install again."
    )


# -- the WebUI -------------------------------------------------------------------------------

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# where browsers put the WebUI once it is added to the Dock (Chrome, Safari)
WEB_APPS = (
    Path.home() / "Applications" / "Chrome Apps.localized" / "Agent Courtyard.app",
    Path.home() / "Applications" / "Agent Courtyard.app",
)


def installed_dock_app(web_apps=WEB_APPS) -> Path | None:
    for app in web_apps:
        if Path(app).exists():
            return Path(app)
    return None


def webui_command(url: str, web_apps=WEB_APPS, chrome: str = CHROME) -> list[str]:
    """Open the board as its own window, never as a tab with the browser's decorations:
    the installed Dock app when there is one, else Chrome in app mode (what `make
    run-chrome` does), else whatever the default browser makes of the URL."""
    app = installed_dock_app(web_apps)
    if app:
        return ["open", "-a", str(app)]
    if Path(chrome).exists():
        return [chrome, f"--app={url}"]
    return ["open", url]


def open_webui() -> None:
    cmd = webui_command(hub_url())
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def edit_env_command(editor: str | None, env_file: Path = ROOT / ".env") -> list[str]:
    """The editor from the app's settings, else the system's text editor (`open -t`)."""
    if editor:
        return ["open", "-a", editor, str(env_file)]
    return ["open", "-t", str(env_file)]


# -- install steps ---------------------------------------------------------------------------


def check_prerequisites() -> None:
    if sys.platform != "darwin":
        sys.exit("the app install is macOS only (the hub itself runs anywhere with Docker)")
    if shutil.which("docker") is None:
        sys.exit(
            "docker is not on PATH: install Docker Desktop or Colima, set it to start at login"
        )
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        sys.exit("docker is installed but not running: start it (and set it to start at login)")


def python_for_venv() -> str:
    """The interpreter the venv is built from: the pinned major.minor, wherever it is."""
    want = f"python{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
    for candidate in (want, "python3"):
        path = shutil.which(candidate)
        if path is None:
            continue
        version = subprocess.run(
            [path, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        if tuple(int(v) for v in version) >= REQUIRED_PYTHON:
            return path
    sys.exit(
        f"python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} is required (brew install python@3.14)"
    )


def make_venv() -> None:
    say("1. the hub's environment (.venv)")
    if shutil.which("uv"):
        sh(["uv", "sync"], cwd=ROOT)
    else:
        python = python_for_venv()
        if not (ROOT / ".venv").exists():
            sh([python, "-m", "venv", ".venv"], cwd=ROOT)
        sh([str(ROOT / ".venv" / "bin" / "pip"), "install", "-q", "-e", "."], cwd=ROOT)
    record("the hub's environment (.venv)")


# The settings the one-command install takes from the environment and writes into a
# NEW .env, so `curl ... | COURTYARD_COMPOSE_PROJECT=x COURTYARD_PORT=2628 sh` is a
# complete, isolated instance without editing a file by hand. Every other knob stays a
# .env edit. An existing .env is never changed.
ENV_KNOBS = (
    "COURTYARD_COMPOSE_PROJECT",
    "COURTYARD_PG_PORT",
    "COURTYARD_PORT",
    "COURTYARD_ADMINER_PORT",
    "COURTYARD_LOG_LEVEL",
    "COURTYARD_EMBEDDINGS_URL",
    "COURTYARD_EMBEDDINGS_MODEL",
    "COURTYARD_EMBEDDINGS_API_KEY",
    "COURTYARD_EMBEDDINGS_ALLOW_REMOTE",
)


def render_env(template: str, values: dict[str, str]) -> str:
    """`.env.default` with the given settings set: the commented `#KEY=...` line becomes
    `KEY=value` in place, so the file keeps its explanations; a key the template does
    not mention is appended."""
    lines = template.splitlines()
    for key, value in values.items():
        wanted = f"{key}={value}"
        for i, line in enumerate(lines):
            if line.strip().lstrip("#").strip().startswith(f"{key}="):
                lines[i] = wanted
                break
        else:
            lines.append(wanted)
    return "\n".join(lines) + "\n"


def unquote_env_from_dotenv() -> None:
    """`make` exports every .env line as it is, so a value written as KEY="x" reaches
    docker compose and the hub as `"x"` with the quotes. The .env file is the truth for
    this directory: put its values, unquoted, into the environment before anything runs."""
    os.environ.update(read_env())


def env_knobs(environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    return {key: environ[key] for key in ENV_KNOBS if environ.get(key, "").strip()}


def make_env_file() -> None:
    say("2. local settings (.env)")
    target = ROOT / ".env"
    given = env_knobs()
    if target.exists():
        say("  .env exists, kept as is")
        details = [".env existed and was kept as is"]
        if given:
            ignored = ", ".join(f"{k}={v}" for k, v in given.items())
            say(f"  NOT applied (edit .env yourself): {ignored}")
            record(
                "local settings (.env)",
                "WARNING",
                details + [f"from the environment, not applied: {ignored}"],
            )
            return
        record("local settings (.env)", details=details)
    else:
        target.write_text(render_env((ROOT / ".env.default").read_text(), given))
        if given:
            written = ", ".join(f"{k}={v}" for k, v in given.items())
            say(f"  .env created from .env.default with {written}")
            record("local settings (.env)", details=[f"written from the environment: {written}"])
        else:
            say("  .env created from .env.default (edit it for ports, log level, embeddings)")
            record("local settings (.env)")


def project() -> str:
    """The compose project: one per machine by default, so every checkout and install
    shares the same volume; COURTYARD_COMPOSE_PROJECT names an isolated second instance."""
    return read_env().get("COURTYARD_COMPOSE_PROJECT") or os.environ.get(
        "COURTYARD_COMPOSE_PROJECT", "courtyard"
    )


def psql(sql: str) -> str | None:
    """One query against the compose postgres, through the container; None when the hub's
    tables are not there yet (a fresh database) or the container is not answering."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            f"{project()}-postgres",
            "psql",
            "-U",
            "courtyard",
            "-d",
            "courtyard",
            "-tAc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def database_report() -> str:
    """What this install is going to use: a fresh database, or one with a history."""
    counts = psql(
        "SELECT (SELECT count(*) FROM agents WHERE type <> 'human' AND removed_at IS NULL),"
        " (SELECT count(*) FROM messages), (SELECT count(*) FROM memory),"
        " (SELECT coalesce(string_agg(name, ', '), '') FROM teams)"
    )
    if not counts:
        return "fresh courtyard database (nothing registered yet)"
    agents, messages, memory, teams = counts.split("|")
    return describe_database(int(agents), int(messages), int(memory), teams)


def describe_database(agents: int, messages: int, memory: int, teams: str) -> str:
    if not agents and not messages and not memory and not teams:
        return "fresh courtyard database (nothing registered yet)"
    return (
        f"EXISTING courtyard database found and used: {agents} agent(s), {messages} message(s),"
        f" {memory} memory record(s)" + (f", team {teams}" if teams else "")
    )


EXISTING_DATABASE_ADVICE = [
    "One machine, one courtyard database, by design: every checkout and install",
    "shares it. To start from nothing instead: `make db-nuke` here (deletes it),",
    "or give this install its own COURTYARD_COMPOSE_PROJECT, COURTYARD_PG_PORT and",
    "COURTYARD_PORT in .env, then run `make install` again.",
]


def prepare_postgres() -> None:
    say(
        f"3. postgres (docker compose project {project()!r}, host port"
        f" {read_env().get('COURTYARD_PG_PORT', '26432')})"
    )
    sh(["docker", "compose", "up", "-d", "--wait", "postgres"], cwd=ROOT)
    report = database_report()
    say(f"  {report}")
    if report.startswith("EXISTING"):
        details = [report, *EXISTING_DATABASE_ADVICE]
        for line in EXISTING_DATABASE_ADVICE:
            say("  " + line)
        record("postgres", "WARNING", details)
    else:
        record("postgres")


def compose_down(purge: bool = False) -> None:
    cmd = ["docker", "compose", "--profile", "tools", "down"]
    if purge:
        cmd.append("-v")
    sh(cmd, cwd=ROOT, check=False)


def trial_start() -> None:
    """Prove the .env: postgres up, the hub up and answering, both down again."""
    say("4. a trial start of the hub (then stopped)")
    refuse_a_hub_already_on_the_port()
    pid_start()
    report = wait_for_hub()
    url = hub_url()
    pid_stop()
    wait_for_hub_down()
    compose_down()
    if not report:
        sys.exit(f"the hub did not answer at {url} within a minute; see {PID_LOG}")
    say(f"  the hub answered at {url} (status {report.get('status')}, db {report.get('db')})")
    record("a trial start of the hub", details=["the hub started and was stopped again"])


def previous_directory(inst: Instance) -> Path | None:
    """The directory the app of this name already controls, when it is another one."""
    directory = read_config(inst).get("directory")
    if not directory or Path(directory).resolve() == ROOT.resolve():
        return None
    return Path(directory)


def takeover_warning(name: str, old_root: Path) -> list[str]:
    return [
        f"{name} already existed and controlled {old_root};",
        "it now controls this directory instead (that directory's files are untouched).",
        "Both share the same database unless their .env files say otherwise.",
    ]


def build_app(inst: Instance) -> Path:
    """The app bundle in ~/Applications: built from app/ by swiftc, or the release's
    prebuilt bundle (default name only) when the Command Line Tools are missing."""
    inst.app.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("swiftc"):
        sh(
            [
                "/bin/sh",
                str(APP_SRC / "build.sh"),
                str(inst.app),
                inst.bundle_id,
                inst.name,
                project_version(),
            ],
            cwd=ROOT,
        )
        return inst.app
    if PREBUILT_APP.exists():
        if inst.name != DEFAULT_APP:
            sys.exit(
                f"a named app ({inst.name}) needs swiftc to build; install the Command Line"
                " Tools (xcode-select --install) or use the default name"
            )
        shutil.rmtree(inst.app, ignore_errors=True)
        shutil.copytree(PREBUILT_APP, inst.app, symlinks=True)
        return inst.app
    sys.exit(
        "swiftc not found: install the Command Line Tools (xcode-select --install), or use"
        " install.sh, which brings the built app from the release"
    )


def write_app(inst: Instance) -> None:
    say(f"5. the app: ~/Applications/{inst.name}.app, its settings and the login item")
    old_root = previous_directory(inst)
    if old_root:
        for line in takeover_warning(inst.name, old_root):
            say("  " + line)
        record("the app", "WARNING", takeover_warning(inst.name, old_root))
    else:
        record("the app")
    if app_call(inst, "status") is not None:
        app_call(inst, "quit", timeout=30.0)
        time.sleep(1)
    build_app(inst)
    inst.support.mkdir(parents=True, exist_ok=True)
    inst.logs.mkdir(parents=True, exist_ok=True)
    kept = read_config(inst)
    inst.config.write_text(
        json.dumps(
            render_config(
                inst,
                start_hub_with_app=bool(kept.get("start_hub_with_app", False)),
                start_at_login=bool(kept.get("start_at_login", True)),
                editor=kept.get("editor"),
            ),
            indent=2,
        )
        + "\n"
    )
    SANDBOX.mkdir(parents=True, exist_ok=True)
    INSTANCE_FILE.write_text(inst.name + "\n")
    say(f"  wrote {inst.app}")
    say(f"  wrote {inst.config} (the app starts at login; the hub starts from its menu)")


def ask_keep_hub() -> bool:
    """The one question of the install, read from the terminal (stdin may be the script
    under `curl | sh`); KEEP_HUB=1 or 0 answers it without asking."""
    given = os.environ.get("KEEP_HUB", "").strip()
    if given:
        return given == "1"
    try:
        with open("/dev/tty") as tty:
            print("  Keep the hub running? [y/N] ", end="", flush=True)
            return tty.readline().strip().lower() in ("y", "yes")
    except OSError:
        return False


def launch_app(inst: Instance) -> bool:
    sh(["open", "-a", str(inst.app)])
    return wait_for_app(inst)


def install(app_name: str | None) -> None:
    inst = instance(app_name or DEFAULT_APP)
    check_prerequisites()
    make_venv()
    make_env_file()
    prepare_postgres()
    trial_start()
    write_app(inst)
    say("6. starting the app")
    keep = ask_keep_hub()
    if not launch_app(inst):
        record("starting the app", "WARNING", [f"the app did not answer; see {inst.logs}"])
    elif keep:
        app_call(inst, "start")
        report = wait_for_hub()
        if report:
            say(f"  hub up at {hub_url()} (status {report.get('status')}, db {report.get('db')})")
            record("starting the app", details=["the hub is running under the app"])
        else:
            record("starting the app", "WARNING", [f"the hub did not answer; see {inst.hub_log}"])
    else:
        say("  the app is in the menu bar; the hub is down until Start hub")
        record("starting the app", details=["the hub is down until Start hub"])
    say("")
    say(format_summary(STEPS))
    say("")
    say(f"Done. {inst.name} is in the menu bar and starts at login: Open WebUI, Start / Stop /")
    say("Restart hub, Start / End shift, Show hub log, Edit .env, Settings, About, Quit.")
    say(f"Logs: {inst.hub_log}")
    say("make hub-status | hub-stop | hub-start | hub-restart | hub-open ; make uninstall")


# -- the shared commands: the app's menu and make hub-* run these ----------------------------


def supervisor(inst: Instance) -> str:
    """Who runs the hub here: `app`, `pid` (started without the app) or `none`."""
    if app_owns_this_directory(inst):
        return "app"
    if read_pid() is not None:
        return "pid"
    return "none"


def start() -> None:
    inst = instance()
    url = hub_url()
    if health(url):
        say(f"the hub is already up at {url}")
        return
    if app_owns_this_directory(inst):
        reply = app_call(inst, "start") or {}
        if not reply.get("ok", True):
            sys.exit(f"the app refused: {reply.get('error', 'unknown')}")
    else:
        pid_start()
        say(f"  started without the app (pid {read_pid()}, log {PID_LOG})")
    report = wait_for_hub()
    say(f"hub {'up' if report else 'did not answer in time, see the log'} at {url}")


def stop() -> None:
    inst = instance()
    if app_owns_this_directory(inst):
        app_call(inst, "stop", timeout=30.0)
    elif read_pid() is not None:
        pid_stop()
    else:
        other = " (something else answers on the port)" if health(hub_url()) else ""
        say(f"the hub is not running from here{other}")
        return
    say("hub stopped" if wait_for_hub_down() else "the hub did not stop in time")


def restart() -> None:
    inst = instance()
    if app_owns_this_directory(inst):
        app_call(inst, "restart", timeout=30.0)
    else:
        if read_pid() is not None:
            pid_stop()
            wait_for_hub_down()
            pid_start()
    report = wait_for_hub()
    say(f"hub {'up' if report else 'did not answer in time, see the log'} at {hub_url()}")


def status_report() -> dict:
    """Everything the menu shows, in one answer."""
    inst = instance()
    url = hub_url()
    report = {
        "directory": str(ROOT),
        "url": url,
        "app": inst.name,
        "version": project_version(),
        "supervisor": supervisor(inst),
        "hub": "down",
        "db": None,
        "shift": "off",
        "stale": False,
        "pending": 0,
    }
    h = health(url)
    if not h:
        return report
    report["hub"] = "up"
    report["db"] = h.get("db")
    try:
        report["pending"] = len(get_json("/api/gate/pending"))
        shift = get_json("/api/shift")
        report["shift"] = shift.get("state", "off")
        report["stale"] = bool(shift.get("stale"))
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        pass
    return report


def status(as_json: bool) -> None:
    report = status_report()
    if as_json:
        print(json.dumps(report))
        return
    inst = instance()
    running = "running" if app_call(inst, "status") else "not running"
    say(f"directory  : {report['directory']}")
    say(f"app        : {inst.name} ({running})")
    say(f"supervisor : {report['supervisor']}")
    up = f"up (db {report['db']})" if report["hub"] == "up" else "down"
    say(f"hub        : {report['url']} {up}")
    if report["hub"] == "up":
        say(f"shift      : {report['shift']}" + (" (nobody home)" if report["stale"] else ""))
        say(f"gate       : {report['pending']} waiting")


def shift_start() -> None:
    print(json.dumps(post_json("/api/shift/start")))


def shift_end(force: bool, keep_terminals: bool) -> None:
    """Exit 0 with the status, or exit 3 with the hub's error code (`shift_busy` means
    the caller should ask and retry with --force)."""
    body = {"force": force, "keep_terminals": keep_terminals}
    try:
        print(json.dumps(post_json("/api/shift/end", body)))
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error": _error_code(exc)}))
        sys.exit(3)


# -- uninstall ---------------------------------------------------------------------------------


def disconnect_agents() -> list[str] | None:
    """Take the courtyard files out of every registered agent's directory, through the hub:
    it holds the directories and does the file work (the same call as the WebUI's "take the
    files out"). Registrations and the charter stay, so a later install plus a charter load
    connects the directories again. One line per agent; None when the hub does not answer."""
    url = hub_url()
    try:
        with urllib.request.urlopen(url + "/api/agents", timeout=3) as resp:
            agents = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    lines = []
    for a in sorted(agents, key=lambda a: a["name"]):
        if (
            a.get("removed_at")
            or a.get("type") not in ("claude-code", "pi")
            or not a.get("workdir")
        ):
            continue
        name, workdir = a["name"], a["workdir"]
        req = urllib.request.Request(
            f"{url}/api/agents/{urllib.parse.quote(name)}/disconnect",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                lines.append(f"{name}: files taken out of {workdir}")
        except urllib.error.HTTPError as exc:
            code = _error_code(exc)
            if code == "nothing_to_disconnect":
                lines.append(f"{name}: nothing to take out of {workdir}")
            else:
                lines.append(f"{name}: NOT cleaned, {workdir} ({code})")
        except (urllib.error.URLError, OSError) as exc:
            lines.append(f"{name}: NOT cleaned, {workdir} ({exc})")
    return lines


def hub_up_for_uninstall(inst: Instance) -> bool:
    """The disconnect step needs the hub: start it when it is down (Docker permitting)."""
    if health(hub_url()):
        return True
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        return False
    if app_owns_this_directory(inst):
        app_call(inst, "start")
    else:
        try:
            sh(["docker", "compose", "up", "-d", "--wait", "postgres"], cwd=ROOT, quiet=True)
            pid_start()
        except (OSError, subprocess.CalledProcessError):
            return False
    return wait_for_hub(90.0) is not None


def quit_app(inst: Instance, unregister_login_item: bool = False) -> None:
    """Ask the app to quit (its hub stops with it); for an uninstall the app also drops
    its login item first, so it is launched for that when it is not running."""
    if app_call(inst, "status") is None and unregister_login_item and inst.app.exists():
        sh(["open", "-a", str(inst.app)], check=False, quiet=True)
        wait_for_app(inst)
    if app_call(inst, "status") is not None:
        app_call(inst, "quit", timeout=30.0, unregister_login_item=unregister_login_item)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and app_call(inst, "status") is not None:
            time.sleep(0.5)


def uninstall(purge: bool) -> None:
    inst = instance()
    say("1. the agents' project directories: taking the courtyard files out")
    outcome = disconnect_agents() if hub_up_for_uninstall(inst) else None
    if outcome is None:
        say("  the hub could not be started (Docker?), so no directory was cleaned. Each")
        say("  agent's directory holds .mcp.json, .claude/settings.local.json and")
        say("  start-with-courtyard.sh; to clean them: make hub-start, then per agent")
        say("  .venv/bin/courtyard-invite --name <agent> --disconnect")
    elif not outcome:
        say("  no registered agent has a project directory")
    else:
        for line in outcome:
            say("  " + line)
    say(f"2. the app ({inst.name}), its login item, settings and logs")
    quit_app(inst, unregister_login_item=True)
    if read_pid() is not None:
        pid_stop()
    for path in (inst.app, inst.support, inst.logs):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            say(f"  removed {path}")
    INSTANCE_FILE.unlink(missing_ok=True)
    PID_FILE.unlink(missing_ok=True)
    say("3. containers" + (" and the data volume" if purge else " (data volume kept)"))
    compose_down(purge)
    if purge:
        sh(
            ["docker", "image", "rm", "pgvector/pgvector:pg18", "adminer:latest"],
            check=False,
            capture_output=True,
        )
    say("4. the environment (.venv)")
    shutil.rmtree(ROOT / ".venv", ignore_errors=True)
    say("")
    say(
        "Uninstalled. Kept: this directory, .env, sandbox/"
        + ("" if purge else ", the postgres data volume")
    )
    say("Remove the Dock app by dragging it out of the Dock (Safari) or from chrome://apps.")


# -- main ------------------------------------------------------------------------------------


def main() -> None:
    unquote_env_from_dotenv()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inst = sub.add_parser("install")
    inst.add_argument("--app", default=None, help="the app's name (default: Courtyard)")
    un = sub.add_parser("uninstall")
    un.add_argument(
        "--purge", action="store_true", help="also remove the postgres volume and images"
    )
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true", help="one JSON object (what the app reads)")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("open")
    sub.add_parser("edit-env")
    sub.add_parser("shift-start")
    se = sub.add_parser("shift-end")
    se.add_argument("--force", action="store_true")
    se.add_argument("--keep-terminals", action="store_true")
    args = parser.parse_args()
    if args.command == "install":
        install(args.app)
    elif args.command == "uninstall":
        uninstall(args.purge)
    elif args.command == "status":
        status(args.json)
    elif args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "restart":
        restart()
    elif args.command == "open":
        open_webui()
    elif args.command == "edit-env":
        subprocess.Popen(edit_env_command(read_config(instance()).get("editor")))
    elif args.command == "shift-start":
        shift_start()
    elif args.command == "shift-end":
        shift_end(args.force, args.keep_terminals)


if __name__ == "__main__":
    main()
