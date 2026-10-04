"""`make install` and the commands the Courtyard app shares with `make hub-*`
(scripts/install.py). The install itself touches the operator's machine, so it stays a
manual verification procedure; tested here is everything around it: the app instance's
places, the control-socket client, the pid-file mode, the install and uninstall
contracts, the Makefile and install.sh wrappers."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install

# -- the app instance --------------------------------------------------------------------------


def test_the_default_app_and_a_named_one_live_in_their_own_places(tmp_path):
    default = install.Instance(home=tmp_path)
    assert default.name == "Courtyard"
    assert default.bundle_id == "com.courtyard.app"
    assert default.app == tmp_path / "Applications" / "Courtyard.app"
    support = tmp_path / "Library" / "Application Support" / "Courtyard"
    assert default.config == support / "config.json"
    assert default.socket == support / "control.sock"
    assert default.hub_log == tmp_path / "Library" / "Logs" / "Courtyard" / "hub.log"

    dev = install.Instance("Courtyard Dev", home=tmp_path)
    assert dev.bundle_id == "com.courtyard.app.courtyard-dev"
    assert dev.app == tmp_path / "Applications" / "Courtyard Dev.app"
    assert dev.support != default.support and dev.logs != default.logs
    assert install.slug("My  App (2)!") == "my-app-2"


def test_the_directory_remembers_which_app_controls_it(tmp_path, monkeypatch):
    marker = tmp_path / "sandbox" / "app-instance"
    monkeypatch.setattr(install, "INSTANCE_FILE", marker)
    assert install.instance().name == "Courtyard"  # nothing installed: the default
    marker.parent.mkdir()
    marker.write_text("Courtyard Dev\n")
    assert install.instance().name == "Courtyard Dev"
    assert install.instance("Other").name == "Other"  # an explicit name wins


def test_the_config_names_the_directory_and_the_defaults(tmp_path):
    inst = install.Instance("Courtyard Dev", home=tmp_path)
    config = install.render_config(inst, root=tmp_path / "checkout")
    assert config == {
        "directory": str(tmp_path / "checkout"),
        "start_hub_with_app": False,  # the hub starts from the menu
        "start_at_login": True,  # the app is in the menu bar after a login
        "editor": None,
        "bundle_id": "com.courtyard.app.courtyard-dev",
        "name": "Courtyard Dev",
    }
    assert install.read_config(inst) == {}  # no file yet
    inst.support.mkdir(parents=True)
    inst.config.write_text(json.dumps(config))
    assert install.read_config(inst)["directory"] == str(tmp_path / "checkout")


def test_a_takeover_from_another_directory_is_said(tmp_path):
    inst = install.Instance(home=tmp_path)
    inst.support.mkdir(parents=True)
    assert install.previous_directory(inst) is None  # no config
    inst.config.write_text(json.dumps({"directory": str(install.ROOT)}))
    assert install.previous_directory(inst) is None  # this directory: a reinstall
    other = tmp_path / "elsewhere"
    inst.config.write_text(json.dumps({"directory": str(other)}))
    assert install.previous_directory(inst) == other
    warning = install.takeover_warning("Courtyard", other)
    assert str(other) in warning[0] and "now controls this directory" in warning[1]


# -- the control socket ------------------------------------------------------------------------


class FakeApp:
    """What the Swift app does on its socket: one JSON line in, one out."""

    def __init__(self, path: Path, directory: str):
        self.path, self.directory, self.commands = path, directory, []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(4)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                request = json.loads(conn.makefile("rb").readline())
                self.commands.append(request["command"])
                reply = {"ok": True, "directory": self.directory, "hub": "down"}
                conn.sendall(json.dumps(reply).encode() + b"\n")

    def close(self):
        self.server.close()


@pytest.fixture
def short_home():
    """A home directory with a short path: AF_UNIX socket paths are limited to about 100
    bytes, and pytest's tmp_path is longer than that."""
    home = Path(tempfile.mkdtemp(prefix="cy-", dir="/tmp"))
    try:
        yield home
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_the_socket_client_talks_to_a_running_app_and_knows_whose_it_is(short_home):
    tmp_path = short_home
    inst = install.Instance(home=tmp_path)
    assert install.app_call(inst, "status") is None  # no socket: no app
    inst.support.mkdir(parents=True)
    app = FakeApp(inst.socket, str(install.ROOT))
    try:
        assert install.app_call(inst, "status")["directory"] == str(install.ROOT)
        assert install.app_owns_this_directory(inst)
        install.app_call(inst, "quit", unregister_login_item=True)
        assert app.commands == ["status", "status", "quit"]
    finally:
        app.close()
    other = install.Instance("Other", home=tmp_path)
    other.support.mkdir(parents=True)
    app = FakeApp(other.socket, str(tmp_path / "another-checkout"))
    try:
        assert install.app_call(other, "status") is not None
        assert not install.app_owns_this_directory(other)  # someone else's checkout
    finally:
        app.close()


