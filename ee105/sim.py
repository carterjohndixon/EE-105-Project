"""A simulated demo board, so every notebook also runs without hardware.

    board = connect(simulate=True)      # or set the environment variable EE105_SIMULATE=1

The simulator answers the same text commands as the ee105 firmware, using
simple physical models of the board:

* touch panel (A0): press a key with ``board.sim.press("S5")``
* divider header (A1): by default the Lab 3.1 thermistor divider, a 10 kOhm
  3950 NTC on top of 10 kOhm; a finger warms it. By default ("auto") a finger
  touches it during long recordings; call ``board.sim.touch_thermistor(True / False)``
  to control it yourself. ``board.sim.set_divider(r_top, r_bottom)`` plugs in
  two resistors instead, ``board.sim.set_divider(None)`` leaves the header empty.
* diode (A2): Shockley diode with series resistance (n = 1.93, I_S = 3.4 nA,
  Rs = 28 Ohm, the fit to a real board's sweep), 1 kOhm sense resistor
* NMOS (A3): square-law MOSFET with a smooth subthreshold tail and a little
  channel-length modulation, set to match the transfer sweep of a real demo board
  (V_th = 1.40 V, K = 0.53 mA/V^2). A3 reads the voltage across the 1 kOhm drain
  sense resistor, but the drain path from DAC channel 2 is 4.6 kOhm in all (the
  sense resistor plus 3.6 kOhm more, as measured on that board), so the drain
  current levels off near 0.64 mA at V_DAC2 = 3.3 V. The simulator solves the
  series circuit for I_D.
* ADC noise on A2 and A3: about 0.9 and 0.65 count rms per sweep point at 4 readings
  per point, as on the real board (about half of that at 16 readings)
* module selector (A7): reports the position the lab asks for with
  ``board.check_module(...)``; set ``board.sim.selector = 2`` (or 1, 3, "CAM",
  None) to turn the simulated switch yourself, ``"auto"`` to follow the lab again
* photodiode (A6): LEDs with a 2.75 V turn-on, first-order photodiode response;
  LED pair 2 of one simulated board shines on the photodiode of the others
* PPG: red and infrared pulse waveform at about 130 samples per second,
  72 beats per minute, SpO2 about 97 % (``board.sim.heart_rate``, ``board.sim.spo2``,
  ``board.sim.finger_on_ppg``)

Results look like real data but they are made up: use them to learn the
notebook, then measure the real board.
"""
import math
import os
import time
from collections import deque

import numpy as np

from . import hardware as hw

FW_LINE = "#ee105 3.0"
V_LED_ON = 2.75         # LED drive voltage where light starts (V)
G_OWN = 900.0           # A6 counts per volt of LED pair 1 drive above turn-on
G_CROSS = 400.0         # A6 counts per volt of another board's LED pair 2 drive above turn-on
TAU_PD = 300e-6         # photodiode amplifier time constant (s)


def _now():
    return time.monotonic()


SWEEP_SHOW_S = 0.007    # seconds per sweep point when a person watches (about a real board's pace)


def _interactive():
    """False under the automatic notebook runs (tools/runsim.py sets EE105_FAST=1): no delays for show."""
    return os.environ.get("EE105_FAST", "") != "1"


# ------------------------------------------------------------------ light channel
class _Channel:
    """All simulated boards in this Python session share one optical path."""

    def __init__(self):
        self.boards = []
        self.serials = []
        self.version = 0


CHANNEL = _Channel()


class DriveLog:
    """The DAC code of one channel as a step function of time."""

    def __init__(self):
        self.t = [0.0]
        self.code = [0]

    def set(self, t, code):
        while len(self.t) > 1 and self.t[-1] > t:     # a new setting replaces planned ones
            self.t.pop()
            self.code.pop()
        self.t.append(t)
        self.code.append(int(code))
        CHANNEL.version += 1
        self._prune()

    def plan(self, ts, codes):
        """Schedule many settings at once (a transmission)."""
        if len(ts) == 0:
            return
        while len(self.t) > 1 and self.t[-1] > ts[0]:
            self.t.pop()
            self.code.pop()
        self.t.extend(float(x) for x in ts)
        self.code.extend(int(c) for c in codes)
        CHANNEL.version += 1
        self._prune()

    def _prune(self, keep_s=300.0):
        if len(self.t) > 200000:
            cut = np.searchsorted(self.t, self.t[-1] - keep_s)
            if cut > 1:
                self.t = [0.0] + self.t[cut:]
                self.code = [self.code[cut - 1]] + self.code[cut:]

    def at(self, times):
        idx = np.searchsorted(self.t, times, side="right") - 1
        return np.asarray(self.code)[np.maximum(idx, 0)]

    def events_after(self, t0):
        i = int(np.searchsorted(self.t, t0, side="right"))
        return self.t[i:]


def _dac_volts(code):
    return np.minimum(np.asarray(code, dtype=float) * hw.DAC_V_PER_CODE, hw.VREF)


def _led_light(code):
    return np.maximum(0.0, _dac_volts(code) - V_LED_ON)


def _filtered(log, ts, gain, tau=TAU_PD):
    """First-order low-pass response of gain*light(log) at the (sorted) times ts."""
    ts = np.asarray(ts, dtype=float)
    T = np.asarray(log.t)
    k0 = max(0, int(np.searchsorted(T, ts[0] - 20 * tau, side="right")) - 1)
    k1 = int(np.searchsorted(T, ts[-1], side="right"))
    T = T[k0:k1]
    U = gain * _led_light(np.asarray(log.code)[k0:k1])
    if len(T) == 0:
        return np.zeros_like(ts)
    Tl, Ul = T.tolist(), U.tolist()
    Y = [Ul[0]]
    for k in range(1, len(Tl)):
        Y.append(Ul[k - 1] + (Y[-1] - Ul[k - 1]) * math.exp(-(Tl[k] - Tl[k - 1]) / tau))
    Y = np.array(Y)
    idx = np.maximum(np.searchsorted(T, ts, side="right") - 1, 0)
    return U[idx] + (Y[idx] - U[idx]) * np.exp(-(ts - T[idx]) / tau)


