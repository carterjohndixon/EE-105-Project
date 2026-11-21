"""Compile and upload Arduino sketches from Python, using arduino-cli.

Students never call this module directly; the notebooks use
``ee105.setup()``, ``ee105.connect()`` and the ``%%arduino`` cell magic.

What it does
------------
* Finds an ``arduino-cli`` program: one already installed (on the PATH, or
  bundled inside the Arduino IDE 2), or downloads its own copy into
  ``~/.ee105/bin`` the first time.
* Installs the board package for the Nano 33 BLE (``arduino:mbed_nano``) once.
* Finds the board's USB port, then compiles and uploads a sketch folder.
"""
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

FQBN = "arduino:mbed_nano:nano33ble"     # Nano 33 BLE and Nano 33 BLE Sense
CORE = "arduino:mbed_nano"
CLI_VERSION = "1.1.1"
HOME = Path(os.environ.get("EE105_HOME", Path.home() / ".ee105"))
BIN = HOME / "bin"
ARDUINO_VID = 0x2341                       # USB vendor ID of Arduino boards

_cli_cache = None


# ----------------------------------------------------------------- messages
def _say(msg, ok=None):
    mark = {True: "[ok] ", False: "[!!] ", None: "     "}[ok]
    print(mark + msg, flush=True)


# --------------------------------------------------------- find / install CLI
def _exe(name):
    return name + (".exe" if os.name == "nt" else "")


def _ide_cli_candidates():
    """arduino-cli bundled inside an Arduino IDE 2 installation."""
    rel = Path("resources/app/lib/backend/resources") / _exe("arduino-cli")
    if sys.platform == "darwin":
        return [Path("/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"),
                Path.home() / "Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"]
    if os.name == "nt":
        roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramFiles(x86)", "")]
        return [Path(r) / "Programs" / "Arduino IDE" / rel for r in roots if r] + \
               [Path(r) / "Arduino IDE" / rel for r in roots if r]
    return [Path("/opt/arduino-ide") / rel, Path.home() / "arduino-ide" / rel]


def find_cli():
    """Path of a working arduino-cli, or None."""
    global _cli_cache
    if _cli_cache and Path(_cli_cache).exists():
        return _cli_cache
    cands = []
    if os.environ.get("EE105_ARDUINO_CLI"):
        cands.append(Path(os.environ["EE105_ARDUINO_CLI"]))
    cands.append(BIN / _exe("arduino-cli"))
    w = shutil.which("arduino-cli")
    if w:
        cands.append(Path(w))
    cands += _ide_cli_candidates()
    for c in cands:
        if c and Path(c).is_file():
            _cli_cache = str(c)
            return _cli_cache
    return None


def _cli_asset():
    machine = platform.machine().lower()
    if os.name == "nt":
        return f"arduino-cli_{CLI_VERSION}_Windows_64bit.zip"
    if sys.platform == "darwin":
        arch = "ARM64" if machine in ("arm64", "aarch64") else "64bit"
        return f"arduino-cli_{CLI_VERSION}_macOS_{arch}.tar.gz"
    arch = {"x86_64": "64bit", "amd64": "64bit", "aarch64": "ARM64", "arm64": "ARM64",
            "armv7l": "ARMv7"}.get(machine, "64bit")
    return f"arduino-cli_{CLI_VERSION}_Linux_{arch}.tar.gz"


def install_cli():
    """Download arduino-cli into ~/.ee105/bin (about 25 MB, once)."""
    asset = _cli_asset()
    urls = [f"https://github.com/arduino/arduino-cli/releases/download/v{CLI_VERSION}/{asset}",
            f"https://downloads.arduino.cc/arduino-cli/{asset}"]
    BIN.mkdir(parents=True, exist_ok=True)
    last = None
    for url in urls:
        try:
            _say(f"Downloading arduino-cli {CLI_VERSION} ...")
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            if asset.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    z.extract(_exe("arduino-cli"), BIN)
            else:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
                    t.extract("arduino-cli", BIN)
            exe = BIN / _exe("arduino-cli")
            exe.chmod(0o755)
            global _cli_cache
            _cli_cache = str(exe)
            return _cli_cache
        except Exception as e:      # try the next mirror
            last = e
    raise RuntimeError(f"Could not download arduino-cli ({last}). Check the internet connection, "
                       "or install the Arduino IDE 2 and run setup() again.")


