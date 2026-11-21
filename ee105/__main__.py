"""Command line entry of the toolkit, used by the setup files.

    python -m ee105 setup      install arduino-cli and the Nano 33 BLE board package (once)
    python -m ee105 version    print the toolkit version
"""
import sys


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "setup":
        from . import arduino
        try:
            arduino.setup(check_board=False)
        except Exception as e:                 # a clear message for the setup log, not a traceback
            print(f"[!!] Arduino tools: {e}")
            return 1
        return 0
    if cmd == "version":
        from . import __version__
        print(__version__)
        return 0
    print(__doc__)
    return 0 if cmd == "help" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