# --------------------------------------------------------------- device models
# Diode and MOSFET of the devices block, fitted to the sweeps of a real demo board
# (instructor's board, November 2026; testdata/real_board_2026-11-04 in the lab repository).
DIODE_IS, DIODE_N, DIODE_RS = 3.4e-9, 1.93, 28.0      # A, -, Ohm: knee (0.5 mA) near 0.61 V, 2.5 mA at 3.3 V
NMOS_VTH, NMOS_K, NMOS_LAMBDA = 1.40, 0.53, 0.02      # V, mA/V^2 (K = k'/2), 1/V
R_DRAIN_EXTRA_KOHM = 3.6                              # measured: drain path = 1 kOhm sense + 3.6 kOhm more
R_DRAIN_PATH_KOHM = hw.R_SENSE_NMOS / 1e3 + R_DRAIN_EXTRA_KOHM   # 4.6 kOhm from DAC channel 2 to the drain
ADC_NOISE = {hw.PIN_PD: 1.0, hw.PIN_TOUCH: 1.2,       # rms counts of ONE reading (adc() divides by sqrt(avg))
             hw.PIN_DIODE: 1.7, hw.PIN_NMOS: 1.2}     # A2, A3: 0.9 and 0.65 count per point at 4 readings
ADC_NOISE_DEFAULT = 0.8


def _diode_table(Is=DIODE_IS, n=DIODE_N, Rs=DIODE_RS, R=1e3, Vt=0.02585):
    I = np.concatenate([[0.0], np.logspace(-9, -2, 4000)])          # A
    vdac = n * Vt * np.log1p(I / Is) + I * (R + Rs)
    return vdac, I


_DIODE_V, _DIODE_I = _diode_table()


def diode_current_ma(v_dac):
    """Diode current (mA) for a DAC voltage across diode + 1 kOhm."""
    return np.interp(v_dac, _DIODE_V, _DIODE_I) * 1e3


def nmos_current_ma(vgs, vds, vth=NMOS_VTH, k=2 * NMOS_K, lam=NMOS_LAMBDA, n=1.5, Vt=0.02585):
    """Drain current (mA): square law with a smooth subthreshold tail. k = 2K in mA/V^2.

    With vth = 1.40 V and K = k/2 = 0.53 mA/V^2 (the fit to a real board's transfer sweep) the
    saturation current is 0.19 mA at V_GS = 2.0 V and 0.53 mA at 2.4 V; 0.25 mA needs about 2.09 V.
    """
    vgs = np.asarray(vgs, dtype=float)
    vds = np.maximum(np.asarray(vds, dtype=float), 0.0)
    s = 2 * n * Vt
    vov = s * np.logaddexp(0.0, (vgs - vth) / s)       # smooth overdrive, about vgs - vth above threshold
    vde = np.minimum(vds, vov)
    i = k * (vov * vde - 0.5 * vde ** 2) * (1 + lam * vds)
    return np.maximum(i, 0.0)


def nmos_series_ma(vgs, v_dac2, r_kohm=R_DRAIN_PATH_KOHM):
    """Drain current (mA) with the drain fed from v_dac2 through r_kohm (the whole drain path,
    4.6 kOhm): solves I = f(V_GS, V_DS) with V_DS = V_DAC2 - R I by bisection. I can never exceed
    V_DAC2 / R."""
    vgs, v2 = np.broadcast_arrays(np.asarray(vgs, dtype=float), np.maximum(np.asarray(v_dac2, dtype=float), 0.0))
    lo = np.zeros(vgs.shape)
    hi = v2 / r_kohm
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        below = mid < nmos_current_ma(vgs, v2 - mid * r_kohm)    # the root lies above mid
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


def thermistor_volts(temp_c, r0=10e3, beta=3950.0, r_fixed=10e3):
    t = np.asarray(temp_c) + 273.15
    rt = r0 * np.exp(beta * (1.0 / t - 1.0 / 298.15))
    return hw.VREF * r_fixed / (rt + r_fixed)