def test_a_dead_socket_file_counts_as_no_app(short_home):
    tmp_path = short_home
    inst = install.Instance(home=tmp_path)
    inst.support.mkdir(parents=True)
    inst.socket.touch()  # left behind by a crash: not a listening socket
    assert install.app_call(inst, "status") is None
    assert install.supervisor(inst) in ("none", "pid")


# -- the hub without the app: the pid file ---------------------------------------------------


def test_pid_mode_starts_the_launcher_detached_and_stops_its_process_group(tmp_path):
    launcher = tmp_path / "launch.sh"
    launcher.write_text("#!/bin/sh\necho started\nexec sleep 60\n")
    log, pid_file = tmp_path / "hub.log", tmp_path / "hub.pid"
    pid = install.pid_start(launcher=launcher, log=log, pid_file=pid_file, cwd=tmp_path)
    try:
        assert install.read_pid(pid_file) == pid
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "started" not in log.read_text():
            time.sleep(0.1)
        assert "started" in log.read_text()
        assert install.pid_stop(pid_file, grace=2.0)
        assert install.read_pid(pid_file) is None and not pid_file.exists()
        assert not install.pid_running(pid)
    finally:
        if install.pid_running(pid):
            os.killpg(pid, 9)
    assert install.pid_stop(pid_file) is False  # nothing to stop


def test_a_stale_pid_file_is_cleaned_up(tmp_path):
    pid_file = tmp_path / "hub.pid"
    pid_file.write_text("999999999\n")
    assert install.read_pid(pid_file) is None
    assert not pid_file.exists()
    pid_file.write_text("not a pid\n")
    assert install.read_pid(pid_file) is None


def test_pid_mode_never_claims_to_be_supervised(tmp_path, monkeypatch):
    """A hub started without the app must refuse the WebUI's restart button: nobody
    would start it again."""
    monkeypatch.setenv("COURTYARD_SUPERVISED", "courtyard-app")
    launcher = tmp_path / "launch.sh"
    launcher.write_text("#!/bin/sh\nenv | grep -c COURTYARD_SUPERVISED || echo none\n")
    log, pid_file = tmp_path / "hub.log", tmp_path / "hub.pid"
    install.pid_start(launcher=launcher, log=log, pid_file=pid_file, cwd=tmp_path)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not log.read_text().strip():
        time.sleep(0.1)
    assert log.read_text().strip().endswith("none")


# -- the launcher ----------------------------------------------------------------------------


def test_launcher_sets_path_loads_env_waits_for_docker_and_execs_the_venv_hub():
    text = (ROOT / "scripts" / "hub-launch.sh").read_text()
    assert "/opt/homebrew/bin" in text and "/usr/local/bin" in text  # the app's PATH is bare
    assert ". ./.env" in text
    assert "docker info" in text and "docker compose up -d --wait postgres" in text
    assert "exec .venv/bin/courtyard-hub" in text  # no uv needed at runtime
    if shutil.which("sh"):
        assert (
            subprocess.run(
                ["sh", "-n", str(ROOT / "scripts" / "hub-launch.sh")], check=False
            ).returncode
            == 0
        )


def test_install_script_is_standard_library_only():
    """It runs with the machine's python3 before the venv exists."""
    text = (ROOT / "scripts" / "install.py").read_text()
    for third_party in ("import httpx", "import psycopg", "import fastapi", "from courtyard"):
        assert third_party not in text


