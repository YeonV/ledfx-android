#!/usr/bin/env python3
"""
Live dev harness for ledfx-android.

Iterating on missing/broken Python dependencies through CI costs ~40 minutes a
round. A *debug* APK is debuggable, so `run-as` can read and write the app's
private files - including the unpacked Python bundle. That turns the loop into
seconds: drop a module in, restart the service, read the next traceback.

Requires a debug APK (the one WITHOUT `-release` in the name). Release builds
are not debuggable and `run-as` will refuse.

    python androdev.py status
    python androdev.py logs
    python androdev.py push audio-hotplug aiosendspin
    python androdev.py stub psutil mss
    python androdev.py cycle          # restart, wait, report next error

Wheels are fetched straight from the PyPI JSON API rather than via pip, because
pip applies *this* machine's interpreter constraints. The APK runs Python 3.14
on Android; several LedFx deps still declare `<3.14` or ship no Android wheel,
and pip would refuse to download them even though the pure-python code is fine.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

PKG = "com.ledfx.ledfx"
SERVICE = f"{PKG}:service_ledfx"
BUNDLE = "files/app/_python_bundle/site-packages"
DEVICE_TMP = "/data/local/tmp/androdev"


# --------------------------------------------------------------------------- adb


def find_adb() -> str:
    if os.environ.get("ANDRODEV_ADB"):
        return os.environ["ANDRODEV_ADB"]
    found = shutil.which("adb")
    if found:
        # Reject ancient builds: wireless pairing needs platform-tools >= 30.
        try:
            out = subprocess.run([found, "version"], capture_output=True, text=True).stdout
            m = re.search(r"Version (\d+)\.", out)
            if m and int(m.group(1)) >= 30:
                return found
        except Exception:
            pass
    for guess in (
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
    ):
        if os.path.isfile(guess):
            return guess
    if found:
        return found
    sys.exit("adb not found. Set ANDRODEV_ADB to a platform-tools >= 30 adb binary.")


ADB = find_adb()
_DEVICE: str | None = None


def device() -> str:
    """Pick a serial explicitly.

    A wirelessly-paired phone often shows up twice - once by ip:port and once by
    mDNS name - and every bare adb call then fails with 'more than one device'.
    """
    global _DEVICE
    if _DEVICE:
        return _DEVICE
    if os.environ.get("ANDRODEV_SERIAL"):
        _DEVICE = os.environ["ANDRODEV_SERIAL"]
        return _DEVICE
    out = subprocess.run([ADB, "devices"], capture_output=True, text=True).stdout
    serials = [
        line.split()[0]
        for line in out.splitlines()[1:]
        if line.strip() and line.split()[-1] == "device"
    ]
    if not serials:
        sys.exit("No device. Try: adb connect <ip>:<port>   (pair first on Android 11+)")
    # Prefer the ip:port transport; it survives mDNS flapping.
    serials.sort(key=lambda s: (":" not in s, s))
    _DEVICE = serials[0]
    return _DEVICE


def adb(*args: str, check: bool = False) -> str:
    res = subprocess.run(
        [ADB, "-s", device(), *args], capture_output=True, text=True
    )
    if check and res.returncode != 0:
        sys.exit(f"adb {' '.join(args)} failed:\n{res.stderr or res.stdout}")
    return (res.stdout or "") + (res.stderr or "")


def runas(cmd: str, check: bool = False) -> str:
    out = adb("shell", f"run-as {PKG} {cmd}", check=check)
    if "package not debuggable" in out:
        sys.exit(
            "This build is not debuggable.\n"
            "Install the APK *without* '-release' in the filename, e.g.\n"
            "  LedFx_CC-v2.1.6-b21--android-arm64-v8a.apk"
        )
    return out


# ------------------------------------------------------------------------- pypi


def wheel_url(spec: str) -> tuple[str, str]:
    """Resolve a pure-python wheel URL, ignoring requires_python."""
    name, _, want = spec.partition("==")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as r:
        data = json.load(r)
    version = want or data["info"]["version"]
    files = data["releases"].get(version) or []
    for f in files:
        if f["filename"].endswith(("py3-none-any.whl", "py2.py3-none-any.whl")):
            return f["url"], f["filename"]
    natives = [f["filename"] for f in files if f["filename"].endswith(".whl")]
    raise SystemExit(
        f"{name} {version} has no pure-python wheel"
        + (f" (native only: {natives[0]} ...)" if natives else "")
        + "\nNative deps cannot be side-loaded; they need a p4a recipe and a real build."
    )


# ----------------------------------------------------------------- push to device


def push_tree(local_dir: str) -> None:
    """Tar a directory over and unpack it into site-packages."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for entry in sorted(os.listdir(local_dir)):
            tar.add(os.path.join(local_dir, entry), arcname=entry)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp_path = tmp.name
    try:
        adb("shell", f"mkdir -p {DEVICE_TMP}", check=True)
        adb("push", tmp_path, f"{DEVICE_TMP}/payload.tar", check=True)
        adb("shell", f"chmod 644 {DEVICE_TMP}/payload.tar")
        out = runas(f"sh -c 'cd {BUNDLE} && tar xf {DEVICE_TMP}/payload.tar'")
        if out.strip():
            print("   ", out.strip())
    finally:
        os.unlink(tmp_path)


# -------------------------------------------------------------------- commands


