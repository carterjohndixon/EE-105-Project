"""Live plots and a serial monitor inside the notebook (no Serial Monitor or Plotter window needed)."""
import re
import time

import numpy as np

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


CARDINAL, SLATE, STEEL, GOLD, PAPER = "#990000", "#4A5560", "#5B8DB8", "#E0A800", "#F5F2EC"


def interactive():
    """True when a person is watching: artificial delays and animations are allowed.
    tools/runsim.py sets EE105_FAST=1, so automatic runs never wait for show."""
    import os
    return os.environ.get("EE105_FAST", "") != "1"


def in_notebook():
    """True inside IPython/Jupyter (live figures can be updated in place); False in plain Python."""
    try:
        from IPython import get_ipython
        return get_ipython() is not None
    except Exception:
        return False


def _ip_display(fig):
    """Display a figure and return a handle whose update(fig) redraws it in place."""
    from IPython.display import display
    return display(fig, display_id=True)


def live_plot(source, seconds=10, labels=None, window_s=None, title=None, ylabel=None,
              refresh_s=0.3, separate=False, text=None, annotate=None, gauge=None):
    """Plot values from `source` as they arrive, for `seconds` (press the stop button to end early).

    source : an iterator of tuples (t_s, y1, y2, ...), for example board.stream(1)
    labels : names of y1, y2, ...
    window_s : show only the last window_s seconds while recording (default: everything,
               or the last 10 s for recordings longer than 20 s)
    separate : one panel per signal (useful when the signals have different sizes)
    text : function of the latest tuple that returns a string: shown in large type in the
           corner of the plot (for example the value in volts, or a decoded button)
    annotate : function of the data so far (a 2-D array, one row per sample: t, y1, y2, ...)
           that returns a dict with any of
             "title": extra title text        "text": corner text (instead of `text`)
             "marks": [(t, y, panel), ...]    points to mark (for example detected beats)
             "beat": True                     the heart in the corner lights up
             "gauge": value                   the value the gauge shows
    gauge : a bar on the right that shows the latest value:
             "touch"      a 0 to 3.3 V bar with the nine touch-panel levels and the pressed pad
             "volts"      a 0 to 3.3 V bar
             dict(range=(lo, hi), unit="°C", value=f, levels={name: level}, title=...)
                          f(row) gives the value (default: y1)
    Returns all samples as a pandas DataFrame with columns t_s and the labels.
    In plain Python (no notebook) it prints a line now and then instead of drawing.
    """
    import pandas as pd
    import time as _time

    rows = []
    notebook = in_notebook()
    view = None
    if window_s is None:
        window_s = None if seconds <= 20 else 10.0
    if not interactive():
        refresh_s = max(refresh_s, 1.0)              # automatic run: few redraws
    ncol = None
    names = None
    last_print = [0.0]

    def draw(final=False):
        nonlocal view
        data = np.asarray(rows, dtype=float)
        extra = annotate(data) if annotate is not None else {}
        corner = extra.get("text")
        if corner is None and text is not None:
            corner = text(rows[-1])
        if not notebook:
            now = _time.time()
            if final or now - last_print[0] >= max(1.0, refresh_s):
                last_print[0] = now
                vals = "  ".join(f"{n} {v:g}" for n, v in zip(names, data[-1, 1:]))
                print(f"t = {data[-1, 0]:6.2f} s  {vals}" + (f"  {corner}" if corner else "")
                      + (f"  {extra['title']}" if extra.get("title") else ""))
            return
        if view is None:
            view = _LiveView(names, separate=separate, title=title, ylabel=ylabel, gauge=gauge, seconds=seconds)
        view.update(data, window_s if not final else None, corner, extra, final)

    t_end = _time.time() + seconds * 1.5 + 5          # safety stop on the wall clock
    next_draw = _time.time() + refresh_s
    try:
        for item in source:
            rows.append(tuple(float(v) for v in item))
            if ncol is None:
                ncol = len(rows[0]) - 1
                names = list(labels or [f"y{i + 1}" for i in range(ncol)])[:ncol]
                names += [f"y{i + 1}" for i in range(len(names), ncol)]
            now = _time.time()
            if now >= next_draw:
                draw()
                next_draw = _time.time() + refresh_s      # measured from the end of the redraw
            if rows[-1][0] - rows[0][0] >= seconds or now >= t_end:
                break
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        close = getattr(source, "close", None)
        if close:
            close()
    if not rows:
        print("No data arrived.")
        return pd.DataFrame(columns=["t_s"] + list(labels or ["y1"]))
    draw(final=True)
    if view is not None:
        view.close()
    return pd.DataFrame(rows, columns=["t_s"] + names)