def test_env_file_parser_reads_the_port(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "ROOT", tmp_path)
    assert install.hub_url() == "http://127.0.0.1:2626"
    (tmp_path / ".env").write_text(
        "# comment\nCOURTYARD_PORT=2727\nCOURTYARD_LOG_LEVEL='WARNING'\n"
    )
    assert install.read_env() == {"COURTYARD_PORT": "2727", "COURTYARD_LOG_LEVEL": "WARNING"}
    assert install.hub_url() == "http://127.0.0.1:2727"


def test_the_version_comes_from_pyproject():
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        assert install.project_version() == tomllib.load(f)["project"]["version"]


# -- status, the menu's one read -------------------------------------------------------------


def test_status_without_an_install_or_a_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "INSTANCE_FILE", tmp_path / "app-instance")
    monkeypatch.setattr(install, "PID_FILE", tmp_path / "hub.pid")
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install, "app_call", lambda inst, command, timeout=5.0, **a: None)
    report = install.status_report()
    assert report["hub"] == "down" and report["supervisor"] == "none"
    assert report["app"] == "Courtyard" and report["directory"] == str(install.ROOT)
    assert report["version"] == install.project_version()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "install.py"), "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert set(json.loads(result.stdout)) >= {"hub", "shift", "pending", "supervisor", "url"}


def test_status_reads_the_shift_and_the_gate_from_a_live_hub(monkeypatch):
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: {"status": "ok", "db": "ok"})
    monkeypatch.setattr(install, "supervisor", lambda inst: "app")
    answers = {"/api/gate/pending": [1, 2], "/api/shift": {"state": "on", "stale": True}}
    monkeypatch.setattr(install, "get_json", lambda path, timeout=2.0: answers[path])
    report = install.status_report()
    assert (report["hub"], report["db"], report["pending"]) == ("up", "ok", 2)
    assert report["shift"] == "on" and report["stale"] is True


# -- the WebUI and .env ------------------------------------------------------------------------


def test_the_webui_opens_as_its_own_window(tmp_path):
    """The Dock app when it was added, else Chrome in app mode, else the default browser."""
    url = "http://127.0.0.1:2626"
    no_chrome = str(tmp_path / "no-chrome")
    assert install.webui_command(url, web_apps=(), chrome=no_chrome) == ["open", url]
    chrome = tmp_path / "Chrome"
    chrome.write_text("")
    assert install.webui_command(url, web_apps=(), chrome=str(chrome)) == [
        str(chrome),
        f"--app={url}",
    ]
    dock_app = tmp_path / "Agent Courtyard.app"
    dock_app.mkdir()
    assert install.webui_command(url, web_apps=(dock_app,), chrome=str(chrome)) == [
        "open",
        "-a",
        str(dock_app),
    ]


def test_edit_env_uses_the_chosen_editor_or_the_system_text_editor(tmp_path):
    env = tmp_path / ".env"
    assert install.edit_env_command(None, env) == ["open", "-t", str(env)]
    assert install.edit_env_command("Visual Studio Code", env) == [
        "open",
        "-a",
        "Visual Studio Code",
        str(env),
    ]


def test_install_opens_the_dock_app_when_it_is_already_installed(tmp_path):
    app = tmp_path / "Agent Courtyard.app"
    assert install.installed_dock_app(web_apps=(app,)) is None
    app.mkdir()
    assert install.installed_dock_app(web_apps=(app,)) == app


# -- the install's contract --------------------------------------------------------------------


def test_the_summary_lists_every_step_and_repeats_warnings_in_full():
    steps = [
        ("the hub's environment (.venv)", "OK", []),
        ("local settings (.env)", "OK", [".env existed and was kept as is"]),
        (
            "postgres",
            "WARNING",
            ["EXISTING courtyard database found and used: 3 agent(s)", "shared"],
        ),
        ("the app", "OK", []),
    ]
    text = install.format_summary(steps)
    lines = text.splitlines()
    assert lines[0] == "*" * 60 and "Summary" in lines[1]
    assert "1. the hub's environment (.venv) - OK" in lines
    assert "2. local settings (.env) - OK:" in lines
    assert "3. postgres - WARNING:" in lines
    assert "  EXISTING courtyard database found and used: 3 agent(s)" in lines
    assert lines.count("--------") == 4  # one block around each step's details
    assert lines[-1] == "1 warning(s), see above"
    assert install.format_summary([("postgres", "OK", [])]).endswith("no warnings")