def cmd_status(_args) -> None:
    print(f"adb    : {ADB}")
    print(f"device : {device()}")
    ver = re.search(r"versionName=(\S+)", adb("shell", f"dumpsys package {PKG}"))
    print(f"version: {ver.group(1) if ver else '<not installed>'}")
    dbg = "yes" if "package not debuggable" not in adb(
        "shell", f"run-as {PKG} true"
    ) else "NO - install the non-release APK"
    print(f"debuggable: {dbg}")
    ps = adb("shell", "ps -A")
    print(f"activity: {'up' if f' {PKG}' in ps else 'down'}")
    print(f"service : {'up' if SERVICE in ps else 'DOWN'}")


def cmd_push(args) -> None:
    for spec in args.packages:
        url, fname = wheel_url(spec)
        print(f"-> {spec}: {fname}")
        with urllib.request.urlopen(url, timeout=120) as r:
            blob = r.read()
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                z.extractall(tmp)
            tops = sorted({n.split("/")[0] for n in os.listdir(tmp)})
            print(f"   contains: {', '.join(tops)}")
            push_tree(tmp)
        print("   installed")


def cmd_stub(args) -> None:
    """Fake a module to find out whether an import is actually load-bearing."""
    with tempfile.TemporaryDirectory() as tmp:
        for mod in args.modules:
            path = os.path.join(tmp, f"{mod}.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    f'"""androdev stub for {mod} - not the real package."""\n'
                    "class _Stub:\n"
                    "    def __init__(self, *a, **k): pass\n"
                    "    def __call__(self, *a, **k): return _Stub()\n"
                    "    def __getattr__(self, name): return _Stub()\n"
                    "    def __iter__(self): return iter(())\n"
                    "    def __bool__(self): return False\n"
                    "def __getattr__(name): return _Stub()\n"
                )
            print(f"-> stub {mod}")
        push_tree(tmp)
    print("   installed")


def cmd_restart(_args) -> None:
    adb("shell", f"am force-stop {PKG}")
    time.sleep(1)
    adb("shell", f"monkey -p {PKG} -c android.intent.category.LAUNCHER 1")
    print("restarted")


def service_pid() -> str | None:
    for line in adb("shell", "ps -A").splitlines():
        if SERVICE in line:
            return line.split()[1]
    return None


def cmd_logs(args) -> None:
    pid = service_pid()
    if not pid:
        print("service not running; showing whole buffer")
        out = adb("logcat", "-d", "-t", str(args.lines))
        out = "\n".join(l for l in out.splitlines() if "ledfx" in l or "python" in l)
    else:
        out = adb("logcat", "-d", f"--pid={pid}", "-t", str(args.lines))
    print(out.strip() or "<empty>")


def cmd_cycle(args) -> None:
    """Restart and report the outcome: serving, or the next traceback."""
    adb("logcat", "-c")
    cmd_restart(args)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        time.sleep(2)
        log = adb("logcat", "-d")
        if "ModuleNotFoundError" in log or "Traceback (most recent call last)" in log:
            lines = [
                l for l in log.splitlines()
                if any(k in l for k in ("ledfx", "python")) and "WebViewLoader" not in l
            ]
            tail = lines[-25:]
            print("\n".join(tail))
            miss = re.findall(r"ModuleNotFoundError: No module named '([^']+)'", log)
            if miss:
                print(f"\n>>> MISSING: {miss[-1]}")
                print(f">>> try: python androdev.py push {miss[-1].replace('_', '-')}")
                print(f">>>  or: python androdev.py stub {miss[-1]}")
            return
        if SERVICE in adb("shell", "ps -A") and "8888" in adb(
            "shell", "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"
        ).replace("22B8", "8888"):
            print(">>> LedFx is listening on 8888 - it booted.")
            print(">>> confirm with: python androdev.py api")
            return
    print(f">>> no traceback and not serving after {args.timeout}s; run 'logs' for detail")


def cmd_api(args) -> None:
    """Talk to the running LedFx over an adb port-forward.

    The definitive proof of life: the service process can be up while LedFx
    itself is wedged, and the device has no curl to check from the inside.
    """
    adb("forward", f"tcp:{args.port}", "tcp:8888", check=True)
    base = f"http://localhost:{args.port}"
    for path in args.endpoints:
        url = base + path
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                body = json.dumps(json.loads(body), indent=2)[:1200]
            except Exception:
                body = body[:400]
            print(f"--- {path} ---\n{body}\n")
        except Exception as exc:
            print(f"--- {path} ---\nFAILED: {exc}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="device, version, debuggable, processes").set_defaults(func=cmd_status)

    sp = sub.add_parser("push", help="install pure-python wheels into the bundle")
    sp.add_argument("packages", nargs="+", metavar="PKG[==VER]")
    sp.set_defaults(func=cmd_push)

    ss = sub.add_parser("stub", help="fake a module to test whether it is load-bearing")
    ss.add_argument("modules", nargs="+")
    ss.set_defaults(func=cmd_stub)

    sub.add_parser("restart", help="force-stop and relaunch").set_defaults(func=cmd_restart)

    sl = sub.add_parser("logs", help="tail the service process log")
    sl.add_argument("-n", "--lines", type=int, default=200)
    sl.set_defaults(func=cmd_logs)

    sc = sub.add_parser("cycle", help="restart, wait, report next error or success")
    sc.add_argument("--timeout", type=int, default=60)
    sc.set_defaults(func=cmd_cycle)

    sa = sub.add_parser("api", help="query the running LedFx via adb port-forward")
    sa.add_argument("endpoints", nargs="*", default=["/api/info", "/api/audio/devices"])
    sa.add_argument("--port", type=int, default=8899, help="local forwarded port")
    sa.set_defaults(func=cmd_api)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