class _LiveView:
    """The figure of live_plot: time panels, a large value in the corner, a heart, marks, a gauge."""

    def __init__(self, names, separate, title, ylabel, gauge, seconds):
        import matplotlib.pyplot as plt
        self.names, self.separate, self.title = names, separate, title or ""
        self.seconds = seconds
        npanel = len(names) if separate else 1
        self.gauge = _gauge_spec(gauge)
        height = 2.4 + 1.5 * npanel
        if self.gauge:
            fig = plt.figure(figsize=(10.5, height))
            gs = fig.add_gridspec(npanel, 2, width_ratios=[6, 1.25], wspace=0.28)
            axes = [fig.add_subplot(gs[i, 0]) for i in range(npanel)]
            if self.gauge.get("pads"):
                sub = gs[:, 1].subgridspec(2, 1, height_ratios=[1, 2.6], hspace=0.6)
                self.pad_ax = fig.add_subplot(sub[0])
                self.gauge_ax = fig.add_subplot(sub[1])
            else:
                self.pad_ax = None
                self.gauge_ax = fig.add_subplot(gs[:, 1])
        else:
            fig, axes = plt.subplots(npanel, 1, figsize=(10, height), squeeze=False)
            axes = list(axes[:, 0])
            self.gauge_ax = self.pad_ax = None
        for ax in axes[1:]:
            ax.sharex(axes[0])
        self.fig, self.axes = fig, axes
        self.lines, self.markers = [], []
        colors = [STEEL, CARDINAL, SLATE, GOLD]
        for i, name in enumerate(names):
            ax = axes[i if separate else 0]
            (ln,) = ax.plot([], [], lw=1.3, color=colors[i % len(colors)], label=name)
            (mk,) = ax.plot([], [], "o", ms=6, color=CARDINAL, mfc="white", mew=1.5, zorder=5)
            self.lines.append(ln)
            self.markers.append(mk)
            ax.grid(alpha=0.3)
            if separate:
                ax.set_ylabel(name)
        if not separate:
            axes[0].set_ylabel(ylabel or "")
            if len(names) > 1:
                axes[0].legend(loc="upper left", fontsize=9, frameon=False)
        axes[-1].set_xlabel("time (s)")
        for ax in axes[:-1]:
            ax.tick_params(labelbottom=False)
        self.corner = axes[0].text(0.985, 0.92, "", transform=axes[0].transAxes, ha="right", va="top",
                                   fontsize=15, fontweight="bold", color=SLATE,
                                   bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.8", alpha=0.9), zorder=6)
        self.heart = axes[0].text(0.012, 0.92, "", transform=axes[0].transAxes, ha="left", va="top",
                                  fontsize=22, color=CARDINAL, zorder=6)
        self.progress = axes[-1].text(0.995, 0.03, "", transform=axes[-1].transAxes, ha="right", va="bottom",
                                      fontsize=8, color="0.5")
        self._gauge_setup()
        if not self.gauge:
            fig.tight_layout()
        else:
            fig.subplots_adjust(left=0.08, right=0.97, top=0.9, bottom=0.14)
        self.handle = _ip_display(fig)
        plt.close(fig)

    def _gauge_setup(self):
        g, ax = self.gauge, self.gauge_ax
        if not g:
            return
        lo, hi = g["range"]
        ax.set_xlim(0, 1)
        ax.set_ylim(lo, hi)
        ax.set_xticks([])
        ax.spines[["top", "right", "bottom"]].set_visible(False)
        self.bar = ax.bar([0.5], [0], width=0.5, bottom=lo, color=g.get("color", STEEL), zorder=3)[0]
        self.bulb = None
        if g.get("kind") == "thermometer":
            self.bar.set_width(0.3)
            self.bulb = ax.scatter([0.5], [lo], s=420, color=g.get("color", CARDINAL), zorder=4, clip_on=False)
        self.level_labels = {}
        if g.get("levels"):
            items = sorted(g["levels"].items(), key=lambda kv: kv[1])
            gap = 0.045 * (hi - lo)                       # keep the names from overlapping
            pos, last = {}, None
            for name, lvl in items:
                y = lvl if last is None else max(lvl, last + gap)
                pos[name], last = y, y
            for name, lvl in items:
                ax.axhline(lvl, color="0.75", lw=0.8, zorder=2)
                self.level_labels[name] = ax.text(1.04, pos[name], name, ha="left", va="center", fontsize=8,
                                                  color="0.45", transform=ax.get_yaxis_transform(), clip_on=False)
            ax.set_yticks([lo, (lo + hi) / 2, hi])
            ax.tick_params(axis="y", labelsize=7)
        ax.set_ylabel(g.get("unit", ""), fontsize=9)
        if self.pad_ax is not None:
            pads = g["pads"]
            self.pad_ax.set_xlim(-0.5, 2.5)
            self.pad_ax.set_ylim(2.5, -0.5)
            self.pad_ax.set_aspect("equal")
            self.pad_ax.set_axis_off()
            from matplotlib.patches import Rectangle
            self.pad_patches = {}
            for name, (r, c) in pads.items():
                p = Rectangle((c - 0.42, r - 0.42), 0.84, 0.84, fc="white", ec="0.6", lw=0.8)
                self.pad_ax.add_patch(p)
                self.pad_ax.text(c, r, name, ha="center", va="center", fontsize=7, color="0.4")
                self.pad_patches[name] = p

    def update(self, data, window_s, corner, extra, final):
        t = data[:, 0]
        keep = slice(None)
        if window_s:
            keep = t >= t[-1] - window_s
        for i, ln in enumerate(self.lines):
            ln.set_data(t[keep], data[keep, i + 1])
        marks = extra.get("marks") or []
        for i, mk in enumerate(self.markers):
            pts = [(x, y) for x, y, p in marks if p == i]        # marks of signal i
            if pts:
                xs, ys = zip(*pts)
                if window_s:
                    sel = np.asarray(xs) >= t[-1] - window_s
                    xs, ys = np.asarray(xs)[sel], np.asarray(ys)[sel]
                mk.set_data(xs, ys)
            else:
                mk.set_data([], [])
        for ax in self.axes:
            ax.relim()
            ax.autoscale_view()
        head = self.title
        if extra.get("title"):
            head = (head + "   " if head else "") + str(extra["title"])
        self.axes[0].set_title(head, loc="left")
        self.corner.set_text(corner or "")
        if "beat" in extra:
            self.heart.set_text("\u2665")
            self.heart.set_fontsize(26 if extra["beat"] else 15)
            self.heart.set_color(CARDINAL if extra["beat"] else "#d9b3b3")
        t_now = t[-1] - t[0]
        self.progress.set_text(f"{t_now:.0f} of {self.seconds:g} s" if not final else f"{t_now:.1f} s recorded")
        if self.gauge:
            g = self.gauge
            value = extra.get("gauge")
            if value is None:
                value = g["value"](data[-1]) if g.get("value") else data[-1, 1]
            lo, hi = g["range"]
            v = float(np.clip(value, lo, hi))
            self.bar.set_height(v - lo)
            self.gauge_ax.set_title(g["fmt"].format(value) if g.get("fmt") else f"{value:.2f} {g.get('unit', '')}",
                                    fontsize=11, fontweight="bold", color=SLATE)
            if g.get("levels"):
                near = min(g["levels"], key=lambda n: abs(g["levels"][n] - value))
                hit = abs(g["levels"][near] - value) <= g.get("tol", 0.06)
                for name, lab in self.level_labels.items():
                    on = hit and name == near
                    lab.set_color(CARDINAL if on else "0.45")
                    lab.set_fontweight("bold" if on else "normal")
                if self.pad_ax is not None:
                    for name, p in self.pad_patches.items():
                        p.set_facecolor(GOLD if (hit and name == near) else "white")
                    self.pad_ax.set_title(near if hit else "no press", fontsize=9,
                                          color=CARDINAL if hit else "0.5")
        self.handle.update(self.fig)

    def close(self):
        pass


def _gauge_spec(gauge):
    if not gauge:
        return None
    from . import hardware as hw
    if gauge == "touch":
        pads = {f"S{k + 1}": divmod(k, 3) for k in range(9)}
        return {"range": (0, 3.3), "unit": "V", "levels": dict(hw.TOUCH_NODE_V), "pads": pads, "tol": 0.07,
                "title": "A0", "color": STEEL}
    if gauge == "volts":
        return {"range": (0, 3.3), "unit": "V", "title": "", "color": STEEL}
    if gauge == "thermometer":
        return {"kind": "thermometer", "range": (15, 40), "unit": "°C", "fmt": "{:.1f} °C", "color": CARDINAL}
    g = dict(gauge)
    g.setdefault("range", (0, 3.3))
    if g.get("kind") == "thermometer" or g.get("unit") in ("°C", "C"):
        g.setdefault("kind", "thermometer")
        g.setdefault("color", CARDINAL)
        g.setdefault("fmt", "{:.1f} " + g.get("unit", "°C"))
    return g


# ------------------------------------------------------------------ live I-V sweeps
class LiveIV:
    """A curve that grows point by point while a sweep runs (board.sweep(..., live=True)).

        view = LiveIV("DAC (V)", "A2 (V)", title="Diode sweep")
        view.add(x, y)            # or view.add(x, y, series="V_GS = 1.6 V") for several curves
        view.finish()
    Outside a notebook it prints a short line now and then instead.
    """

    def __init__(self, xlabel, ylabel, title="", refresh_s=0.08, xlim=None, ylim=None):
        import time as _time
        self.notebook = in_notebook()
        self.series, self.order = {}, []
        self.xlabel, self.ylabel, self.title = xlabel, ylabel, title
        self.refresh_s, self.next = (refresh_s if interactive() else max(refresh_s, 1.0)), 0.0
        self.n = 0
        self._time = _time
        self.fig = None
        self.xlim, self.ylim = xlim, ylim

    def _setup(self):
        import matplotlib.pyplot as plt
        self.fig, self.ax = plt.subplots(figsize=(7.5, 4.2))
        self.ax.set_xlabel(self.xlabel)
        self.ax.set_ylabel(self.ylabel)
        self.ax.grid(alpha=0.3)
        if self.xlim:
            self.ax.set_xlim(*self.xlim)
        if self.ylim:
            self.ax.set_ylim(*self.ylim)
        (self.dot,) = self.ax.plot([], [], "o", ms=9, color=CARDINAL, mfc=GOLD, mew=1.5, zorder=6)
        self.label = self.ax.text(0.985, 0.95, "", transform=self.ax.transAxes, ha="right", va="top", fontsize=12,
                                  fontweight="bold", color=SLATE,
                                  bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.8", alpha=0.9))
        self.fig.tight_layout()
        self.handle = _ip_display(self.fig)
        plt.close(self.fig)

    def add(self, x, y, series=None):
        import matplotlib.pyplot as plt
        key = series or ""
        if key not in self.series:
            if self.notebook and self.fig is None:
                self._setup()
            if self.notebook:
                color = CARDINAL if not series else plt.get_cmap("viridis")(min(1.0, 0.1 + 0.11 * len(self.order)))
                (ln,) = self.ax.plot([], [], "-", lw=1.4, color=color, label=series)
                self.series[key] = (ln, [], [])
                if series:
                    self.ax.legend(loc="upper left", fontsize=8, frameon=False)
            else:
                self.series[key] = (None, [], [])
            self.order.append(key)
        ln, xs, ys = self.series[key]
        xs.append(float(x))
        ys.append(float(y))
        self.n += 1
        if self._time.time() >= self.next:
            self._draw(key, final=False)
            self.next = self._time.time() + (self.refresh_s if self.notebook else 1.0)

    def _draw(self, key, final):
        ln, xs, ys = self.series[key]
        if not self.notebook:
            print(f"   {self.n} points" + (f", {key}" if key else "") + f": x = {xs[-1]:.3f}, y = {ys[-1]:.4f}")
            return
        for k, (l, a, b) in self.series.items():
            l.set_data(a, b)
        self.dot.set_data([] if final else [xs[-1]], [] if final else [ys[-1]])
        self.label.set_text(f"{self.n} points" if final else (f"{key}   " if key else "") + f"{xs[-1]:.2f} V -> {ys[-1]:.3f} V")
        self.ax.set_title(self.title + ("" if final else "  (measuring ...)"), loc="left")
        self.ax.relim()
        self.ax.autoscale_view()
        self.handle.update(self.fig)

    def finish(self):
        if self.order:
            self.next = 0.0
            self._draw(self.order[-1], final=True)


# ------------------------------------------------------------------ received bits (LiFi)
def bits_strip(sent, received, bits_per_char=8, chars_per_row=6, title="Received bits", animate=True):
    """Draw the received bits as a strip: one small square per bit (dark = 1, light = 0), eight bits per
    character with the decoded character under each byte, errors framed in red. With `animate` (and a
    person watching) the strip fills in byte by byte; the final figure stays.
    sent, received: strings of 0 and 1 of the same length (the whole frame). Returns the number of errors.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    sent, received = str(sent), str(received)
    n = min(len(sent), len(received))
    n_bytes = -(-n // bits_per_char)
    rows = -(-n_bytes // chars_per_row)
    x_range = chars_per_row * (bits_per_char + 1.2) - 1.2 + 0.6
    y_range = rows * 2.0 + 0.4
    fig_w = 10.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * y_range / x_range + 0.6))
    ax.set_xlim(-0.3, x_range - 0.3)
    ax.set_ylim(y_range - 0.6, -0.8)
    ax.set_aspect("equal")
    ax.set_axis_off()
    cells, errors = [], 0
    for b in range(n_bytes):
        r, c = divmod(b, chars_per_row)
        x0, y0 = c * (bits_per_char + 1.2), r * 2.0
        byte = received[b * bits_per_char:(b + 1) * bits_per_char]
        code = int(byte.ljust(bits_per_char, "0"), 2)
        ch = chr(code) if 32 <= code < 127 else "·"
        group = []
        for k, bit in enumerate(byte):
            wrong = bit != sent[b * bits_per_char + k]
            errors += wrong
            p = Rectangle((x0 + k, y0), 0.92, 0.92, fc=(SLATE if bit == "1" else "#e9e6df"),
                          ec=(CARDINAL if wrong else "none"), lw=2 if wrong else 0, visible=False)
            ax.add_patch(p)
            group.append(p)
        label = ax.text(x0 + bits_per_char / 2 - 0.5, y0 + 1.42, ch, ha="center", va="center", fontsize=8,
                        color=SLATE, family="monospace", visible=False)
        cells.append((group, label))
    summary = f"{n} bits, {n_bytes} bytes, {errors} bit error{'s' if errors != 1 else ''}"
    live = animate and interactive() and in_notebook()
    handle = _ip_display(fig) if live else None
    import time as _time
    for i, (group, label) in enumerate(cells):
        for p in group:
            p.set_visible(True)
        label.set_visible(True)
        if live and (i % 2 == 1 or i == len(cells) - 1):
            ax.set_title(f"{title}   ({i + 1} of {n_bytes} bytes)", loc="left", fontsize=11)
            handle.update(fig)
            _time.sleep(0.12)
    ax.set_title(f"{title}   ({summary})", loc="left", fontsize=11)
    if live:
        handle.update(fig)
        plt.close(fig)
    else:
        plt.show()
    return errors


# ------------------------------------------------------- plain serial helpers
def _simulated():
    import os
    return os.environ.get("EE105_SIMULATE") == "1"


def _open(port=None, baud=115200):
    from . import arduino, board
    arduino.ensure_pyserial()
    import serial
    port = port or arduino.find_port(wait=3)
    if not port:
        raise RuntimeError("No Arduino found. Plug in the USB cable.")
    board.release_port(port)
    ser = serial.Serial(port, baud, timeout=0.1)
    return ser


def monitor(seconds=5, port=None, baud=115200, send=None, max_lines=60, quiet=False):
    """Serial Monitor in the notebook for your own sketches.

    Prints what the board sends for `seconds`. `send` is a line (or list of lines) to send first.
    Returns the list of lines.
    """
    if _simulated():
        print("(simulator: your own sketches only run on a real board, so there is no output here)")
        return []
    ser = _open(port, baud)
    lines, buf = [], b""
    try:
        time.sleep(0.2)
        if send:
            for s in ([send] if isinstance(send, str) else send):
                ser.write((s.strip() + "\n").encode())
        t_end = time.time() + seconds
        while time.time() < t_end:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="replace").rstrip("\r")
                lines.append(line)
                if not quiet and len(lines) <= max_lines:
                    print(line, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
    if buf.strip():
        lines.append(buf.decode(errors="replace").strip())
        if not quiet and len(lines) <= max_lines:
            print(lines[-1])
    if not quiet and len(lines) > max_lines:
        print(f"... {len(lines)} lines in total (all of them are in the returned list)")
    if not quiet and not lines:
        print("(nothing received; check the baud rate and that the sketch calls Serial.begin)")
    return lines


def serial_values(port=None, baud=115200):
    """Generator of (t_s, v1, v2, ...) from a sketch that prints numbers, one line per reading."""
    if _simulated():
        print("(simulator: your own sketches only run on a real board, so there is no data here)")
        return
    ser = _open(port, baud)
    t0 = time.time()
    buf = b""
    try:
        while True:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                nums = _NUM.findall(raw.decode(errors="replace"))
                if nums:
                    yield (time.time() - t0, *[float(x) for x in nums])
    finally:
        ser.close()


def serial_plot(seconds=10, port=None, baud=115200, labels=None, **kw):
    """Serial Plotter in the notebook: live plot of the numbers your sketch prints.

    Each line the sketch prints (for example "512" or "1.65,2.10") becomes one point per number.
    Returns the data as a DataFrame.
    """
    first = None
    gen = serial_values(port, baud)

    def consistent():
        nonlocal first
        for item in gen:
            if first is None:
                first = len(item)
            if len(item) == first:
                yield item
    src = consistent()
    try:
        return live_plot(src, seconds=seconds, labels=labels, **kw)
    finally:
        gen.close()


def record(seconds=2, port=None, baud=115200, labels=None):
    """Collect the numbers your sketch prints for `seconds` (no plot). Returns a DataFrame."""
    import pandas as pd
    rows = []
    gen = serial_values(port, baud)
    t_end = time.time() + seconds
    try:
        for item in gen:
            rows.append(item)
            if time.time() >= t_end:
                break
    finally:
        gen.close()
    if not rows:
        return pd.DataFrame(columns=["t_s"] + list(labels or ["y1"]))
    width = max(set(len(r) for r in rows), key=[len(r) for r in rows].count)
    rows = [r for r in rows if len(r) == width]
    names = list(labels or [f"y{i + 1}" for i in range(width - 1)])[:width - 1]
    names += [f"y{i + 1}" for i in range(len(names), width - 1)]
    return pd.DataFrame(rows, columns=["t_s"] + names)
