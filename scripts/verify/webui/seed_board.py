"""Verification fixture: a board worth looking at, for the WebUI procedures.

Those procedures need agents that have talked, a message waiting at the gate and
something that answers the operator. This registers throwaway dummies on a hub of
your choosing, leaves them running, and prints what it made. `--stop` takes the
whole cast off the board again: the dummies are removed, their lines archived and
those throwaway archives deleted.

It refuses the operator's hub (port 2626): the dummies are registrations, and agent
names are permanent. Give it a throwaway hub:

    uv run python .claude/skills/courtyard-testing/scripts/scratch_hub.py start --name webui
    export COURTYARD_HUB_URL=<the printed url>
    uv run python scripts/verify/webui/seed_board.py
    # ... the procedures under "The WebUI" in docs/testing.md ...
    uv run python scripts/verify/webui/seed_board.py --stop

What it leaves on the board:

  · alice ↔ bob    auto-pass, a finished exchange, its thread closed by alice
  · dev ↔ ops      supervised, one message held at the gate, and the pair reacts to
                   your verdict: returned asks again, dropped backs off
  · concierge      an echo dummy, for your own line from the input box
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from courtyard.common.client import HubClient, HubError
from courtyard.common.envfile import load_env_file

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / "sandbox" / "seed-board"
BEHAVIORS = "scripts/verify/webui/behaviors"
OPERATOR_PORT = 2626
OPENING = "Hey bob, the payments service is ready on branch feat/payments. Deploy it to staging?"
GATED_ASK = "I want to run schema migration 0042 on prod tonight, can I go ahead?"


def options() -> tuple[str, bool]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true", help="take the cast off the board")
    parser.add_argument("--hub", help="hub URL (default: COURTYARD_HUB_URL)")
    args = parser.parse_args()
    url = (args.hub or os.environ.get("COURTYARD_HUB_URL", "")).rstrip("/")
    if not url:
        sys.exit("seed_board: no hub; pass --hub or set COURTYARD_HUB_URL")
    if urlsplit(url).port == OPERATOR_PORT:
        sys.exit(f"seed_board: port {OPERATOR_PORT} is the operator's hub; use a throwaway one")
    return url, args.stop


def start_dummy(admin_url: str, name: str, token: str, behavior: str, opening: str = "") -> None:
    cmd = [
        "uv",
        "run",
        "courtyard-dummy",
        "--hub",
        admin_url,
        "--heartbeat",
        "5",
        "--name",
        name,
        "--token",
        token,
        "--behavior",
        behavior,
    ]
    if opening:
        cmd += ["--open", opening]
    log = (STATE / f"{name}.log").open("w")
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    (STATE / f"{name}.pid").write_text(str(proc.pid))


def stop_dummies() -> None:
    """Each dummy is a `uv run` wrapper around a python child; both go."""
    for pid_file in sorted(STATE.glob("*.pid")):
        pid = pid_file.read_text().strip()
        children = subprocess.run(
            ["pgrep", "-P", pid], check=False, capture_output=True, text=True
        ).stdout
        for victim in [pid, *children.split()]:
            subprocess.run(["kill", victim], check=False, capture_output=True)
        pid_file.unlink()


def clear_cast(admin: HubClient) -> int:
    """Remove a previous run's dummies and the archives their removal produced. A hub
    that is already gone took its scratch database with it; then only the local state
    is left to clear."""
    cast_file = STATE / "cast.json"
    if not cast_file.exists():
        return 0
    names = set(json.loads(cast_file.read_text()))
    removed = 0
    try:
        for name in sorted(names):
            try:
                admin.remove_agent(name)
                removed += 1
            except HubError:
                pass  # already gone
        for archive in admin.archives():
            if archive.agent_a_name in names or archive.agent_b_name in names:
                admin.delete_archive(archive.id)
    except httpx.HTTPError:
        print("hub not reachable; its scratch database went with it, local state cleared")
    cast_file.unlink()
    return removed


def record(names: list[str]) -> None:
    (STATE / "cast.json").write_text(json.dumps(names))


def wait_for(predicate, timeout: float, what: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.25)
    sys.exit(f"seed_board: timed out waiting for {what}")


def main() -> None:
    load_env_file(ROOT)
    url, stop = options()
    STATE.mkdir(parents=True, exist_ok=True)
    admin = HubClient(url)

    stop_dummies()
    removed = clear_cast(admin)
    if stop:
        shutil.rmtree(STATE, ignore_errors=True)
        print(f"board cleared: {removed} dummies removed, their archives deleted")
        admin.close()
        return

    if not any(t.is_current for t in admin.teams()):
        sys.exit("seed_board: the hub has no current team; a scratch hub starts with one")

    suffix = secrets.token_hex(2)
    names = {k: f"{k}-{suffix}" for k in ("alice", "bob", "dev", "ops", "concierge")}
    tokens = {}
    cast: list[str] = []
    for key, description in [
        ("alice", "coding agent working on the payments service"),
        ("bob", "infra agent owning the staging and prod clusters"),
        ("dev", "dev dummy asking for risky things"),
        ("ops", "ops dummy guarding prod"),
        ("concierge", "echo dummy that acknowledges everything"),
    ]:
        _, tokens[key] = admin.register_agent(names[key], "dummy", description)
        cast.append(names[key])
        record(cast)  # incrementally: a failed run's partial cast is still cleaned

    # the lines are pre-created and pinned, so the fixture looks the same whatever the
    # hub's discovery mode and default are
    admin.set_mode(admin.link(names["alice"], names["bob"]).id, "auto_pass")
    gate_line = admin.link(names["dev"], names["ops"])
    admin.set_mode(gate_line.id, "supervised")

    start_dummy(url, names["bob"], tokens["bob"], f"script:{BEHAVIORS}/bob.yaml")
    start_dummy(url, names["ops"], tokens["ops"], f"script:{BEHAVIORS}/gated-ops.yaml")
    start_dummy(url, names["concierge"], tokens["concierge"], "echo")
    time.sleep(1.0)  # the listeners must be up before the openers speak
    start_dummy(
        url,
        names["alice"],
        tokens["alice"],
        f"script:{BEHAVIORS}/alice.yaml",
        f"{names['bob']}: {OPENING}",
    )
    start_dummy(
        url,
        names["dev"],
        tokens["dev"],
        f"script:{BEHAVIORS}/gated-dev.yaml",
        f"{names['ops']}: {GATED_ASK}",
    )

    line = wait_for(
        lambda: next(
            (ln for ln in admin.lines() if names["alice"] in (ln.agent_a_name, ln.agent_b_name)),
            None,
        ),
        15,
        "alice's line to appear",
    )
    wait_for(
        lambda: len([m for m in admin.line_messages(line.id) if m.kind == "message"]) >= 6,
        30,
        "the exchange to finish",
    )
    as_alice = HubClient(url, names["alice"], tokens["alice"])
    as_alice.close_thread(names["bob"])
    as_alice.close()
    held = wait_for(
        lambda: [m for m in admin.pending() if m.sender_name == names["dev"]],
        15,
        "the gated ask to reach the gate",
    )

    print(f"""
board seeded on {url}

  {names["alice"]} ↔ {names["bob"]}   auto-pass, {len(admin.line_messages(line.id))} messages, thread closed by alice
  {names["dev"]} ↔ {names["ops"]}   supervised, held at the gate: "{held[0].body[:48]}..."
  {names["concierge"]}   echoes whatever you type in the box

  stop: uv run python scripts/verify/webui/seed_board.py --stop""")
    admin.close()


if __name__ == "__main__":
    main()