def test_install_says_which_database_it_found():
    assert (
        install.describe_database(0, 0, 0, "")
        == "fresh courtyard database (nothing registered yet)"
    )
    assert (
        install.describe_database(3, 20, 2, "vvk-devops-team")
        == "EXISTING courtyard database found and used: 3 agent(s), 20 message(s),"
        " 2 memory record(s), team vvk-devops-team"
    )


def test_install_records_the_existing_database_as_a_warning(monkeypatch):
    monkeypatch.setattr(install, "STEPS", [])
    monkeypatch.setattr(install, "sh", lambda *a, **k: None)
    monkeypatch.setattr(install, "read_env", dict)
    monkeypatch.setattr(install, "database_report", lambda: install.describe_database(3, 0, 0, "t"))
    install.prepare_postgres()
    monkeypatch.setattr(install, "database_report", lambda: install.describe_database(0, 0, 0, ""))
    install.prepare_postgres()
    (label, status, details), (_, fresh, _) = install.STEPS
    assert (label, status, fresh) == ("postgres", "WARNING", "OK")
    assert details[0].startswith("EXISTING courtyard database") and "make db-nuke" in "\n".join(
        details
    )


def test_the_trial_start_proves_the_env_and_leaves_nothing_running(monkeypatch):
    """Step 4: the launcher up, the hub answering, the hub stopped, postgres down; a hub
    that never answers ends the install with the log's path."""
    calls = []
    monkeypatch.setattr(install, "STEPS", [])
    monkeypatch.setattr(install, "refuse_a_hub_already_on_the_port", lambda: calls.append("refuse"))
    monkeypatch.setattr(install, "pid_start", lambda: calls.append("start") or 1)
    monkeypatch.setattr(install, "wait_for_hub", lambda seconds=60.0: {"status": "ok", "db": "ok"})
    monkeypatch.setattr(install, "pid_stop", lambda: calls.append("stop") or True)
    monkeypatch.setattr(install, "wait_for_hub_down", lambda seconds=15.0: True)
    monkeypatch.setattr(install, "compose_down", lambda purge=False: calls.append("down"))
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    install.trial_start()
    assert calls == ["refuse", "start", "stop", "down"]
    assert install.STEPS[-1][:2] == ("a trial start of the hub", "OK")

    monkeypatch.setattr(install, "wait_for_hub", lambda seconds=60.0: None)
    with pytest.raises(SystemExit, match="did not answer"):
        install.trial_start()
    assert calls[-2:] == ["stop", "down"]  # cleaned up before giving up


def test_install_refuses_a_hub_already_on_the_port(monkeypatch):
    """A `make run` hub or another app's hub on the port would make the trial start fail
    to bind; the install says so and stops."""
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: None)
    install.refuse_a_hub_already_on_the_port()  # nothing there: fine
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: {"status": "ok"})
    with pytest.raises(SystemExit, match="already answers"):
        install.refuse_a_hub_already_on_the_port()


def test_the_keep_hub_question_is_answered_by_the_environment(monkeypatch):
    monkeypatch.setenv("KEEP_HUB", "1")
    assert install.ask_keep_hub() is True
    monkeypatch.setenv("KEEP_HUB", "0")
    assert install.ask_keep_hub() is False