def cli():
    return find_cli() or install_cli()


def run(args, stream=False, check=True, timeout=None):
    """Run arduino-cli with arguments; returns (returncode, output text)."""
    cmd = [cli()] + list(args)
    if not stream:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        if check and p.returncode != 0:
            raise RuntimeError(out.strip() or f"arduino-cli {' '.join(args)} failed")
        return p.returncode, out
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    for line in p.stdout:
        lines.append(line)
        s = line.rstrip()
        if s and not s.startswith("Downloading index") and "%" not in s[-6:]:
            print("     " + s, flush=True)
    p.wait()
    out = "".join(lines)
    if check and p.returncode != 0:
        raise RuntimeError(out.strip()[-3000:])
    return p.returncode, out


# ------------------------------------------------------------- board package
def core_installed():
    try:
        _, out = run(["core", "list", "--format", "json"])
        data = json.loads(out or "{}")
        plats = data.get("platforms", data) if isinstance(data, dict) else data
        for p in plats or []:
            pid = p.get("id") or p.get("ID") or ""
            if pid == CORE:
                return True
    except Exception:
        pass
    return False


def install_core():
    _say("Installing the Nano 33 BLE board package (about 200 MB, a few minutes, once) ...")
    run(["core", "update-index"], stream=True)
    args = ["core", "install", CORE]
    if os.name == "nt":
        args.append("--run-post-install")   # installs the USB driver; Windows may ask for permission
    run(args, stream=True)


# ------------------------------------------------------------------ ports
def list_ports():
    """[(port, description)] of Arduino boards that are plugged in."""
    found = []
    try:
        from serial.tools import list_ports as lp
        for p in lp.comports():
            if p.vid == ARDUINO_VID or "arduino" in (p.description or "").lower() \
                    or "nano 33" in (p.description or "").lower():
                found.append((p.device, p.description or ""))
    except ImportError:
        pass
    if not found:
        try:
            _, out = run(["board", "list", "--format", "json"], timeout=20)
            data = json.loads(out or "{}")
            items = data.get("detected_ports", data) if isinstance(data, dict) else data
            for item in items or []:
                port = item.get("port", item)
                if item.get("matching_boards") or "usb" in str(port.get("protocol_label", "")).lower():
                    found.append((port.get("address"), port.get("label", "")))
        except Exception:
            pass
    return found


def find_port(wait=0):
    """Port name of the (first) Nano 33 BLE, waiting up to `wait` seconds."""
    t0 = time.time()
    while True:
        ports = list_ports()
        if ports:
            return ports[0][0]
        if time.time() - t0 >= wait:
            return None
        time.sleep(0.5)


# ------------------------------------------------------------ compile/upload
def compile_sketch(sketch_dir, fqbn=FQBN, verbose=False):
    sketch_dir = Path(sketch_dir).resolve()
    _say(f"Compiling {sketch_dir.name} ...")
    t0 = time.time()
    code, out = run(["compile", "--fqbn", fqbn, str(sketch_dir)], check=False)
    if code != 0:
        print(_clean_errors(out))
        raise RuntimeError(f"{sketch_dir.name} did not compile; see the messages above.")
    _say(f"Compiled in {time.time() - t0:.0f} s. " + _size_line(out), ok=True)
    if verbose:
        print(out)
    return out


