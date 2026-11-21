"""The OV7675 camera on header J6 of the demo board, from a notebook.

Selector S10 on Camera, both caps of jumpers J7 and J8 on the Camera end, pins 1-2 (put them back on
the Module 1 end, pins 2-3, after the lab).

    cam = ee105.connect_camera()          # uploads the camera firmware if needed
    cam.check_module("CAM")               # warns if the selector S10 does not read Camera
    img = cam.snap()                      # 120 x 160 grayscale numpy array (0..255)
    x = ee105.camera.to_digit(img)        # 28 x 28, white digit on black, like MNIST
"""
import base64
import time
from pathlib import Path

import numpy as np

from . import hardware as hw
from .board import Board, BoardError, _connect

CAM_DIR = Path(__file__).resolve().parent.parent / "firmware" / "ee105_camera"


class Camera(Board):
    """The demo board's Nano 33 BLE Sense with the OV7675 camera on J6, running the ee105_camera firmware."""
    FW_NAME, FW_VERSION, FW_DIR, KIND = "ee105cam", "2.2", CAM_DIR, "camera"

    def snap(self, width=160, height=120, timeout=10):
        """One grayscale picture as a (height, width) uint8 array."""
        self.begin(f"snap {int(width)} {int(height)}")
        size, data = None, None
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self._readline()
            if line is None:
                continue
            if line.startswith("#done"):
                break
            if line.startswith("#err"):
                raise BoardError(line[4:].strip())
            if line.startswith("#size"):
                w, h = (int(v) for v in line.split()[1:3])
                size = (h, w)
            elif not line.startswith("#") and size:
                data = line.strip()
        else:
            raise TimeoutError("The camera did not send a picture. Press RESET on the Arduino and connect again.")
        if data is None:
            raise BoardError("no picture data received")
        pix = np.frombuffer(base64.b64decode(data), dtype=np.uint8)
        return pix[:size[0] * size[1]].reshape(size)

    def show(self, img=None, title=None, ax=None):
        """Show a picture (takes a new one if img is None)."""
        import matplotlib.pyplot as plt
        img = self.snap() if img is None else img
        if ax is None:
            fig, ax = plt.subplots(figsize=(4.5, 3.6))
        ax.imshow(img, cmap="gray", vmin=0, vmax=255)
        ax.set_axis_off()
        if title:
            ax.set_title(title)
        return img

    def live(self, seconds=20, width=160, height=120, process=None, every=1):
        """Live view for `seconds`. process(img) may return a title string (for example a prediction).

        The corner shows the picture count and the rate; the stop button ends the view early.
        Returns the last picture.
        """
        import matplotlib.pyplot as plt
        from .live import in_notebook, _ip_display
        notebook = in_notebook()
        img = self.snap(width, height)
        if notebook:
            fig, ax = plt.subplots(figsize=(5.2, 4.3))
            im = ax.imshow(img, cmap="gray", vmin=0, vmax=255)
            ax.set_axis_off()
            ax.set_title("live view", loc="left", fontsize=12)
            corner = ax.text(0.99, 0.99, "", transform=ax.transAxes, ha="right", va="top", fontsize=9,
                             color="white", bbox=dict(boxstyle="round,pad=0.25", fc="#4A5560", ec="none", alpha=0.85))
            foot = ax.text(0.01, 0.01, "", transform=ax.transAxes, ha="left", va="bottom", fontsize=8,
                           color="white", bbox=dict(boxstyle="round,pad=0.2", fc="#4A5560", ec="none", alpha=0.7))
            handle = _ip_display(fig)
            plt.close(fig)
        t0 = time.time()
        t_end = t0 + seconds
        k, title = 0, ""
        try:
            while time.time() < t_end:
                img = self.snap(width, height)
                k += 1
                if process is not None and k % every == 0:
                    title = str(process(img))
                rate = k / max(1e-6, time.time() - t0)
                if notebook:
                    im.set_data(img)
                    if title:
                        ax.set_title(title, loc="left", fontsize=12)
                    corner.set_text(f"picture {k}   {rate:.1f} per s")
                    foot.set_text(f"{time.time() - t0:.0f} of {seconds:g} s   mean {img.mean():.0f}")
                    handle.update(fig)
                elif k % 5 == 1:
                    print(f"picture {k} ({rate:.1f} per s), mean {img.mean():.0f}" + (f"   {title}" if title else ""))
        except KeyboardInterrupt:
            pass
        if notebook:
            corner.set_text(f"{k} pictures in {time.time() - t0:.0f} s ({k / max(1e-6, time.time() - t0):.1f} per s)")
            handle.update(fig)
        return img

    def test_pattern(self, on=True):
        self.query(f"test {1 if on else 0}", timeout=3)