# ------------------------------------------------------------------ the board
class SimBoard:
    """Physical state of one simulated demo board."""

    def __init__(self, seed=None):
        if seed is None and os.environ.get("EE105_SEED"):
            seed = int(os.environ["EE105_SEED"]) + len(CHANNEL.boards)
        self.rng = np.random.default_rng(seed)
        self.dac = [DriveLog() for _ in range(5)]
        self.keys = [(0.0, None)]                 # touch panel: (time, key) steps
        self.room_c = 22.0
        self.finger_c = 31.5
        self.thermistor_auto = True
        self.finger = [(0.0, False)]              # thermistor finger: (time, on) steps
        self.heart_rate = 72.0
        self.spo2 = 97.0
        self.finger_on_ppg = True
        self.ambient = 3.0                         # room light on the photodiode (counts)
        self.selector = "auto"                     # S10: 1, 2, 3, "CAM", None, or "auto" (follows the lab)
        self._expected = 1                         # what the lab asked for (check_module)
        self.divider = "thermistor"                # divider header: "thermistor", (r_top, r_bottom) or None
        idrng = np.random.default_rng(None if seed is None else seed + 1000)
        self.device_id = "".join("0123456789ABCDEF"[int(d)] for d in idrng.integers(0, 16, 16))
        self.link_gain = 1.0                       # scales the light from other boards
        self.tx_len = 0
        self.tx_buf = ""
        self._ppg_phase = self.rng.uniform(0, 1)
        self._beats = []
        self._beats_hr = None
        CHANNEL.boards.append(self)

    def close(self):
        if self in CHANNEL.boards:
            CHANNEL.boards.remove(self)

    # ---------------------------------------------------------- user controls
    def press(self, key, seconds=None):
        """Hold touch-panel key 'S1'..'S9' (None releases). With seconds, release after that time."""
        if key is not None and key not in hw.TOUCH_NODE_V:
            raise ValueError("key must be one of " + ", ".join(hw.TOUCH_NODE_V))
        t = _now()
        self.keys = [(a, b) for a, b in self.keys if a <= t] + [(t, key)]
        if seconds is not None:
            self.keys.append((t + seconds, None))

    def release(self):
        self.press(None)

    def press_sequence(self, steps, start_in=0.0):
        """Script several presses: steps = [("S1", 1.0), (None, 0.5), ("S5", 1.0), ...] (key, seconds).

        The first step starts `start_in` seconds from now; the panel is released after the last step.
        """
        t = _now() + start_in
        self.keys = [(a, b) for a, b in self.keys if a <= _now()]
        if start_in > 0:
            self.keys.append((_now(), None))
        for key, seconds in steps:
            if key is not None and key not in hw.TOUCH_NODE_V:
                raise ValueError("key must be one of " + ", ".join(hw.TOUCH_NODE_V))
            self.keys.append((t, key))
            t += seconds
        self.keys.append((t, None))

    def expect_module(self, position):
        """Called by board.check_module(): the "auto" selector moves to the position the lab needs."""
        self._expected = position

    def selector_position(self):
        return self._expected if self.selector == "auto" else self.selector

    def set_divider(self, r_top="thermistor", r_bottom=None):
        """Parts in the divider header: set_divider("thermistor") (Lab 3.1, the default),
        set_divider(4.7e3, 10e3) for two resistors (ohms, top then bottom), set_divider(None) for none."""
        if r_top is None or r_top == "thermistor":
            self.divider = r_top
        else:
            self.divider = (float(r_top), float(r_bottom))

    def touch_thermistor(self, on=True):
        """Put a finger on the thermistor (True) or take it off (False). Turns off the automatic finger."""
        self.thermistor_auto = False
        t = _now()
        self.finger = [(a, b) for a, b in self.finger if a <= t] + [(t, bool(on))]

    # ------------------------------------------------------------- analog pins
    def _key_at(self, ts):
        times = [a for a, _ in self.keys]
        idx = np.searchsorted(times, ts, side="right") - 1
        return [self.keys[max(i, 0)][1] for i in idx]

    def _temperature(self, ts):
        ev = sorted(self.finger)
        T = [self.room_c]
        times = [ev[0][0]]
        for k in range(1, len(ev)):
            dt = ev[k][0] - ev[k - 1][0]
            target = self.finger_c if ev[k - 1][1] else self.room_c
            tau = 6.0 if ev[k - 1][1] else 25.0
            T.append(target + (T[-1] - target) * math.exp(-dt / tau))
            times.append(ev[k][0])
        idx = np.maximum(np.searchsorted(times, ts, side="right") - 1, 0)
        out = np.empty(len(ts))
        for j, (i, t) in enumerate(zip(idx, ts)):
            on = ev[i][1]
            target = self.finger_c if on else self.room_c
            tau = 6.0 if on else 25.0
            out[j] = target + (T[i] - target) * math.exp(-(t - times[i]) / tau)
        return out

    def _auto_finger(self, t0, duration):
        """Automatic finger on the thermistor for long recordings (when not controlled by hand)."""
        if not self.thermistor_auto or duration < 4.0:
            return
        if any(a > t0 - 60 for a, _ in self.finger[1:]):
            return                       # a recent automatic touch is still cooling down
        on, off = t0 + 0.2 * duration, t0 + 0.6 * duration
        self.finger = [(a, b) for a, b in self.finger if a <= t0] + [(on, True), (off, False)]

    def volts(self, pin, ts):
        """Pin voltage at the times ts (before the ADC)."""
        ts = np.atleast_1d(np.asarray(ts, dtype=float))
        n = len(ts)
        r = self.rng
        mains = np.sin(2 * np.pi * 60 * ts)
        if pin == hw.PIN_TOUCH:
            keys = self._key_at(ts)
            v = np.array([hw.TOUCH_NODE_V[k] if k else np.nan for k in keys])
            floating = np.isnan(v)
            v[floating] = (1.0 + 0.35 * mains[floating] + 0.08 * r.standard_normal(floating.sum()))
            return np.clip(v, 0, hw.VREF)
        if pin == hw.PIN_DIVIDER:
            if self.divider == "thermistor":
                return thermistor_volts(self._temperature(ts)) + 0.0016 * mains
            if self.divider is None:                    # empty header: A1 floats
                return np.clip(0.9 + 0.3 * mains + 0.08 * r.standard_normal(n), 0, hw.VREF)
            rt, rb = self.divider
            return np.full(n, hw.VREF * rb / (rt + rb)) + 0.0016 * mains
        if pin == hw.PIN_DIODE:
            return diode_current_ma(_dac_volts(self.dac[hw.DAC_DIODE].at(ts))) * (hw.R_SENSE_DIODE / 1e3)
        if pin == hw.PIN_NMOS:                          # A3 = I_D x 1 kOhm (the sense part of the drain path)
            vgs = _dac_volts(self.dac[hw.DAC_GATE].at(ts))
            v_dac2 = _dac_volts(self.dac[hw.DAC_DRAIN].at(ts))
            return nmos_series_ma(vgs, v_dac2) * hw.NMOS_V_PER_MA
        if pin == hw.PIN_PD:
            return self.photodiode_counts(ts) * hw.ADC_V_PER_COUNT
        if pin == hw.PIN_SELECT:
            pos = self.selector_position()
            level = hw.SELECTOR_V.get(pos, 0.02) if pos is not None else 0.02
            return np.full(n, level) + 0.004 * r.standard_normal(n)
        return np.clip(1.0 + 0.2 * mains + 0.05 * r.standard_normal(n), 0, hw.VREF)

    def photodiode_counts(self, ts):
        ts = np.asarray(ts, dtype=float)
        flicker = 1.0 + 0.3 * np.abs(np.sin(2 * np.pi * 60 * ts))
        y = self.ambient * flicker
        y = y + _filtered(self.dac[hw.DAC_LED1], ts, G_OWN)
        for other in CHANNEL.boards:
            if other is not self:
                y = y + _filtered(other.dac[hw.DAC_LED2], ts, G_CROSS * self.link_gain)
        return y

    def adc(self, pin, ts, avg=1):
        v = self.volts(pin, ts)
        noise = ADC_NOISE.get(pin, ADC_NOISE_DEFAULT) / math.sqrt(avg)
        raw = v / hw.ADC_V_PER_COUNT + noise * self.rng.standard_normal(len(v))
        return np.clip(np.round(raw), 0, 1023).astype(int)

    # -------------------------------------------------------------------- PPG
    def _beat_times(self, t_start, t_end):
        """One running schedule of heart beats (with a little rate variability), extended as needed."""
        b = self._beats
        rr = 60.0 / self.heart_rate
        if not b or t_start < b[0] or t_start > b[-1] + 30:
            b[:] = [t_start - self._ppg_phase * rr]
        elif self.heart_rate != self._beats_hr:      # new rate: keep the beats before t_start only
            keep = [x for x in b if x <= t_start]
            b[:] = keep[-1:] or [t_start - self._ppg_phase * rr]
        self._beats_hr = self.heart_rate
        while b[-1] < t_end + 2 * rr:
            rr = 60.0 / self.heart_rate
            b.append(b[-1] + rr * (1 + 0.04 * math.sin(2 * math.pi * 0.25 * b[-1]) +
                                   0.01 * self.rng.standard_normal()))
        if len(b) > 2000:
            del b[:len(b) - 1000]
        return np.array(b)

    def ppg(self, n, t0, amp=0x7F):
        """n samples: (t_us from t0, ir, red)."""
        r = self.rng
        dt = 1.0 / 131.0
        t = np.cumsum(np.full(n, dt) + r.normal(0, 0.0002, n))
        t -= t[0]
        if not self.finger_on_ppg:
            ir = 1500 + r.normal(0, 60, n)
            red = 1200 + r.normal(0, 60, n)
            return t, np.round(ir), np.round(red)
        abs_t = t0 + t
        beats = self._beat_times(abs_t[0], abs_t[-1])
        k = np.searchsorted(beats, abs_t, side="right") - 1
        ph = (abs_t - beats[k]) / (beats[k + 1] - beats[k])   # 0..1 within each beat
        pulse = np.exp(-((ph - 0.18) / 0.08) ** 2) + 0.35 * np.exp(-((ph - 0.48) / 0.07) ** 2)
        pulse /= 1.1
        scale = min(1.0, amp / 127.0) if amp else 0.0
        dc_ir, dc_red = 120000.0 * scale, 109000.0 * scale
        ac_ir = 0.010
        ratio = max(0.2, (110.0 - self.spo2) / 25.0)       # SpO2 = 110 - 25 R
        ac_red = ac_ir * ratio
        breath = 1 + 0.003 * np.sin(2 * np.pi * 0.25 * abs_t)
        drift = 1 + 0.002 * np.sin(2 * np.pi * 0.03 * abs_t + 1.0)
        ir = dc_ir * (1 - ac_ir * pulse) * breath * drift + r.normal(0, 25, n)
        red = dc_red * (1 - ac_red * pulse) * breath * drift + r.normal(0, 25, n)
        return t, np.clip(np.round(ir), 0, 262143), np.clip(np.round(red), 0, 262143)


