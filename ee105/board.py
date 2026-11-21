"""Talk to the EE 105 demo board from a notebook.

    from ee105 import connect
    board = connect()                    # finds the board, uploads the firmware if needed
    data = board.read(pin=1, n=1000, interval_ms=1)
    board.set_dac(0, 1.2)                # 1.2 V on DAC channel 0

Every method returns plain numbers, numpy arrays or pandas DataFrames, so the
data goes straight into your analysis: no copying from a Serial Monitor.
"""
import time
from pathlib import Path

import numpy as np

from . import arduino, hardware as hw

FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware" / "ee105_board"
FIRMWARE_NAME = "ee105"
FIRMWARE_VERSION = "3.2"
BAUD = 115200

_open_boards = []          # every Board that is currently open (so uploads can release the port)

# Commands you can type (board.monitor("circuits")); the old names still work on the board.
COMMANDS = {
    "help": "list of commands",
    "module": "which selector position is active (A7)",
    "circuits": "touch-panel button pressed and its node voltage (S10 on Module 1, J7/J8 caps on the Module 1 end)",
    "divider": "voltage at the divider output A1 (S10 on Module 1, J7/J8 caps on the Module 1 end)",
    "temperature": "thermistor temperature from the divider on A1 (S10 on Module 1, J7/J8 caps on the Module 1 end)",
    "diodes": "diode I-V sweep: V_DAC, V_D, I_D in mA (S10 on Module 2)",
    "transistors": "MOSFET output curves: V_GS, V_DS, I_D in mA (S10 on Module 2)",
    "transfer": "MOSFET transfer curve at V_DAC2 = 3.3 V: V_GS, V_DS, I_D in mA (S10 on Module 2)",
    "light": "LED pair 1 on, photodiode reading (S10 on Module 3, J5 on P1-A)",
    "sensors": "red and infrared PPG (S10 on Module 3)",
    "communications send <text>": "send text over light on the TX LED, pair 2 (S10 on Module 3)",
    "communications receive": "print the text received by the RX photodiode (S10 on Module 3, J5 on A-P2)",
    "stop": "stop the running command",
}
OLD_NAMES = {"m1na": "circuits", "m1vd": "divider", "m2d": "diodes", "m2draw": "diodes",
             "m2tran_vds": "transistors", "m2tran_vgs": "transfer", "m3pdcurrent": "light",
             "show_pd": "light", "m3led": "light", "m3stepled": "light", "m3ppg": "sensors",
             "lifi_tx": "communications send", "lifi_rx": "communications receive"}


class BoardError(RuntimeError):
    """The board answered with an error (#err ...)."""


def release_port(port=None):
    """Close any open notebook connection (to `port`, or all)."""
    for b in list(_open_boards):
        if port is None or b.port == port:
            b.close()


class Result:
    """Parsed reply: `cols` (names), `data` (2-D numpy array), `meta` (dict of #key value lines)."""

    def __init__(self, cols, data, meta, lines):
        self.cols, self.data, self.meta, self.lines = cols, data, meta, lines

    def column(self, name):
        return self.data[:, self.cols.index(name)]

    def frame(self):
        import pandas as pd
        return pd.DataFrame(self.data, columns=self.cols)

    def __repr__(self):
        return f"Result(cols={self.cols}, rows={len(self.data)}, meta={self.meta})"