def connect_camera(port=None, upload_firmware=True, simulate=None, quiet=False):
    """Connect to the camera board (simulate=True gives a simulated camera that sees digits)."""
    def make_sim():
        return SimCameraSerial()
    return _connect(Camera, make_sim, port, upload_firmware, simulate, quiet)


# -------------------------------------------------------------- preprocessing
def center_square(img, fraction=0.8):
    """Center square crop whose side is `fraction` of the picture height."""
    h, w = img.shape
    s = max(1, int(round(min(h, w) * fraction)))
    y0, x0 = (h - s) // 2, (w - s) // 2
    return img[y0:y0 + s, x0:x0 + s]


def resize(img, size):
    """Resize with area averaging (PIL if available)."""
    try:
        from PIL import Image
        return np.asarray(Image.fromarray(img.astype(np.uint8)).resize((size, size), Image.BILINEAR),
                          dtype=np.float32)
    except ImportError:
        idx = (np.arange(size) * img.shape[0] / size).astype(int)
        jdx = (np.arange(size) * img.shape[1] / size).astype(int)
        return img[np.ix_(idx, jdx)].astype(np.float32)


def to_digit(img, size=28, fraction=0.8, contrast=True):
    """Turn a camera picture of a dark digit on paper into an MNIST-style input.

    Crops the center, resizes to size x size, makes the digit white on black,
    and stretches the contrast so the background is 0 and the strokes near 1.
    Returns a float32 array in [0, 1].
    """
    x = resize(center_square(img, fraction), size) / 255.0
    if x.mean() > 0.5:                   # paper is bright: invert so the digit is bright
        x = 1.0 - x
    if contrast:
        lo = np.percentile(x, 50)        # most of the picture is background
        hi = np.percentile(x, 99.5)
        x = np.clip((x - lo) / max(hi - lo, 1e-3), 0, 1)
    return x.astype(np.float32)