# ------------------------------------------------------------- serial endpoint
def _wait_until(io, t):
    while _now() < t:
        if io.stop:
            return
        yield None


class SimSerial:
    """Looks like a pyserial port; behind it runs the simulated firmware."""

    simulated = True

    def __init__(self, seed=None):
        self.model = SimBoard(seed)
        self.is_open = True
        self.timeout = 0.2
        self.port = "SIM"
        self._out = deque(maxlen=200000)
        self._inbuf = b""
        self._gen = None
        self.stop = False
        CHANNEL.serials.append(self)

    # -- pyserial-like interface
    @property
    def in_waiting(self):
        return sum(len(x) for x in self._out)

    def write(self, data):
        if not self.is_open:
            raise OSError("port closed")
        self._inbuf += bytes(data)
        while b"\n" in self._inbuf:
            line, self._inbuf = self._inbuf.split(b"\n", 1)
            self._handle(line.decode(errors="replace").strip())
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self._out.clear()

    def reset_output_buffer(self):
        pass

    def close(self):
        self.is_open = False
        self.model.close()
        if self in CHANNEL.serials:
            CHANNEL.serials.remove(self)

    def _step(self):
        """Run the simulated firmware one step: 'line', 'wait' or 'idle'."""
        if self._gen is None:
            return "idle"
        try:
            item = next(self._gen)
        except StopIteration:
            self._gen = None
            return "idle"
        if item is None:
            return "wait"
        if item.startswith(("#done", "#err")) or item.startswith("Ready to enter"):
            self._gen = None
        self._out.append((item + "\r\n").encode())
        return "line"

    def _pump(self, max_items=5000):
        """Let this board's firmware run on while the notebook talks to another board."""
        for _ in range(max_items):
            if self._step() != "line":
                break

    def readline(self):
        deadline = _now() + (self.timeout or 0)
        while True:
            for other in list(CHANNEL.serials):
                if other is not self and other.is_open:
                    other._pump()
            if self._out:
                return self._out.popleft()
            state = self._step()
            if state == "line":
                continue
            if _now() >= deadline:
                return b""
            time.sleep(0.001 if state == "wait" else 0.005)

    # -- command handling
    def _handle(self, line):
        if not line:
            return
        if self._gen is not None:
            if line.lower() in ("e", "exit", "stop"):
                self.stop = True
            return                      # the firmware ignores other input while busy
        self.stop = False
        self._gen = _firmware(self.model, line, self, _now())