def test_write_app_builds_the_bundle_writes_the_config_and_marks_the_directory(
    tmp_path, monkeypatch
):
    inst = install.Instance("Courtyard Dev", home=tmp_path)
    marker = tmp_path / "sandbox" / "app-instance"
    monkeypatch.setattr(install, "STEPS", [])
    monkeypatch.setattr(install, "INSTANCE_FILE", marker)
    monkeypatch.setattr(install, "SANDBOX", marker.parent)
    monkeypatch.setattr(install, "app_call", lambda inst, command, timeout=5.0, **a: None)
    built = []
    monkeypatch.setattr(install, "build_app", lambda inst: built.append(inst.app) or inst.app)
    install.write_app(inst)
    assert built == [inst.app]
    config = json.loads(inst.config.read_text())
    assert config["directory"] == str(install.ROOT) and config["name"] == "Courtyard Dev"
    assert config["start_hub_with_app"] is False and config["start_at_login"] is True
    assert marker.read_text().strip() == "Courtyard Dev"
    assert inst.logs.is_dir()
    assert install.STEPS[-1][:2] == ("the app", "OK")

    # a reinstall keeps the operator's settings and warns when the app controlled another directory
    inst.config.write_text(
        json.dumps(
            {"directory": str(tmp_path / "old"), "start_hub_with_app": True, "editor": "Zed"}
        )
    )
    install.write_app(inst)
    config = json.loads(inst.config.read_text())
    assert config["start_hub_with_app"] is True and config["editor"] == "Zed"
    assert config["directory"] == str(install.ROOT)
    assert install.STEPS[-1][1] == "WARNING" and str(tmp_path / "old") in install.STEPS[-1][2][0]


def test_build_app_needs_swiftc_or_the_prebuilt_bundle(tmp_path, monkeypatch):
    inst = install.Instance(home=tmp_path)
    monkeypatch.setattr(install.shutil, "which", lambda name: None)
    monkeypatch.setattr(install, "PREBUILT_APP", tmp_path / "no-such.app")
    with pytest.raises(SystemExit, match="swiftc not found"):
        install.build_app(inst)
    prebuilt = tmp_path / "Courtyard.app"
    (prebuilt / "Contents").mkdir(parents=True)
    (prebuilt / "Contents" / "Info.plist").write_text("<plist/>")
    monkeypatch.setattr(install, "PREBUILT_APP", prebuilt)
    assert install.build_app(inst) == inst.app
    assert (inst.app / "Contents" / "Info.plist").exists()
    with pytest.raises(SystemExit, match="needs swiftc"):
        install.build_app(install.Instance("Courtyard Dev", home=tmp_path))


# -- the shared commands -----------------------------------------------------------------------


def test_start_goes_through_the_app_when_it_owns_the_directory(monkeypatch, capsys):
    inst = install.Instance()
    sent = []
    monkeypatch.setattr(install, "instance", lambda name=None: inst)
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: None)
    monkeypatch.setattr(install, "app_owns_this_directory", lambda inst: True)
    monkeypatch.setattr(
        install,
        "app_call",
        lambda inst, command, timeout=5.0, **a: sent.append(command) or {"ok": True},
    )
    monkeypatch.setattr(install, "wait_for_hub", lambda seconds=60.0: {"status": "ok"})
    monkeypatch.setattr(install, "wait_for_hub_down", lambda seconds=15.0: True)
    monkeypatch.setattr(install, "pid_start", lambda: pytest.fail("pid mode used with an app"))
    install.start()
    assert sent == ["start"] and "hub up" in capsys.readouterr().out
    install.stop()
    install.restart()
    assert sent == ["start", "stop", "restart"]


def test_start_falls_back_to_the_pid_file_without_the_app(monkeypatch, capsys):
    inst = install.Instance()
    calls = []
    monkeypatch.setattr(install, "instance", lambda name=None: inst)
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: None)
    monkeypatch.setattr(install, "app_owns_this_directory", lambda inst: False)
    monkeypatch.setattr(install, "pid_start", lambda: calls.append("start") or 42)
    monkeypatch.setattr(install, "read_pid", lambda pid_file=None: 42)
    monkeypatch.setattr(install, "pid_stop", lambda pid_file=None, grace=10.0: calls.append("stop"))
    monkeypatch.setattr(install, "wait_for_hub", lambda seconds=60.0: {"status": "ok"})
    monkeypatch.setattr(install, "wait_for_hub_down", lambda seconds=15.0: True)
    install.start()
    assert calls == ["start"] and "without the app" in capsys.readouterr().out
    install.stop()
    assert calls == ["start", "stop"]
    install.restart()
    assert calls == ["start", "stop", "stop", "start"]