# ------------------------------------------------------------- simulation
class SimCamera:
    """A pretend camera looking at a handwritten digit on a sheet of paper.

    digit : which digit (0..9) is on the paper; None picks a new random one each picture
    last_digit : the digit in the most recent picture (to check a classifier)
    """

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.digit = None
        self.last_digit = None
        self.test = False
        self.selector = "CAM"              # the simulated selector S10 (set it to test check_module)
        self._mnist = None

    def _mnist_digit(self, d):
        if self._mnist is None:
            try:
                from .datasets import load_mnist
                self._mnist = load_mnist("test")
            except Exception:
                self._mnist = False
        if self._mnist is False:
            return None
        X, y = self._mnist
        idx = np.nonzero(y == d)[0]
        return X[self.rng.choice(idx)] if len(idx) else None

    def _font_digit(self, d):
        from PIL import Image, ImageDraw, ImageFont
        im = Image.new("L", (28, 28), 0)
        dr = ImageDraw.Draw(im)
        try:
            font = ImageFont.load_default(size=24)
        except TypeError:
            font = ImageFont.load_default()
        dr.text((14, 14), str(d), fill=255, font=font, anchor="mm")
        return np.asarray(im)

    def picture(self, w, h):
        W, H = 320, 240
        if self.test:
            bars = np.tile(np.repeat(np.linspace(0, 255, 8), W // 8), (H, 1))
            frame = bars.astype(np.uint8)
        else:
            d = self.digit if self.digit is not None else int(self.rng.integers(10))
            self.last_digit = d
            g = self._mnist_digit(d)
            if g is None:
                g = self._font_digit(d)
            from PIL import Image
            side = int(H * self.rng.uniform(0.55, 0.7))
            glyph = Image.fromarray(g.astype(np.uint8)).rotate(self.rng.uniform(-8, 8), resample=Image.BILINEAR)
            glyph = np.asarray(glyph.resize((side, side), Image.BILINEAR), dtype=float) / 255.0
            yy, xx = np.mgrid[0:H, 0:W]
            paper = 185 + 25 * (1 - ((xx - W / 2) ** 2 + (yy - H / 2) ** 2) / (W * W / 2))   # vignette
            paper += 10 * (xx / W - 0.5)                                                    # light gradient
            y0 = (H - side) // 2 + int(self.rng.integers(-8, 9))
            x0 = (W - side) // 2 + int(self.rng.integers(-10, 11))
            ink = 40.0
            region = paper[y0:y0 + side, x0:x0 + side]
            paper[y0:y0 + side, x0:x0 + side] = region * (1 - glyph) + ink * glyph
            paper += self.rng.normal(0, 4, paper.shape)
            frame = np.clip(paper, 0, 255).astype(np.uint8)
        sy = (np.arange(h) * H // h)
        sx = (np.arange(w) * W // w)
        return frame[np.ix_(sy, sx)]


class SimCameraSerial:
    """pyserial look-alike that runs the simulated camera firmware."""
    simulated = True

    def __init__(self, seed=None):
        import os
        if seed is None and os.environ.get("EE105_SEED"):
            seed = int(os.environ["EE105_SEED"])
        self.model = SimCamera(seed)
        idrng = np.random.default_rng(None if seed is None else seed + 2000)
        self.device_id = "".join("0123456789ABCDEF"[int(d)] for d in idrng.integers(0, 16, 16))
        self.is_open = True
        self.timeout = 0.2
        self._out = []

    def write(self, data):
        for line in bytes(data).decode().splitlines():
            self._handle(line.strip())
        return len(data)

    def _handle(self, line):
        tok = line.split()
        if not tok:
            return
        c = tok[0]
        say = self._out.append
        if c == "id":
            say("#ee105cam 2.0")
            say(f"#device_id {self.device_id}")
            say("#done")
        elif c == "module":
            pos = self.model.selector
            v = hw.SELECTOR_V.get(pos, 0.02) if pos is not None else 0.02
            label = hw.selector_line_label(pos)
            say(f"selector: {label} {v:.2f} V")
            say("#done")
        elif c == "snap":
            w = int(tok[1]) if len(tok) > 1 else 160
            h = int(tok[2]) if len(tok) > 2 else w * 3 // 4
            if not (8 <= w <= 320 and 8 <= h <= 240):
                say("#err size must be 8x8 to 320x240")
                return
            time.sleep(0.05)
            img = self.model.picture(w, h)
            say(f"#size {w} {h}")
            say(base64.b64encode(img.tobytes()).decode())
            say("#done")
        elif c == "test":
            self.model.test = bool(int(tok[1])) if len(tok) > 1 else True
            say("#done")
        elif c in ("e", "exit", "stop"):
            say("#done")
        else:
            say(f"#err unknown command: {c}")

    def readline(self):
        if self._out:
            return (self._out.pop(0) + "\r\n").encode()
        time.sleep(0.01)
        return b""

    def reset_input_buffer(self):
        self._out.clear()

    def flush(self):
        pass

    def close(self):
        self.is_open = False
