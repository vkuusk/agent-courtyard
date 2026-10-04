"""Verification: the Courtyard app's lifetime over its control socket.

Builds the app from app/ (swiftc), runs it with a scratch HOME pointed at THIS checkout
(its .env, its ports, its compose project), and drives it the way scripts/install.py
does: status, a bad command, start (the hub answers and says it is supervised), stop
(the hub is down, postgres still up), quit (`docker compose down`, the socket gone, the
app exited). Nothing is written outside the scratch home; the app's login item is off.

Needs swiftc (the Command Line Tools) and Docker running. Stops any hub already on this
checkout's port first (`make run-stop`, `make hub-stop`). Run:
    uv run python scripts/verify/app/app_lifecycle.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import install


def hr(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def check(label, ok):
    print(("  OK   " if ok else "  FAIL ") + label)
    return ok


def main() -> int:
    if shutil.which("swiftc") is None:
        print("swiftc not found: install the Command Line Tools (xcode-select --install)")
        return 2
    url = install.hub_url()
    if install.health(url):
        print(f"a hub already answers at {url}: stop it first (make run-stop / make hub-stop)")
        return 2
    results = []
    # a short path: AF_UNIX socket paths are limited to about 100 bytes
    home = Path(tempfile.mkdtemp(prefix="cy-", dir="/tmp"))
    app_proc = None
    try:
        hr("1. build the app")
        bundle = home / "Courtyard.app"
        built = subprocess.run(
            [
                "sh",
                str(ROOT / "app" / "build.sh"),
                str(bundle),
                "com.courtyard.app",
                "Courtyard",
                "0.0.0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        print(built.stdout.strip() or built.stderr.strip())
        if not check("built", built.returncode == 0):
            return 1

        hr("2. a scratch home pointed at this checkout")
        inst = install.Instance(home=home)
        inst.support.mkdir(parents=True)
        config = install.render_config(inst, root=ROOT, start_at_login=False)
        inst.config.write_text(__import__("json").dumps(config))
        # the docker CLI finds its compose plugin under $HOME/.docker
        os.symlink(Path.home() / ".docker", home / ".docker")
        app_proc = subprocess.Popen(
            [str(bundle / "Contents" / "MacOS" / "Courtyard")],
            env={**os.environ, "HOME": str(home)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        results.append(check("the app answers on its socket", install.wait_for_app(inst, 15)))
        reply = install.app_call(inst, "status") or {}
        results.append(check("status names this directory", reply.get("directory") == str(ROOT)))
        results.append(check("hub is down", reply.get("hub") == "down"))
        bad = install.app_call(inst, "bogus") or {}
        results.append(check("a bad command is refused", bad.get("ok") is False))

        hr("3. start: the hub comes up, supervised")
        install.app_call(inst, "start")
        report = install.wait_for_hub(90)
        results.append(check(f"the hub answers at {url}", bool(report)))
        results.append(check("it says it is supervised", install.hub_is_supervised(url) is True))
        results.append(
            check("app.log says hub started", "hub started" in (inst.logs / "app.log").read_text())
        )

        hr("4. stop: the hub is down, postgres stays")
        install.app_call(inst, "stop", timeout=30)
        results.append(check("the hub is down", install.wait_for_hub_down(30)))
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
        )
        results.append(check("postgres still up", f"{install.project()}-postgres" in ps.stdout))

        hr("5. quit: compose down, socket gone, app exited")
        install.app_call(inst, "quit", timeout=30)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and app_proc.poll() is None:
            time.sleep(0.5)
        results.append(check("the app exited", app_proc.poll() is not None))
        results.append(check("the socket is gone", not inst.socket.exists()))
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
        )
        results.append(check("postgres down", f"{install.project()}-postgres" not in ps.stdout))
        print("\napp.log:")
        print((inst.logs / "app.log").read_text())
    finally:
        if app_proc and app_proc.poll() is None:
            app_proc.kill()
        shutil.rmtree(home, ignore_errors=True)
    hr("RESULT: " + ("PASS" if all(results) else "FAIL"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