class Board:
    """A connection to the demo board running the ee105 firmware.

    Use `connect()` rather than creating a Board yourself.
    """
    FW_NAME, FW_VERSION, FW_DIR, KIND = FIRMWARE_NAME, FIRMWARE_VERSION, FIRMWARE_DIR, "demo board"

    def __init__(self, port, serial_obj=None, baud=BAUD):
        self.port = port
        self.simulated = serial_obj is not None and getattr(serial_obj, "simulated", False)
        self.sim = serial_obj.model if self.simulated else None   # the simulated hardware (press keys etc.)
        self._pending = None
        self._buf = b""
        self.info = {"firmware": None, "device_id": None}   # filled in by firmware()
        if serial_obj is None:
            import serial
            for attempt in range(6):          # the port can take a moment to appear after a reset
                try:
                    serial_obj = serial.Serial(port, baud, timeout=0.2, write_timeout=2)
                    break
                except serial.SerialException as e:
                    if attempt == 5:
                        raise RuntimeError(f"Could not open {port}: {e}. If another program (Arduino IDE, "
                                           "another notebook) is using the board, close it and try again.")
                    time.sleep(0.5)
        self._ser = serial_obj
        _open_boards.append(self)
        time.sleep(0.05 if self.simulated else 0.3)
        self._drain()

    # ------------------------------------------------------------ plumbing
    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass
        if self in _open_boards:
            _open_boards.remove(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        kind = "simulated board" if self.simulated else f"board on {self.port}"
        return f"<EE 105 {kind}>"

    @property
    def is_open(self):
        return bool(getattr(self._ser, "is_open", False))

    def _drain(self):
        """Throw away anything waiting in the input buffer."""
        self._buf = b""
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass

    def _write(self, text):
        if not self.is_open:
            raise BoardError("The board connection is closed. Run board = connect() again.")
        self._ser.write((text.strip() + "\n").encode())
        try:
            self._ser.flush()
        except Exception:
            pass

    def _readline(self):
        """One line of text, or None if nothing arrived within the port timeout."""
        if self.simulated:
            raw = self._ser.readline()
            return raw.decode(errors="replace").strip() if raw else None
        # read in chunks (pyserial's readline reads one byte at a time, which is slow for big replies)
        while True:
            i = self._buf.find(b"\n")
            if i >= 0:
                raw, self._buf = self._buf[:i], self._buf[i + 1:]
                return raw.decode(errors="replace").strip()
            n = self._ser.in_waiting
            chunk = self._ser.read(n if n else 1)
            if not chunk:
                return None
            self._buf += chunk

    def send(self, command):
        """Send a raw text command (for example "communications send Hello")."""
        self._write(command)

    def readline(self, timeout=1.0):
        """One line of text from the board, or None after `timeout` seconds."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self._readline()
            if line is not None:
                return line
        return None

    def query(self, command, timeout=10.0, on_line=None):
        """Send a notebook command and collect the reply until '#done'.

        `timeout` is the longest wait between two lines. Returns a Result.
        """
        self.begin(command)
        return self.finish(timeout=timeout, on_line=on_line)

    def begin(self, command):
        """Send a command without waiting for the reply (collect it later with finish())."""
        self._drain()
        self._write(command)
        self._pending = command

    def finish(self, timeout=10.0, on_line=None, max_total=None):
        """Collect the reply to the command sent with begin(). Returns a Result.

        timeout: longest wait between two lines; max_total: longest wait overall (None = no limit).
        """
        command = getattr(self, "_pending", "") or "command"
        cols, rows, meta, lines = None, [], {}, []
        last = t_start = time.time()
        while True:
            if max_total is not None and time.time() - t_start > max_total:
                self._pending = None
                raise TimeoutError(f"No complete reply to '{command}' within {max_total:.0f} s.")
            line = self._readline()
            if line is None:
                if time.time() - last > timeout:
                    self._pending = None
                    raise TimeoutError(f"No reply to '{command}' within {timeout:.0f} s. Is the board "
                                       "running the ee105 firmware? Run board = connect() again.")
                continue
            last = time.time()
            if not line:
                continue
            lines.append(line)
            if line.startswith("#done"):
                break
            if line.startswith("#err"):
                self._pending = None
                raise BoardError(line[4:].strip())
            if line.startswith("#cols"):
                cols = line[5:].strip().split(",")
                continue
            if line.startswith("#"):
                parts = line[1:].split(None, 1)
                if parts:
                    meta[parts[0]] = parts[1] if len(parts) > 1 else ""
                continue
            if cols is None:          # stray text from a classic command
                continue
            rows.append(line)
            if on_line:
                on_line(line)
        self._pending = None
        data = _parse_rows(rows, cols)
        return Result(cols or [], data, meta, lines)

    # ------------------------------------------------------------ identity
    def firmware(self):
        """'ee105 3.0' (or None if the board runs another sketch). Also reads the board ID."""
        for _ in range(2):
            try:
                self.begin("id")
                r = self.finish(timeout=2.5, max_total=3.0)   # another sketch may print without pause
                fw = None
                for line in r.lines:
                    parts = line[1:].split()
                    if line.startswith("#") and parts and parts[0] == self.FW_NAME:
                        fw = line[1:].strip()
                if fw:
                    self.info = {"firmware": fw, "device_id": r.meta.get("device_id")}
                    return fw
            except (TimeoutError, BoardError):
                pass
            self._drain()
        return None

    @property
    def device_id(self):
        """Unique ID of the board's nRF52840 chip (16 hex digits), or None if not known."""
        return self.info.get("device_id")

    def module(self):
        """Best guess of the module selector S10 position: 1, 2, 3, "CAM", or None (no block
        selected). The board prints these positions as Module 1, Module 2, Module 3 and Camera.

        The board reads S10 on A7 through a resistor ladder. The reading is stored in
        self.selector_volts; its value depends on the board (see hardware.SELECTOR_RANGE).
        """
        r = self.query("module", timeout=3)
        for line in r.lines:
            if line.startswith("selector:"):
                self.selector_line = line
                self.selector_volts = None
                try:
                    self.selector_volts = float(line.split()[-2])
                except (ValueError, IndexError):
                    pass
                tok = line.split()[1]
                return {"1": 1, "2": 2, "3": 3, "CAM": "CAM", "none": None}.get(tok, "unknown")
        raise BoardError("The board did not report the selector position. Run connect() again.")

    def check_module(self, position):
        """Check that the module selector S10 looks like `position` (1, 2, 3 or "CAM", printed on
        the board as Module 1, Module 2, Module 3 and Camera). This is only a check: when the A7
        reading does not fit the position, it prints a warning and the lab goes on."""
        want = "CAM" if str(position).upper() == "CAM" else int(position)
        if self.simulated and hasattr(self.sim, "expect_module"):
            self.sim.expect_module(want)      # the simulated selector follows the lab (unless you set it)
        try:
            got = self.module()
        except BoardError as e:
            arduino._say(f"Could not read the selector S10 ({e}). Check that S10 is on "
                         f"{hw.selector_text(want)} and go on.", ok=False)
            return None
        v = getattr(self, "selector_volts", None)
        if v is None:
            fits = got == want
        else:
            fits = hw.selector_fits(want, v)
        if fits:
            arduino._say(f"Selector S10 is on {hw.selector_text(want)}"
                         + (f" (A7 reads {v:.2f} V)." if v is not None else "."), ok=True)
            return want
        lo, hi = hw.SELECTOR_RANGE[want]
        reading = f"A7 reads {v:.2f} V" if v is not None else "the selector reading is missing"
        arduino._say(f"Warning: {reading}, outside the {lo:.2f} to {hi:.2f} V expected for "
                     f"{hw.selector_text(want)}. Check that S10 points at "
                     f"{hw.SELECTOR_LABEL[want]}; if it does, carry on (this check is only a "
                     "warning).", ok=False)
        return got

    require_module = check_module        # older name, kept so older notebooks still run

    # ------------------------------------------------------- measurements
    def read(self, pin, n=1000, interval_ms=1.0):
        """n samples of analog pin A<pin>, one every interval_ms.

        Returns a DataFrame with columns t_s (time, s), raw (0..1023) and volts.
        """
        us = int(round(interval_ms * 1000))
        r = self.query(f"read {int(pin)} {int(n)} {us}", timeout=max(5, interval_ms / 1000 * 4))
        df = r.frame()
        df["t_s"] = df.pop("t_us") / 1e6
        df["raw"] = df["raw"].astype(int)
        df["volts"] = hw.adc_to_volts(df["raw"])
        return df[["t_s", "raw", "volts"]]

    def volts(self, pin, n=100):
        """Average voltage on A<pin> over n quick readings."""
        return float(self.read(pin, n=n, interval_ms=0.2)["volts"].mean())

    def set_dac(self, channel, volts):
        """Set an AD5593R DAC channel (0..4) to `volts` (0 to 3.3 V). Returns the code used."""
        code = hw.volts_to_dac(volts)
        self.query(f"dac {int(channel)} {code}", timeout=3)
        return code

    def set_dac_code(self, channel, code):
        self.query(f"dac {int(channel)} {int(code)}", timeout=3)

    def zero(self):
        """All DAC outputs back to 0 V."""
        self.query("zero", timeout=3)

    def sweep(self, channel, v_start, v_stop, v_step, pin, settle_ms=2, average=1, live=False):
        """Step DAC `channel` from v_start to v_stop and read A<pin> at each step.

        live=True draws the points as they are measured (the curve grows, the newest point is
        highlighted); live can also be a LiveIV view of your own, or a series name is passed through
        _live_series. Returns a DataFrame: v_dac (V, saturates at 3.3), code, raw, v_adc (V).
        """
        c0, c1 = hw.volts_to_dac(v_start), hw.volts_to_dac(v_stop)
        step = max(1, hw.volts_to_dac(v_step))
        view, series = self._live_view(live, f"DAC channel {int(channel)} (V)", f"A{int(pin)} (V)",
                                       f"Sweep: A{int(pin)} against DAC channel {int(channel)}")
        on_line = None
        if view is not None:
            def on_line(line):
                code, raw = line.split(",")[:2]
                view.add(hw.dac_to_volts(int(float(code))), hw.adc_to_volts(int(float(raw))), series=series)
        r = self.query(f"sweep {int(channel)} {c0} {c1} {step} {int(pin)} {int(settle_ms)} {int(average)}",
                       timeout=10, on_line=on_line)
        if view is not None and live is True:
            view.finish()
        df = r.frame().astype(int)
        df["v_dac"] = hw.dac_to_volts(df["code"])
        df["v_adc"] = hw.adc_to_volts(df["raw"])
        return df[["v_dac", "code", "raw", "v_adc"]]

    def sweep2(self, outer, outer_volts, inner, inner_volts, pin, settle_ms=2, average=1):
        """Nested sweep: outer DAC over outer_volts=(start, stop, step), inner DAC over inner_volts.

        Returns a DataFrame: v_outer, v_inner (V), raw, v_adc (V).
        """
        a0, a1, astep = [hw.volts_to_dac(v) for v in outer_volts]
        b0, b1, bstep = [hw.volts_to_dac(v) for v in inner_volts]
        r = self.query(f"sweep2 {int(outer)} {a0} {a1} {max(1, astep)} {int(inner)} {b0} {b1} {max(1, bstep)} "
                       f"{int(pin)} {int(settle_ms)} {int(average)}", timeout=10)
        df = r.frame().astype(int)
        df["v_outer"] = hw.dac_to_volts(df["codeA"])
        df["v_inner"] = hw.dac_to_volts(df["codeB"])
        df["v_adc"] = hw.adc_to_volts(df["raw"])
        return df[["v_outer", "v_inner", "raw", "v_adc"]]

    def _live_view(self, live, xlabel, ylabel, title):
        """(LiveIV view or None, series name) for the live option of the sweeps."""
        if not live:
            return None, None
        from .live import LiveIV
        if isinstance(live, LiveIV):
            return live, getattr(live, "_series", None)
        return LiveIV(xlabel, ylabel, title=title), None

    def transistor_output(self, v_gs, v_drain=(0.0, 3.3, 0.033), settle_ms=2, average=4, live=False):
        """MOSFET output curves: for each gate voltage in `v_gs` (V), sweep the drain supply V_DAC2
        over v_drain = (start, stop, step) and read A3.

        The drain is fed from DAC channel 2 through a 1 kOhm sense resistor; A3 is the voltage
        across it. Returns a DataFrame: v_gs (V, as set), v_dac2 (V), raw (A3 counts), v_a3 (V).
        Then I_D (mA) = v_a3 and V_DS = v_dac2 - I_D x R_path, with R_path the whole drain path
        (more than 1 kOhm on a real board; see hw.nmos_from_a3 and Lab 2.1 step C3).
        live=True draws every curve as it is measured, one line per gate voltage.
        """
        import pandas as pd
        frames = []
        view, _ = self._live_view(live, "$V_{DAC2}$, the drain supply (V)", "A3 (V), the drain current in mA",
                                  "Output curves: one drain sweep per gate voltage")
        for vg in np.atleast_1d(np.asarray(v_gs, dtype=float)):
            code = self.set_dac(hw.DAC_GATE, vg)
            if view is not None:
                view._series = f"$V_{{GS}}$ = {hw.dac_to_volts(code):.1f} V"
            s = self.sweep(hw.DAC_DRAIN, v_drain[0], v_drain[1], v_drain[2], hw.PIN_NMOS,
                           settle_ms=settle_ms, average=average, live=view)
            frames.append(pd.DataFrame({"v_gs": float(hw.dac_to_volts(code)), "v_dac2": s["v_dac"],
                                        "raw": s["raw"], "v_a3": s["v_adc"]}))
        if view is not None:
            view.finish()
        self.zero()
        return pd.concat(frames, ignore_index=True)

    def transistor_transfer(self, v_drain=3.3, v_gs=(0.0, 3.3, 0.0165), settle_ms=2, average=4, live=False):
        """MOSFET transfer curve: hold the drain supply V_DAC2 at `v_drain` (V) and sweep the gate
        over v_gs = (start, stop, step). Returns a DataFrame: v_gs (V), v_dac2 (V), raw, v_a3 (V).
        live=True draws the curve as it is measured."""
        import pandas as pd
        code = self.set_dac(hw.DAC_DRAIN, v_drain)
        view, _ = self._live_view(live, "$V_{GS}$, the gate voltage (V)", "A3 (V), the drain current in mA",
                                  f"Transfer curve at $V_{{DAC2}}$ = {hw.dac_to_volts(code):.1f} V")
        s = self.sweep(hw.DAC_GATE, v_gs[0], v_gs[1], v_gs[2], hw.PIN_NMOS, settle_ms=settle_ms,
                       average=average, live=view)
        if view is not None:
            view.finish()
        self.zero()
        return pd.DataFrame({"v_gs": s["v_dac"], "v_dac2": float(hw.dac_to_volts(code)),
                             "raw": s["raw"], "v_a3": s["v_adc"]})

    def ppg(self, seconds=8.0, amplitude=0x7F, rate_guess=130):
        """Record red and infrared PPG from the MAX86916 for about `seconds`.

        Returns a DataFrame: t_s (from the board's clock), ir, red (raw counts).
        """
        n = int(seconds * rate_guess)
        r = self.query(f"ppg {n} {int(amplitude)}", timeout=5)
        df = r.frame()
        df["t_s"] = df.pop("t_us") / 1e6
        df[["ir", "red"]] = df[["ir", "red"]].astype(int)
        return df[["t_s", "ir", "red"]]

    def capture(self, pin, n, interval_us, trigger=None, timeout=35):
        """Fast capture of n samples of A<pin> at an exact interval (stored on the board, then sent).

        trigger: start when the reading first rises above this raw level (0..1023).
        Returns (samples as a numpy array of raw counts, actual interval in seconds).
        """
        self.capture_start(pin, n, interval_us, trigger)
        return self.capture_result(timeout=timeout)

    def capture_start(self, pin, n, interval_us, trigger=None):
        """Arm a capture and return at once (for example before another board transmits).

        Collect the samples afterwards with capture_result().
        """
        cmd = f"cap {int(pin)} {int(n)} {int(interval_us)}" + (f" {int(trigger)}" if trigger is not None else "")
        self.begin(cmd)

    def capture_result(self, timeout=35):
        """(samples, interval in seconds) of the capture started with capture_start()."""
        r = self.finish(timeout=timeout)
        x = r.data.ravel()
        dt = float(r.meta.get("interval_us", 0) or 0) / 1e6
        return x, dt

    def _load_symbols(self, symbols):
        s = "".join(str(int(v)) for v in symbols)
        if any(ch not in "0123" for ch in s):
            raise ValueError("symbols must be 0, 1, 2 or 3")
        if not 0 < len(s) <= 20000:
            raise ValueError("send 1 to 20000 symbols at a time")
        self.query("txclear", timeout=3)
        for i in range(0, len(s), 400):
            self.query("txadd " + s[i:i + 400], timeout=3)
        return s

    def transmit(self, symbols, period_ms, levels_volts, channel=hw.DAC_LED2):
        """Play a symbol sequence (string or list of 0..3) on a DAC channel, one symbol per period.

        levels_volts: DAC voltage for symbol 0, 1 (and 2, 3 for 4-level signaling).
        The default channel is LED pair 2, which shines toward the other board.
        """
        s = self._load_symbols(symbols)
        codes = " ".join(str(hw.volts_to_dac(v)) for v in levels_volts)
        us = int(round(period_ms * 1000))
        self.query(f"txgo {int(channel)} {us} {codes}", timeout=len(s) * period_ms / 1000 + 5)

    def loopback(self, symbols, period_ms, levels_volts, samples_per_symbol=4,
                 channel=hw.DAC_LED1, pin=hw.PIN_PD):
        """Send symbols on LED pair 1 and record this board's own photodiode at the same time.

        Returns (samples as raw counts, interval in seconds). Sample k*samples_per_symbol + j
        is the j-th sample inside symbol k, so no synchronization is needed.
        """
        s = self._load_symbols(symbols)
        if len(s) * samples_per_symbol > 40000:
            raise ValueError("symbols x samples_per_symbol must be at most 40000")
        codes = " ".join(str(hw.volts_to_dac(v)) for v in levels_volts)
        us = int(round(period_ms * 1000))
        r = self.query(f"txcap {int(channel)} {us} {int(pin)} {int(samples_per_symbol)} {codes}",
                       timeout=len(s) * period_ms / 1000 + 5)
        return r.data.ravel(), float(r.meta.get("interval_us", 0)) / 1e6

    # ------------------------------------------------------------ streams
    def stream(self, pin, interval_ms=10.0):
        """Generator of (t_s, raw) pairs from A<pin> until you stop iterating.

        Use with ee105.live_plot(...) or a for-loop with a break.
        """
        self._drain()
        self._write(f"stream {int(pin)} {int(round(interval_ms * 1000))}")
        try:
            while True:
                line = self._readline()
                if line is None or line.startswith("#"):
                    if line and line.startswith("#err"):
                        raise BoardError(line[4:].strip())
                    continue
                t_us, raw = line.split(",")
                yield float(t_us) / 1e6, float(raw)
        finally:
            self.stop()

    def ppg_stream(self, amplitude=0x7F):
        """Generator of (t_s, ir, red) from the PPG sensor until you stop iterating."""
        self._drain()
        self._write(f"ppg 100000000 {int(amplitude)}")
        try:
            while True:
                line = self._readline()
                if line is None or line.startswith("#"):
                    if line and line.startswith("#err"):
                        raise BoardError(line[4:].strip())
                    continue
                t_us, ir, red = line.split(",")
                yield float(t_us) / 1e6, float(ir), float(red)
        finally:
            self.stop()

    def live(self, pin, seconds=10, interval_ms=10, volts=True, **kw):
        """Live plot of A<pin> for `seconds`; returns all samples as a DataFrame."""
        from .live import live_plot
        conv = hw.adc_to_volts if volts else (lambda x: x)

        def src():
            g = self.stream(pin, interval_ms)
            try:
                for t, v in g:
                    yield t, conv(v)
            finally:
                g.close()
        kw.setdefault("ylabel", "volts" if volts else "ADC counts")
        kw.setdefault("title", f"A{pin}")
        return live_plot(src(), seconds=seconds, labels=["volts" if volts else "raw"], **kw)

    def live_ppg(self, seconds=15, amplitude=0x7F, **kw):
        """Live plot of the infrared and red PPG for `seconds`; returns the samples as a DataFrame.

        The plot marks every beat it detects (the dips of the last 8 s), shows the heart rate in the
        title, and a heart in the corner lights up on each beat.
        """
        from .live import live_plot
        kw.setdefault("title", "PPG (raw counts)")
        kw.setdefault("annotate", ppg_beats)
        kw.setdefault("refresh_s", 0.25)
        return live_plot(self.ppg_stream(amplitude), seconds=seconds, labels=["ir", "red"],
                         separate=True, **kw)

    def stop(self):
        """Stop a running stream or command. Returns the lines that arrived while stopping."""
        got = []
        try:
            self._write("stop")
            t0 = time.time()
            while time.time() - t0 < 2.0:
                line = self._readline()
                if line is None:
                    continue
                got.append(line)
                if line.startswith("#done") or line.startswith("Ready"):
                    break
        except Exception:
            pass
        self._drain()
        return got

    def monitor(self, command, seconds=5.0, max_lines=40):
        """Serial Monitor in the notebook: send a command you could type, print what comes back.

        Commands: help, module, circuits, divider, temperature, diodes, transistors, transfer,
        light, sensors, "communications send <text>", "communications receive" (see
        ee105.board.COMMANDS). Stops the command after `seconds` (sends "stop").
        Returns all lines received.
        """
        self._drain()
        self._write(command)
        lines, t0 = [], time.time()
        finished = False
        while time.time() - t0 < seconds:
            line = self._readline()
            if line is None:
                continue
            if line.startswith("#done") or line.startswith("Ready to enter"):
                finished = True
                break
            if line.startswith("#err"):
                lines.append(line)
                finished = True
                break
            lines.append(line)
        if not finished:
            lines += [x for x in self.stop() if not x.startswith("#")]   # the command was still running
        if len(lines) <= max_lines:
            for line in lines:
                print(line)
        else:
            half = max_lines // 2
            for line in lines[:half]:
                print(line)
            print(f"... ({len(lines) - 2 * half} more lines; all {len(lines)} are in the returned list) ...")
            for line in lines[-half:]:
                print(line)
        return lines


def ppg_beats(data, window_s=8.0):
    """Beats in the last `window_s` of a live PPG (rows t, ir, red): marks, heart rate and a beat flag
    for live_plot's `annotate` option."""
    t = data[:, 0]
    keep = t >= t[-1] - window_s
    tt, ir = t[keep], data[keep, 1]
    out = {"beat": False}
    if len(tt) < 60 or tt[-1] - tt[0] < 2.5:
        out["title"] = "\u2665 -- bpm"
        return out
    if ir.mean() < 20000:                              # no finger on the sensor
        out["title"] = "\u2665 -- bpm  (no finger?)"
        return out
    from scipy.signal import find_peaks
    fs = (len(tt) - 1) / (tt[-1] - tt[0])
    n = max(3, int(fs))                                # remove the wander: subtract a 1 s moving average
    pad = np.pad(ir, (n // 2, n - 1 - n // 2), mode="edge")
    y = ir - np.convolve(pad, np.ones(n) / n, mode="valid")
    swing = np.percentile(y, 95) - np.percentile(y, 5)
    if swing <= 0:
        return out
    dips, _ = find_peaks(-y, distance=max(1, int(0.4 * fs)), prominence=0.3 * swing)
    if len(dips) == 0:
        out["title"] = "\u2665 -- bpm"
        return out
    out["marks"] = [(tt[i], data[keep, 1][i], 0) for i in dips] + [(tt[i], data[keep, 2][i], 1) for i in dips]
    out["beat"] = (tt[-1] - tt[dips[-1]]) < 0.45
    if len(dips) >= 3:
        bpm = 60.0 / np.median(np.diff(tt[dips]))
        out["title"] = f"\u2665 {bpm:.0f} bpm  (last {window_s:.0f} s)"
    else:
        out["title"] = "\u2665 -- bpm"
    return out


def _parse_rows(rows, cols):
    if not rows:
        return np.zeros((0, len(cols or [])))
    vals = [[float(v) for v in r.split(",") if v != ""] for r in rows]
    if cols and len(cols) == 1:
        flat = [v for row in vals for v in row]
        return np.array(flat, dtype=float).reshape(-1, 1)
    width = len(cols) if cols else max(len(v) for v in vals)
    vals = [v for v in vals if len(v) == width]
    return np.array(vals, dtype=float).reshape(-1, width)


# ---------------------------------------------------------------- connect
def connect(port=None, upload_firmware=True, simulate=None, quiet=False):
    """Connect to the demo board and make sure it runs the ee105 firmware.

    port            : leave None to find the board automatically
    upload_firmware : upload the course firmware if the board runs something else
    simulate        : True for a simulated board (no hardware needed);
                      (the environment variable EE105_SIMULATE=1 also turns it on)
    """
    def make_sim():
        from .sim import SimSerial
        return SimSerial()
    return _connect(Board, make_sim, port, upload_firmware, simulate, quiet)


KNOWN_FIRMWARE = ("ee105", "ee105cam")


def _choose_port(cls):
    """With several Arduinos plugged in, prefer one already running this firmware, and never pick
    one that runs the other EE 105 firmware (so the camera sketch never lands on the demo board)."""
    ports = [p for p, _ in arduino.list_ports()]
    if not ports:
        found = arduino.find_port(wait=3)
        return found
    if len(ports) == 1:
        return ports[0]
    other = None
    for p in ports:
        name = None
        try:
            b = Board(p)
            b.begin("id")
            r = b.finish(timeout=2.5, max_total=3.0)
            b.close()
            for line in r.lines:
                if line.startswith("#") and line[1:].split() and line[1:].split()[0] in KNOWN_FIRMWARE:
                    name = line[1:].split()[0]
        except Exception:
            try:
                b.close()
            except Exception:
                pass
        if name == cls.FW_NAME:
            return p
        if name not in KNOWN_FIRMWARE and other is None:
            other = p
    return other or ports[0]


def _connect(cls, make_sim, port=None, upload_firmware=True, simulate=None, quiet=False):
    import os
    if os.environ.get("EE105_SIMULATE", "") == "1":
        simulate = True              # set by ee105.simulate(True) or by the automatic notebook tests
    if simulate:
        b = cls("SIM", serial_obj=make_sim())
        b.firmware()                 # fills b.info (firmware name and the simulated board ID)
        if not quiet:
            arduino._say(f"Connected to a SIMULATED {cls.KIND} (no hardware). Results look real but are "
                         "made up.", ok=True)
        return b

    arduino.ensure_pyserial()
    port = port or _choose_port(cls)
    if not port:
        raise RuntimeError("No Arduino found. Plug in the Nano 33 BLE with a USB data cable. "
                           "(No board today? Use simulate=True to try the notebook.)")
    release_port(port)
    b = cls(port)
    fw = b.firmware()
    if fw and fw.split()[-1] == cls.FW_VERSION:
        if not quiet:
            arduino._say(f"Connected to the {cls.KIND} on {port} (firmware {fw}, board {b.device_id}).", ok=True)
        return b
    if not upload_firmware:
        if not quiet:
            arduino._say(f"Connected on {port}; the board runs a different sketch.", ok=False)
        return b
    b.close()
    if not quiet:
        arduino._say(f"The board is not running the EE 105 {cls.KIND} firmware yet; uploading it now.")
    new_port = arduino.upload(cls.FW_DIR, port=port)
    time.sleep(1.5)
    b = cls(new_port)
    fw = b.firmware()
    if not fw:
        b.close()
        raise RuntimeError("Uploaded the firmware but the board does not answer. Unplug and replug the USB "
                           "cable, then connect again.")
    if not quiet:
        arduino._say(f"Connected to the {cls.KIND} on {new_port} (firmware {fw}, board {b.device_id}).", ok=True)
    return b


def connect_all(simulate=None):
    """Connect to every board that is plugged in (for LiFi with two boards on one computer)."""
    import os
    if os.environ.get("EE105_SIMULATE", "") == "1":
        simulate = True
    if simulate:
        boards = [connect(simulate=True, quiet=True), connect(simulate=True, quiet=True)]
        arduino._say("Connected to two SIMULATED demo boards facing each other.", ok=True)
        return boards
    return [connect(port=p) for p, _ in arduino.list_ports()]