def upload(sketch_dir, port=None, fqbn=FQBN, compile_first=True):
    """Compile (optional) and upload a sketch folder to the board."""
    from . import board as _board
    sketch_dir = Path(sketch_dir).resolve()
    if compile_first:
        compile_sketch(sketch_dir, fqbn)
    port = port or find_port(wait=5)
    if not port:
        raise RuntimeError("No Arduino found. Plug in the USB cable (a data cable, not charge-only) "
                           "and run the cell again.")
    _board.release_port(port)          # an open notebook connection would block the upload
    before = {p for p, _ in list_ports()}
    _say(f"Uploading to {port} ...")
    for attempt in range(2):
        code, out = run(["upload", "-p", port, "--fqbn", fqbn, str(sketch_dir)], check=False)
        if code == 0:
            break
        # The board sometimes needs a second try right after it re-enumerates.
        time.sleep(2)
        port = find_port(wait=8) or port
    if code != 0:
        print(_clean_errors(out))
        raise RuntimeError("Upload failed. Double-tap the white RESET button on the Nano (the orange LED "
                           "starts pulsing), then run the cell again.")
    _say("Uploaded.", ok=True)
    return _port_after_upload(port, before)


def _port_after_upload(port, before, wait=10):
    """The board's port once the new sketch runs: the same name if it comes back, otherwise a
    port that was not there before (Windows may assign a new COM number)."""
    time.sleep(1.0)
    t0 = time.time()
    while time.time() - t0 < wait:
        now = [p for p, _ in list_ports()]
        if port in now:
            time.sleep(0.5)
            return port
        new = [p for p in now if p not in before]
        if new and time.time() - t0 > 3:
            return new[0]
        time.sleep(0.5)
    return find_port(wait=0) or port


def _size_line(out):
    for line in out.splitlines():
        if line.startswith("Sketch uses"):
            return line.split("(")[0].strip()
    return ""


def _clean_errors(out):
    keep = []
    for line in out.splitlines():
        if "error" in line.lower() or line.strip().startswith(("^", "|")) or ".ino:" in line:
            keep.append(line)
    return "\n".join(keep[-40:]) or out[-3000:]


# ------------------------------------------------------------------- setup
def ensure_pyserial():
    try:
        import serial  # noqa: F401
        return True
    except ImportError:
        _say("Installing pyserial ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyserial"])
        import importlib
        importlib.invalidate_caches()
        return True


PACKAGES = {"numpy": "numpy", "pandas": "pandas", "matplotlib": "matplotlib", "scipy": "scipy",
            "sympy": "sympy", "serial": "pyserial"}


def ensure_packages(packages=None):
    """pip-install any of the course's Python packages that are missing."""
    import importlib
    packages = packages or PACKAGES
    missing = [pip for mod, pip in packages.items() if importlib.util.find_spec(mod) is None]
    if missing:
        _say("Installing " + ", ".join(missing) + " ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + missing)
        importlib.invalidate_caches()
    return True


def install_library(name):
    """Install an Arduino library by name (for example "Arduino_LPS22HB")."""
    if os.environ.get("EE105_SIMULATE") == "1":
        _say(f"Simulator mode: skipping the library {name} (only needed for a real board).", ok=True)
        return
    run(["lib", "update-index"], check=False)
    run(["lib", "install", name], stream=True)
    _say(f"Library {name} installed", ok=True)


def setup(check_board=True):
    """One-time setup. Safe to run again; finished steps are skipped."""
    ensure_packages()
    _say(f"Python {platform.python_version()} with numpy, pandas, matplotlib, scipy, sympy and pyserial",
         ok=True)
    if os.environ.get("EE105_SIMULATE") == "1":
        _say("Simulator mode: skipping the Arduino tools (they are only needed for a real board).", ok=True)
        return
    path = find_cli()
    if not path:
        path = install_cli()
    _, ver = run(["version"])
    _say(f"arduino-cli: {ver.strip().split(' Commit')[0]}", ok=True)
    if not core_installed():
        install_core()
    _say("Nano 33 BLE board package installed", ok=True)
    if check_board:
        port = find_port(wait=2)
        if port:
            _say(f"Board found on {port}", ok=True)
        else:
            _say("No board found yet. Plug in the Nano 33 BLE with a USB data cable.", ok=False)
    _say("Setup complete. Next: board = connect()", ok=True)
