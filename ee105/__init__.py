"""EE 105 lab toolkit: run, upload and test Arduino code from a Jupyter notebook.

Typical first cells of a lab notebook:

    import sys; sys.path.insert(0, "..")    # the ee105 folder sits next to the lab folders
    import ee105
    board = ee105.connect()                  # finds the board; uploads the course firmware if needed

Main tools
----------
ee105.setup()             one-time install of arduino-cli and the Nano 33 BLE board package
                          (the setup files setup-windows.bat / setup-mac.command run it for you)
ee105.connect()           connect to the demo board (simulate=True works without hardware)
board.check_module(2)     warn if the module selector S10 does not read Module 2
board.monitor("circuits") run a command you could type into a serial terminal (see board.COMMANDS)
%%arduino name            cell magic: the cell is an Arduino sketch; compile and upload it
ee105.monitor(5)          Serial Monitor in the notebook (for your own sketches)
ee105.serial_plot(10)     Serial Plotter in the notebook
ee105.record(2)           the numbers your sketch prints, as a table
ee105.live_plot(...)      live plot of any stream of numbers (gauge=..., annotate=...)
ee105.bits_strip(a, b)    the received bits of a LiFi frame as a strip, errors framed
board.sweep(..., live=True)  draw a sweep point by point (also transistor_transfer, transistor_output)
ee105.hw                  pins, DAC channels and unit conversions of the demo board
ee105.running_average(x)  centered running average of a sweep (same length; lowers random noise)
ee105.save_submission()   write the lab's submission file for the course portal
"""
import os
import shlex
from pathlib import Path

from . import arduino
from . import hardware as hw
from .analysis import running_average
from .arduino import setup, compile_sketch, list_ports, install_library
from .board import Board, BoardError, connect, connect_all, release_port
from .live import live_plot, monitor, record, serial_plot, LiveIV, bits_strip
from . import camera, datasets
from .camera import connect_camera
from .submission import save_submission

__version__ = "3.0"
KIT = Path(__file__).resolve().parent.parent


def upload(sketch_folder, port=None):
    """Compile and upload a sketch folder; returns the port."""
    return arduino.upload(sketch_folder, port=port)


def simulate(on=True):
    """Make connect() use the simulated board from now on (True) or the real one (False)."""
    os.environ["EE105_SIMULATE"] = "1" if on else "0"


# ------------------------------------------------------------------ %%arduino
def _arduino_cell(line, cell):
    """%%arduino [name] [--monitor S] [--plot S] [--send TEXT] [--baud B] [--compile]

    The rest of the cell is an Arduino sketch. It is saved as sketches/<name>/<name>.ino
    next to the notebook, compiled, and uploaded to the board. With --monitor S the
    notebook then shows what the sketch prints for S seconds; --plot S plots the numbers
    it prints instead. --compile only checks that the sketch compiles.
    """
    import argparse
    p = argparse.ArgumentParser(prog="%%arduino", add_help=False)
    p.add_argument("name", nargs="?", default="my_sketch")
    p.add_argument("--monitor", "-m", type=float, default=None)
    p.add_argument("--plot", "-p", type=float, default=None)
    p.add_argument("--send", default=None)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--compile", action="store_true")
    p.add_argument("--port", default=None)
    try:
        a = p.parse_args(shlex.split(line))
    except SystemExit:
        print(_arduino_cell.__doc__)
        return
    name = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in a.name)
    folder = Path("sketches") / name
    folder.mkdir(parents=True, exist_ok=True)
    ino = folder / f"{name}.ino"
    ino.write_text(cell, encoding="utf-8")
    if os.environ.get("EE105_SIMULATE") == "1" and not a.compile:
        arduino._say(f"Simulator mode: saved {ino}. Uploading needs a real board, so the sketch "
                     "was not run.", ok=False)
        return
    if a.compile:
        arduino.compile_sketch(folder)
        return
    port = arduino.upload(folder, port=a.port)
    if a.monitor:
        print(f"--- output for {a.monitor:g} s ---")
        monitor(a.monitor, port=port, baud=a.baud, send=a.send)
    elif a.plot:
        return serial_plot(a.plot, port=port, baud=a.baud)


def _register_magics():
    try:
        from IPython import get_ipython
        ip = get_ipython()
    except Exception:
        return
    if ip is None:
        return
    ip.register_magic_function(_arduino_cell, magic_kind="cell", magic_name="arduino")
    try:
        ip.set_custom_exc((NameError, TypeError, ValueError, AttributeError), _error_hint)
    except Exception:
        pass


def _error_hint(shell, etype, evalue, tb, tb_offset=None):
    """Show the usual error, then one line on the two mistakes students make most often:
    running a cell before the earlier steps, and running a cell whose ✍️ lines still hold `...`."""
    shell.showtraceback((etype, evalue, tb), tb_offset=tb_offset)
    msg = str(evalue)
    if "ellipsis" in msg:
        print("\n[!!] A value in this cell is still `...`. Fill the lines marked ✍️ (in this cell or in an "
              "earlier EDIT or ANSWER step; the book shows what to write), run that cell, then this one.")
    elif etype is NameError and "is not defined" in msg:
        name = msg.split("'")[1] if msg.count("'") >= 2 else "a name"
        print(f"\n[!!] `{name}` is made by an earlier step that has not run since the notebook was opened. "
              "Run the cells above in order (Shift+Enter from the top), then this one again.")
    return None


_register_magics()