# ------------------------------------------------------- simulated firmware
def _ints(tok, k, default=None):
    try:
        return int(float(tok[k]))
    except (IndexError, ValueError):
        if default is None:
            raise
        return default


def _firmware(m, line, io, t_cmd):
    tok = line.split()
    c = tok[0].lower()
    try:
        if c == "id":
            yield FW_LINE
            yield f"#device_id {m.device_id}"
            yield "#done"
        elif c in ("read", "stream"):
            yield from _cmd_read(m, tok, io, c == "stream", t_cmd)
        elif c == "dac":
            ch, code = _ints(tok, 1), _ints(tok, 2)
            if not 0 <= ch < 5:
                yield "#err usage: dac <ch 0-4> <code 0-4095>"
                return
            m.dac[ch].set(_now(), max(0, min(4095, code)))
            yield "#done"
        elif c in ("zero", "e", "exit", "stop"):
            t = _now()
            for d in m.dac:
                d.set(t, 0)
            yield "#done"
        elif c == "sweep":
            yield from _cmd_sweep(m, tok, io)
        elif c == "sweep2":
            yield from _cmd_sweep2(m, tok, io)
        elif c == "ppg":
            yield from _cmd_ppg(m, tok, io, t_cmd)
        elif c == "cap":
            yield from _cmd_cap(m, tok, io, t_cmd)
        elif c == "txclear":
            m.tx_buf = ""
            yield "#done"
        elif c == "txadd":
            if len(tok) < 2:
                yield "#err usage: txadd <digits 0-3>"
                return
            m.tx_buf = (m.tx_buf + "".join(ch for ch in tok[1] if ch in "0123"))[:20000]
            yield f"#len {len(m.tx_buf)}"
            yield "#done"
        elif c == "txgo":
            yield from _cmd_txgo(m, tok, io)
        elif c == "txcap":
            yield from _cmd_txcap(m, tok, io)
        elif c == "i2c":
            yield "#done"
        elif c == "button":
            yield from _cmd_button(m, tok, io)
        elif c == "communications":
            sub = tok[1].lower() if len(tok) > 1 else ""
            if sub == "send":
                rest = line.split(None, 2)
                yield from _comm_send(m, io, rest[2].strip() if len(rest) > 2 else "")
            elif sub == "receive":
                yield from _comm_receive(m, io)
            else:
                yield "#err usage: communications send <text>  |  communications receive"
        elif c in _TYPED:
            yield from _TYPED[c](m, io)
        else:
            yield f"#err unknown command: {c} (type help for the list)"
    except (IndexError, ValueError):
        yield f"#err bad arguments for {c}"


def _cmd_read(m, tok, io, streaming, t_cmd):
    pin = _ints(tok, 1)
    if streaming:
        n, dt = None, _ints(tok, 2)
    else:
        n, dt = _ints(tok, 2), _ints(tok, 3)
    if not 0 <= pin <= 7 or dt < 50:
        yield "#err usage: read <pin 0-7> <n> <interval_us >= 50>"
        return
    yield "#cols t_us,raw"
    dts = dt / 1e6
    if pin == hw.PIN_DIVIDER:
        m._auto_finger(t_cmd, (n or 1500) * dts if n else 14.0)
    if not streaming:
        ts = t_cmd + np.arange(n) * dts
        if pin == hw.PIN_PD:            # light from other boards: wait until the window has passed
            yield from _wait_until(io, ts[-1])
        raw = m.adc(pin, ts)
        for i in range(n):
            yield f"{i * dt},{raw[i]}"
        yield "#done"
        return
    i = 0
    nb = max(1, min(32, int(0.05 / dts)))       # compute at most 50 ms ahead, so touches show up at once
    while True:
        block = np.arange(i, i + nb)
        ts = t_cmd + block * dts
        yield from _wait_until(io, ts[0])
        raw = m.adc(pin, ts)
        for j, k in enumerate(block):
            yield from _wait_until(io, ts[j])
            if io.stop:
                break
            yield f"{k * dt},{raw[j]}"
        i += nb
        if io.stop:
            yield "#stopped"
            break
    yield "#done"


def _sweep_codes(a, b, step):
    return list(range(a, b + 1, step)) if step > 0 else []


def _cmd_sweep(m, tok, io):
    if len(tok) < 7:
        yield "#err usage: sweep <ch> <c0> <c1> <step> <pin> <settle_ms> [avg]"
        return
    ch, c0, c1, step, pin, settle = (_ints(tok, k) for k in range(1, 7))
    avg = max(1, _ints(tok, 7, 1))
    if not (0 <= ch < 5 and 0 <= pin <= 7 and step > 0):
        yield "#err bad channel, pin or step"
        return
    yield "#cols code,raw"
    t = _now()
    per = max(settle, 1) / 1000.0
    codes = _sweep_codes(c0, c1, step)
    times = t + np.arange(len(codes)) * per
    m.dac[ch].plan(times, [max(0, min(4095, x)) for x in codes])
    show = SWEEP_SHOW_S if _interactive() else 0.0      # pace the points so a live plot has something to show
    for k, code in enumerate(codes):
        raw = m.adc(pin, [times[k] + per * 0.9], avg)[0]
        if show:
            yield from _wait_until(io, t + (k + 1) * show)
        yield f"{code},{raw}"
        if io.stop:
            yield "#stopped"
            break
    m.dac[ch].set(times[-1] + per if len(codes) else _now(), 0)
    yield "#done"