def test_start_does_nothing_when_a_hub_is_already_up(monkeypatch, capsys):
    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install, "health", lambda url, timeout=2.0: {"status": "ok"})
    monkeypatch.setattr(install, "pid_start", lambda: pytest.fail("started twice"))
    install.start()
    assert "already up" in capsys.readouterr().out


# -- uninstall -------------------------------------------------------------------------------


def test_uninstall_takes_the_files_out_of_every_agent_directory(monkeypatch):
    """Uninstall step 1: every registered claude-code or pi agent with a directory is
    disconnected through the hub (the files leave, the registration stays); a directory
    with nothing of ours in it is reported, a failure is reported as NOT cleaned, and other
    agent types are skipped."""
    import io
    import urllib.error

    agents = [
        {"name": "scout", "type": "claude-code", "workdir": "/w/scout", "removed_at": None},
        {"name": "bare", "type": "claude-code", "workdir": "/w/bare", "removed_at": None},
        {"name": "pi-1", "type": "pi", "workdir": "/w/pi", "removed_at": None},
        {"name": "gone", "type": "claude-code", "workdir": "/w/gone", "removed_at": "2026-01-01"},
        {"name": "dummy", "type": "dummy", "workdir": "/w/dummy", "removed_at": None},
        {"name": "nodir", "type": "claude-code", "workdir": None, "removed_at": None},
    ]
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/api/agents"):
            return Resp(json.dumps(agents).encode())
        calls.append(url)
        if "/bare/" in url:
            body = io.BytesIO(json.dumps({"error": {"code": "nothing_to_disconnect"}}).encode())
            raise urllib.error.HTTPError(url, 404, "nothing", {}, body)
        if "/pi-1/" in url:
            raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b"not json"))
        return Resp(b"{}")

    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install.urllib.request, "urlopen", fake_urlopen)
    lines = install.disconnect_agents()
    assert lines == [
        "bare: nothing to take out of /w/bare",
        "pi-1: NOT cleaned, /w/pi (500)",
        "scout: files taken out of /w/scout",
    ]
    assert [c.rsplit("/", 2)[1] for c in calls] == ["bare", "pi-1", "scout"]