def _cmd_sweep2(m, tok, io):
    if len(tok) < 11:
        yield "#err usage: sweep2 <chA> <a0> <a1> <astep> <chB> <b0> <b1> <bstep> <pin> <settle_ms> [avg]"
        return
    chA, a0, a1, astep, chB, b0, b1, bstep, pin, settle = (_ints(tok, k) for k in range(1, 11))
    avg = max(1, _ints(tok, 11, 1))
    if not (0 <= chA < 5 and 0 <= chB < 5 and 0 <= pin <= 7 and astep > 0 and bstep > 0):
        yield "#err bad channel, pin or step"
        return
    yield "#cols codeA,codeB,raw"
    per = max(settle, 1) / 1000.0
    t = _now()
    stopped = False
    for a in _sweep_codes(a0, a1, astep):
        bs = _sweep_codes(b0, b1, bstep)
        times = t + np.arange(len(bs)) * per
        m.dac[chA].set(t, max(0, min(4095, a)))
        m.dac[chB].plan(times, [max(0, min(4095, b)) for b in bs])
        raw = m.adc(pin, times + per * 0.9, avg)
        for b, v in zip(bs, raw):
            yield f"{a},{b},{v}"
            if io.stop:
                stopped = True
                break
        t = times[-1] + per if len(bs) else t
        if stopped:
            yield "#stopped"
            break
    m.dac[chA].set(t, 0)
    m.dac[chB].set(t, 0)
    yield "#done"


def _cmd_ppg(m, tok, io, t_cmd):
    n = _ints(tok, 1)
    amp = max(0, min(255, _ints(tok, 2, 0x7F)))
    yield "#cols t_us,ir,red"
    paced = n > 50000
    done = 0
    t0 = t_cmd
    while done < n:
        k = min(256, n - done)
        t, ir, red = m.ppg(k, t0, amp)
        for j in range(k):
            if paced:
                yield from _wait_until(io, t_cmd + (t0 - t_cmd) + t[j])
            if io.stop:
                break
            yield f"{int(round((t0 - t_cmd + t[j]) * 1e6))},{int(ir[j])},{int(red[j])}"
        if io.stop:
            yield "#stopped"
            break
        done += k
        t0 = t0 + t[-1] + 1.0 / 131.0
    yield "#done"


def _trigger_time(m, pin, level, t_arm):
    """First time after t_arm when the input rises above level, or None (not yet)."""
    if m.adc(pin, [t_arm])[0] > level:
        return t_arm
    if pin != hw.PIN_PD:
        cands = []
    else:
        cands = list(m.dac[hw.DAC_LED1].events_after(t_arm))
        for other in CHANNEL.boards:
            if other is not m:
                cands += list(other.dac[hw.DAC_LED2].events_after(t_arm))
    for te in sorted(cands)[:400]:
        grid = te + np.linspace(0, 2e-3, 81)
        y = m.photodiode_counts(grid)
        hit = np.nonzero(y > level)[0]
        if len(hit):
            return grid[hit[0]]
    return None


def _cmd_cap(m, tok, io, t_cmd):
    pin, n, dt = _ints(tok, 1), _ints(tok, 2), _ints(tok, 3)
    trig = _ints(tok, 4, -1)
    if not (0 <= pin <= 7 and 1 <= n <= 40000 and dt >= 20):
        yield "#err bad pin, n (1-40000) or interval (>= 20 us)"
        return
    start = t_cmd
    if trig >= 0:
        yield "#waiting for trigger"
        last_version = -1
        while True:
            if CHANNEL.version != last_version or pin != hw.PIN_PD:
                last_version = CHANNEL.version
                start = _trigger_time(m, pin, trig, t_cmd)
                if start is not None:
                    break
            if io.stop:
                yield "#stopped"
                yield "#done"
                return
            if _now() - t_cmd > 30:
                yield "#err no signal above the trigger level within 30 s"
                return
            yield None
    if pin == hw.PIN_DIVIDER:
        m._auto_finger(start, n * dt / 1e6)
    ts = start + np.arange(n) * dt / 1e6
    # the capture ends after the last sample; wait for it if it lies in the future
    yield from _wait_until(io, min(ts[-1], _now() + 60))
    raw = m.adc(pin, ts)
    yield f"#interval_us {dt:.3f}"
    yield "#cols raw"
    for i in range(0, n, 16):
        yield ",".join(str(v) for v in raw[i:i + 16])
    yield "#done"


def _levels(tok, first):
    lev = [max(0, min(4095, int(float(x)))) for x in tok[first:first + 4]]
    return lev or [0]


def _cmd_txgo(m, tok, io):
    if len(tok) < 4:
        yield "#err usage: txgo <ch> <period_us> <L0> [L1 L2 L3]"
        return
    ch, period = _ints(tok, 1), _ints(tok, 2)
    if not (0 <= ch < 5 and period >= 500):
        yield "#err bad channel or period (>= 500 us)"
        return
    lev = _levels(tok, 3)
    syms = [min(int(s), len(lev) - 1) for s in m.tx_buf]
    yield f"#sending {len(syms)} symbols"
    t0 = _now() + 0.001
    p = period / 1e6
    times = t0 + np.arange(len(syms)) * p
    codes = [lev[s] for s in syms]
    m.dac[ch].plan(list(times) + [t0 + len(syms) * p], codes + [0])
    yield from _wait_until(io, t0 + len(syms) * p)
    yield "#done"


def _cmd_txcap(m, tok, io):
    if len(tok) < 6:
        yield "#err usage: txcap <ch> <period_us> <pin> <samples_per_symbol> <L0> [L1 L2 L3]"
        return
    ch, period, pin, sps = (_ints(tok, k) for k in range(1, 5))
    if not (0 <= ch < 5 and 0 <= pin <= 7 and period >= 500 and 1 <= sps <= 32):
        yield "#err bad channel, pin, period (>= 500 us) or samples_per_symbol (1-32)"
        return
    n = len(m.tx_buf) * sps
    if not 1 <= n <= 40000:
        yield "#err symbols x samples_per_symbol must be 1 to 40000"
        return
    lev = _levels(tok, 5)
    syms = [min(int(s), len(lev) - 1) for s in m.tx_buf]
    t0 = _now() + 0.001
    p = period / 1e6
    times = t0 + np.arange(len(syms)) * p
    m.dac[ch].plan(list(times) + [t0 + len(syms) * p], [lev[s] for s in syms] + [0])
    ts = (times[:, None] + (2 * np.arange(sps)[None, :] + 1) * p / (2 * sps)).ravel()
    yield from _wait_until(io, t0 + len(syms) * p)
    raw = m.adc(pin, ts)
    yield f"#interval_us {period / sps:.3f}"
    yield "#cols raw"
    for i in range(0, n, 16):
        yield ",".join(str(v) for v in raw[i:i + 16])
    yield "#done"