def test_uninstall_says_so_when_the_hub_does_not_answer(monkeypatch):
    import urllib.error

    def down(*a, **k):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(install, "hub_url", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(install.urllib.request, "urlopen", down)
    assert install.disconnect_agents() is None


def test_uninstall_removes_the_app_its_files_and_the_marker_in_order(tmp_path, monkeypatch):
    """The hub is brought up for the disconnect, the app quits (and drops its login item),
    then the bundle, the settings, the logs, the pid and the marker go, then the
    containers and .venv."""
    inst = install.Instance("Courtyard Dev", home=tmp_path)
    for path in (inst.app / "Contents", inst.support, inst.logs):
        path.mkdir(parents=True)
    marker = tmp_path / "sandbox" / "app-instance"
    marker.parent.mkdir()
    marker.write_text("Courtyard Dev\n")
    pid_file = tmp_path / "sandbox" / "hub.pid"
    calls = []
    monkeypatch.setattr(install, "ROOT", tmp_path / "checkout")
    (tmp_path / "checkout" / ".venv").mkdir(parents=True)
    monkeypatch.setattr(install, "instance", lambda name=None: inst)  # never the real home
    monkeypatch.setattr(install, "INSTANCE_FILE", marker)
    monkeypatch.setattr(install, "PID_FILE", pid_file)
    monkeypatch.setattr(
        install, "hub_up_for_uninstall", lambda inst: calls.append("hub-up") or True
    )
    monkeypatch.setattr(install, "disconnect_agents", lambda: calls.append("disconnect") or [])
    monkeypatch.setattr(install, "farewell", lambda: calls.append("farewell"))
    monkeypatch.setattr(
        install,
        "quit_app",
        lambda inst, unregister_login_item=False: calls.append(f"quit:{unregister_login_item}"),
    )
    monkeypatch.setattr(install, "read_pid", lambda pid_file=None: None)
    monkeypatch.setattr(install, "compose_down", lambda purge=False: calls.append(f"down:{purge}"))
    monkeypatch.setattr(install, "sh", lambda *a, **k: calls.append(a[0][:3]))
    install.uninstall(purge=True)
    assert calls[:5] == ["hub-up", "disconnect", "farewell", "quit:True", "down:True"]
    assert calls[5] == ["docker", "image", "rm"]
    assert not inst.app.exists() and not inst.support.exists() and not inst.logs.exists()
    assert not marker.exists() and not (tmp_path / "checkout" / ".venv").exists()


# -- the wrappers: Makefile, install.sh, the release ------------------------------------------


def test_purge_means_exactly_purge_equals_1():
    makefile = (ROOT / "Makefile").read_text()
    assert "$(if $(filter 1,$(PURGE)),--purge)" in makefile  # PURGE=0 must not purge


def test_make_install_passes_the_app_name_through():
    if shutil.which("make") is None:
        pytest.skip("make is not installed")

    def dry_run(*args):
        return subprocess.run(
            ["make", "-n", "install", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout

    assert "--app" not in dry_run()
    assert '--app "Courtyard Dev"' in dry_run("APP=Courtyard Dev")


def test_a_new_env_file_takes_the_knobs_from_the_environment(tmp_path, monkeypatch):
    """`curl ... | COURTYARD_COMPOSE_PROJECT=x COURTYARD_PORT=2628 sh`: the settings land
    in the new .env in place of the template's commented lines; an existing .env is kept
    and the install says what it did not apply."""
    template = (
        "# the port\n#COURTYARD_PORT=2626\n# the project\n#COURTYARD_COMPOSE_PROJECT=courtyard\n"
    )
    rendered = install.render_env(
        template, {"COURTYARD_PORT": "2628", "COURTYARD_EMBEDDINGS_URL": "http://x"}
    )
    assert rendered == (
        "# the port\nCOURTYARD_PORT=2628\n# the project\n#COURTYARD_COMPOSE_PROJECT=courtyard\n"
        "COURTYARD_EMBEDDINGS_URL=http://x\n"
    )
    assert install.env_knobs(
        {"COURTYARD_PORT": "2628", "HOME": "/x", "COURTYARD_PG_PORT": " "}
    ) == {"COURTYARD_PORT": "2628"}
    monkeypatch.setattr(install, "ROOT", tmp_path)
    monkeypatch.setattr(install, "STEPS", [])
    (tmp_path / ".env.default").write_text(template)
    monkeypatch.setenv("COURTYARD_PORT", "2628")
    install.make_env_file()
    assert "COURTYARD_PORT=2628" in (tmp_path / ".env").read_text()
    assert install.STEPS[-1][1] == "OK" and "2628" in install.STEPS[-1][2][0]
    monkeypatch.setenv("COURTYARD_PORT", "2629")
    install.make_env_file()
    assert "COURTYARD_PORT=2628" in (tmp_path / ".env").read_text()  # kept
    assert install.STEPS[-1][1] == "WARNING" and "not applied" in install.STEPS[-1][2][1]


def test_quoted_dotenv_values_reach_subprocesses_bare(tmp_path, monkeypatch):
    """make exports `KEY="x"` with the quotes; the install script puts the .env values,
    unquoted, into its own environment first (seen live: container name `"vvk"-postgres`)."""
    monkeypatch.setattr(install, "ROOT", tmp_path)
    (tmp_path / ".env").write_text('COURTYARD_COMPOSE_PROJECT="vvk"\nCOURTYARD_PORT=2627\n')
    monkeypatch.setenv("COURTYARD_COMPOSE_PROJECT", '"vvk"')
    install.unquote_env_from_dotenv()
    assert os.environ["COURTYARD_COMPOSE_PROJECT"] == "vvk"
    assert install.project() == "vvk"


@pytest.mark.skipif(sys.platform != "darwin", reason="install.sh refuses anything but macOS")
@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="needs the git checkout (not the zip)")
def test_install_sh_unpacks_a_zip_package_into_an_empty_directory(tmp_path):
    """The one-command install, minus the download and the install itself: a zip from
    `make zip-package` lands flattened in the target directory, dotfiles included, the
    development-only paths left out by `.gitattributes`; a non-empty directory is refused."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    made = subprocess.run(
        [
            "git",
            "archive",
            "--worktree-attributes",  # the checkout's .gitattributes, committed or not
            "--format=zip",
            "--prefix=courtyard-test/",
            "-o",
            str(zip_dir / "c.zip"),
            "HEAD",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert made.returncode == 0, made.stderr
    target = tmp_path / "install-here"
    env = {
        **os.environ,
        "COURTYARD_ZIP": str(zip_dir / "c.zip"),
        "COURTYARD_DIR": str(target),
        "COURTYARD_UNPACK_ONLY": "1",
    }
    run = subprocess.run(
        ["sh", str(ROOT / "install.sh")], env=env, capture_output=True, text=True, check=False
    )
    if "docker is" in run.stderr or "python 3.14" in run.stderr:
        pytest.skip(f"prerequisite missing on this machine: {run.stderr.strip()}")
    assert run.returncode == 0, run.stderr
    assert f"unpacked into {target}" in run.stdout
    # files at HEAD (the archive is of the commit, so nothing uncommitted can be expected)
    for present in ("Makefile", ".env.default", ".python-version", "tests", "webui"):
        assert (target / present).exists(), present
    for absent in (".github", ".claude", ".gitattributes"):
        assert not (target / absent).exists(), absent
    assert not (target / "courtyard-test").exists()  # flattened

    again = subprocess.run(
        ["sh", str(ROOT / "install.sh")], env=env, capture_output=True, text=True, check=False
    )
    assert again.returncode != 0 and "is not empty" in again.stderr

    # a .env written ahead of the install (and Finder's .DS_Store) does not make the
    # directory "not empty": make install keeps an existing .env, so this is how settings
    # are given before the one-liner runs
    with_env = tmp_path / "with-env"
    with_env.mkdir()
    (with_env / ".env").write_text("COURTYARD_PORT=2628\n")
    (with_env / ".DS_Store").write_bytes(b"")
    run = subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        env={**env, "COURTYARD_DIR": str(with_env)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert "keeping the .env" in run.stdout
    assert (with_env / ".env").read_text() == "COURTYARD_PORT=2628\n"
    assert (with_env / "Makefile").exists()


@pytest.mark.skipif(
    not (ROOT / ".github").exists(), reason=".github is export-ignored: absent from the zip"
)
def test_release_workflow_publishes_the_zip_package_and_the_app():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "make zip-package" in text and "courtyard.zip" in text and "gh release create" in text
    assert 'tags: ["v*"]' in text
    assert (
        "macos" in text and "Courtyard.app" in text
    )  # the prebuilt app, for installs without swiftc


# -- the app bundle ----------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit: the app builds on macOS only")
@pytest.mark.skipif(shutil.which("swiftc") is None, reason="swiftc (Command Line Tools) missing")
def test_the_app_builds_into_a_signed_bundle_with_the_instance_name(tmp_path):
    """app/build.sh: a bundle whose Info.plist carries the instance's id and name, the
    executable always `Courtyard`, an icon from the WebUI's PNG, ad-hoc signed."""
    bundle = tmp_path / "Courtyard Dev.app"
    run = subprocess.run(
        [
            "sh",
            str(ROOT / "app" / "build.sh"),
            str(bundle),
            "com.courtyard.app.courtyard-dev",
            "Courtyard Dev",
            "9.9.9",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    import plistlib

    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "com.courtyard.app.courtyard-dev"
    assert info["CFBundleName"] == "Courtyard Dev" and info["CFBundleExecutable"] == "Courtyard"
    assert info["CFBundleShortVersionString"] == "9.9.9" and info["LSUIElement"] is True
    assert os.access(bundle / "Contents" / "MacOS" / "Courtyard", os.X_OK)
    assert (bundle / "Contents" / "Resources" / "menu-icon.png").exists()
    signed = subprocess.run(
        ["codesign", "-dv", str(bundle)], capture_output=True, text=True, check=False
    )
    assert "Signature=adhoc" in signed.stderr