def _cmd_button(m, tok, io):
    pin = _ints(tok, 1, 0)
    t_cmd = _now()
    idle = int(np.mean(m.adc(pin, [t_cmd - 0.01])))
    yield f"#idle {idle}"
    while True:
        k = m._key_at([_now()])[0]
        if pin == hw.PIN_TOUCH and k is not None:
            break
        if io.stop:
            yield "#stopped"
            yield "#done"
            return
        if _now() - t_cmd > 20:
            yield "#err no press within 20 s"
            return
        yield None
    yield "#cols raw"
    yield str(int(m.adc(pin, [_now()], 32)[0]))
    yield "#done"


# ------------------------------------------------------- commands you can type
def _paced(m, io, period_s, make_line, header):
    """Print make_line(t) every period_s until stop, then '#done' (like the firmware)."""
    yield header
    t = _now()
    while not io.stop:
        line = make_line(t)
        if line is not None:
            yield line
        t += period_s
        yield from _wait_until(io, t)
    yield "#done"


def _help(m, io):
    yield "EE 105 demo board, firmware 3.0 (simulated). Commands:"
    yield "  module                      which selector position is active"
    yield "  circuits                    touch-panel button and its node voltage (S10 on Module 1, J7/J8 caps on Module 1 end)"
    yield "  divider                     voltage at the divider output A1 (S10 on Module 1, J7/J8 caps on Module 1 end)"
    yield "  temperature                 thermistor temperature from the divider (S10 on Module 1, J7/J8 caps on Module 1 end)"
    yield "  diodes                      diode I-V sweep: V_DAC, V_D, I_D (S10 on Module 2)"
    yield "  transistors                 MOSFET output curves: V_GS, V_DS, I_D (S10 on Module 2)"
    yield "  transfer                    MOSFET transfer curve: V_GS, V_DS, I_D (S10 on Module 2)"
    yield "  light                       LED pair 1 on, photodiode reading (S10 on Module 3, J5 on P1-A)"
    yield "  sensors                     red and infrared PPG (S10 on Module 3)"
    yield "  communications send <text>  send text over light from TX, once a second (S10 on Module 3)"
    yield "  communications receive      print the text received by RX (S10 on Module 3, J5 on A-P2)"
    yield "  stop                        stop the running command"
    yield "  help                        this list"
    yield "#done"


def _module(m, io):
    v = float(np.mean(m.adc(hw.PIN_SELECT, [_now()], 16)) * hw.ADC_V_PER_COUNT)
    pos = hw.selector_position(v)
    label = (hw.selector_line_label(pos) if pos in (1, 2, 3, "CAM", None)
             else "unknown (unexpected voltage)")
    yield f"selector: {label} {v:.2f} V"
    yield "#done"


_NODES = sorted(hw.TOUCH_NODE_V.items(), key=lambda kv: kv[1])
_NODE_CODES = [min(1023, int(round(v / hw.ADC_V_PER_COUNT))) for _, v in _NODES]


def _circuits(m, io):
    def line(t):
        raw = m.adc(hw.PIN_TOUCH, t + np.arange(10) * 0.002)
        if raw.max() - raw.min() > 26:
            return "no button  (A0 is floating)"
        mean = raw.mean()
        k = 0
        while k < 8 and mean > (_NODE_CODES[k] + _NODE_CODES[k + 1]) / 2:
            k += 1
        return f"{_NODES[k][0]}  {mean * hw.ADC_V_PER_COUNT:.3f} V"
    yield from _paced(m, io, 0.2, line, "circuits: press a button on the touch panel (S10 on Module 1, J7 and J8 caps on "
                      "the Module 1 end). Send stop to end.")


def _divider(m, io):
    yield from _paced(m, io, 0.25, lambda t: f"A1 = {np.mean(m.adc(hw.PIN_DIVIDER, [t], 16)) * hw.ADC_V_PER_COUNT:.3f} V",
                      "divider: voltage at the divider output A1 (S10 on Module 1, J7 and J8 caps on the Module 1 end). Send stop to end.")


def _temperature(m, io):
    def line(t):
        v = float(np.mean(m.adc(hw.PIN_DIVIDER, [t], 32)) * hw.ADC_V_PER_COUNT)
        if v < 0.05 or v > 3.25:
            return f"A1 = {v:.3f} V   no thermistor divider? Check the parts in J1-J4 and the J7/J8 caps."
        r_t = hw.thermistor_ohms(v)
        return f"A1 = {v:.3f} V   R_T = {r_t / 1e3:.2f} kOhm   T = {hw.thermistor_celsius(r_t):.1f} C"
    yield from _paced(m, io, 0.5, line, "temperature: 10 kOhm NTC thermistor (beta 3950) in J1-J2, 10 kOhm in "
                      "J3-J4 (S10 on Module 1, J7 and J8 caps on the Module 1 end). Send stop to end.")


def _diodes(m, io):
    yield "diodes: diode I-V sweep (S10 on Module 2). Columns: V_DAC (V), V_D (V), I_D (mA)"
    t = _now()
    for code in range(0, 2001, 10):
        m.dac[hw.DAC_DIODE].set(t, code)
        v_r = float(m.adc(hw.PIN_DIODE, [t + 0.002], 4)[0] * hw.ADC_V_PER_COUNT)
        v_dac = code * hw.DAC_V_PER_CODE
        yield f"{v_dac:.3f}, {v_dac - v_r:.3f}, {v_r:.3f}"
        t += 0.002
        if io.stop:
            break
    m.dac[hw.DAC_DIODE].set(t, 0)
    yield "#done"


def _nmos_line(m, t, gate, drain):
    v_a3 = float(m.adc(hw.PIN_NMOS, [t], 4)[0] * hw.ADC_V_PER_COUNT)
    return f"{gate * hw.DAC_V_PER_CODE:.3f}, {drain * hw.DAC_V_PER_CODE - v_a3:.3f}, {v_a3:.3f}"


def _transistors(m, io):
    yield "transistors: MOSFET output curves (S10 on Module 2). Columns: V_GS (V), V_DS (V), I_D (mA)"
    t = _now()
    for k in range(9):                                   # V_GS = 1.2, 1.3, ... 2.0 V
        gate = int((1.2 + 0.1 * k) / hw.DAC_V_PER_CODE + 0.5)
        m.dac[hw.DAC_GATE].set(t, gate)
        for d in range(0, 2001, 20):
            m.dac[hw.DAC_DRAIN].set(t, d)
            yield _nmos_line(m, t + 0.002, gate, d)
            t += 0.002
            if io.stop:
                break
        if io.stop:
            break
    for ch in (hw.DAC_GATE, hw.DAC_DRAIN):
        m.dac[ch].set(t, 0)
    yield "#done"


def _transfer(m, io):
    yield "transfer: MOSFET transfer curve, V_DAC2 = 3.3 V (S10 on Module 2). Columns: V_GS (V), V_DS (V), I_D (mA)"
    t = _now()
    m.dac[hw.DAC_DRAIN].set(t, 2000)
    for g in range(0, 2001, 10):
        m.dac[hw.DAC_GATE].set(t, g)
        yield _nmos_line(m, t + 0.002, g, 2000)
        t += 0.002
        if io.stop:
            break
    for ch in (hw.DAC_GATE, hw.DAC_DRAIN):
        m.dac[ch].set(t, 0)
    yield "#done"


def _light(m, io):
    yield "light: LED pair 1 on, photodiode on A6 (S10 on Module 3, J5 on P1-A). Send stop to end."
    t = _now()
    m.dac[hw.DAC_LED1].set(t, 2000)
    while not io.stop:
        counts = float(np.mean(m.adc(hw.PIN_PD, [t + 0.002], 16)))
        v = counts * hw.ADC_V_PER_COUNT
        yield f"A6 = {counts:.0f} counts = {v:.3f} V, photocurrent {v / 3e6 * 1e9:.0f} nA"
        t += 0.25
        yield from _wait_until(io, t)
    m.dac[hw.DAC_LED1].set(_now(), 0)               # LED off before "#done" ends the command
    yield "#done"


def _sensors(m, io):
    yield "sensors: red and infrared PPG from the MAX86916 (S10 on Module 3). Send stop to end."
    t0 = _now()
    while not io.stop:
        t, ir, red = m.ppg(64, t0)
        for j in range(64):
            yield from _wait_until(io, t0 + t[j])
            if io.stop:
                break
            yield f"red:{int(red[j])},ir:{int(ir[j])}"
        t0 += t[-1] + 1 / 131
    yield "#done"


def _comm_send(m, io, text=""):
    text = (text or "This is a test transmission!")[:200]
    yield f'communications send: "{text}" once a second on LED pair 2 (S10 on Module 3). Send stop to end.'
    msg = text + "\n"
    P = 0.003
    while not io.stop:
        t = _now() + 0.001
        times, codes = [], []
        for ch in msg.encode("latin-1", errors="replace"):
            seq = [0] + [2000 if (ch >> i) & 1 else 0 for i in range(8)] + [2000]
            for code in seq:
                times.append(t)
                codes.append(code)
                t += P
        times.append(t)
        codes.append(2000)                      # the LED stays on between messages, as on the board
        m.dac[hw.DAC_LED2].plan(times, codes)
        yield from _wait_until(io, t + 1.0)
    m.dac[hw.DAC_LED2].set(_now(), 0)
    yield "#done"


def _comm_receive(m, io):
    yield "communications receive: text from photodiode pair 2 (S10 on Module 3, J5 on A-P2). Send stop to end."
    P = 0.003
    thr = 200
    cursor = _now()
    prev = False
    buf = ""
    while not io.stop:
        end = _now()
        if end - cursor < 0.05:
            yield None
            continue
        grid = np.arange(cursor, end, 50e-6)
        on = m.photodiode_counts(grid) > thr
        i = 0
        while i < len(grid):
            cur = bool(on[i])
            if prev and not cur:
                tb = grid[i] + 1.5 * P
                if tb + 8 * P > end:          # the byte is not complete yet
                    break
                bits = m.photodiode_counts(tb + np.arange(8) * P) > thr
                buf += chr(sum(int(bit) << k for k, bit in enumerate(bits)))
                tnext = tb + 8 * P
                i = int(np.searchsorted(grid, tnext))
                prev = bool(on[min(i, len(on) - 1)])
                continue
            prev = cur
            i += 1
        cursor = grid[i] if i < len(grid) else end
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            yield line
    if buf:
        yield buf
    yield "#done"


_TYPED = {
    "help": _help, "module": _module,
    "circuits": _circuits, "m1na": _circuits,
    "divider": _divider, "m1vd": _divider,
    "temperature": _temperature,
    "diodes": _diodes, "m2d": _diodes, "m2draw": _diodes,
    "transistors": _transistors, "m2tran_vds": _transistors,
    "transfer": _transfer, "m2tran_vgs": _transfer,
    "light": _light, "m3pdcurrent": _light, "show_pd": _light, "m3led": _light, "m3stepled": _light,
    "sensors": _sensors, "m3ppg": _sensors,
    "lifi_tx": lambda m, io: _comm_send(m, io, ""), "lifi_rx": _comm_receive,
}
