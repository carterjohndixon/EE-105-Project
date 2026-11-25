"""
webcam.py - This program allows the game to be run with a webcam instead of the board's camera.
            Compared to the board's camera, most webcams have a higher frame rate and resolution that
            could make the model's predictions more accurate.

Choose the camera when starting a script (the board is the default):
    python game_window.py --webcam          or set RPS_CAMERA=webcam first
    RPS_WEBCAM_INDEX=1                      picks a second (e.g. USB) webcam
"""

import os
import sys
import time

import numpy as np

try:
    import cv2              # only needed for the webcam; the board works without OpenCV
except ImportError:
    cv2 = None

def crop_to_aspect(frame, aspect):
    """Resize the webcame to mach the expected aspect ratio of the game and model which is 4:3"""
    h, w = frame.shape[:2]
    if w/h > aspect: # Image is too wide, crop the sides
        new_w = int(round(h* aspect))
        x0 = (w - new_w) // 2
        return frame[:, x0:x0 + new_w]
    new_h = int(round(w / aspect)) # Image is too tall, crop the top and bottom
    y0 = (h - new_h) // 2
    return frame[y0:y0 + new_h]

class Webcam:
    """The computer's webcam, with the same snap()/close() interface as ee105's Camera.

    index   0 is the default webcam; 1, 2, ... are extra (e.g. USB) cameras
    mirror  flip left-right so the live view behaves like a mirror
    warmup  frames thrown away at the start while auto-exposure settles"""
    def __init__(self, index=0, mirror=True, warmup=10):
        if cv2 is None:
            raise RuntimeError("OpenCV is not installed: pip install opencv-python")
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)
        if not self.cap.isOpened():
            raise RuntimeError(f"No webcam found at index {index}")
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Make sure each frame is a new frame
        self.index, self.mirror = index, mirror
        for _ in range(warmup):
            self.cap.read() # Throw away warmup frames where the camera is loading

    def snap(self, width=160, height=120):
        """One grayscale picture as a (height, width) uint8 array, matching the board's camera."""
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError("Webcame failed to capture a picture")
        if self.mirror:
            frame = cv2.flip(frame, 1)
        frame = crop_to_aspect(frame, width/height)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # OpenCV shape is (width, height), but NumPy shape is (height, width)
        return cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def blank_outside_box(img, crop=0.8, fill=128):
    """Gray everything out expect the center square for the model to see."""
    h, w, = img.shape
    s = int(round(min(h, w) * crop))
    y0, x0 = (h - s) // 2, (w - s) // 2
    out = np.full_like(img, fill)
    out[y0:y0 + s, x0:x0 + s] = img[y0:y0 + s, x0:x0 + s]
    return out

def open_camera(source=None):
    """Open the boards camera which is the default or open the webcame.
    Order: the source argument, then a --webcam flag on the command line, then RPS_CAMERA."""
    if source is None and "--webcam" in sys.argv:
        source = "webcam"
    source = (source or os.environ.get("RPS_CAMERA", "board")).lower()
    if source == "webcam":
        return Webcam(int(os.environ.get("RPS_WEBCAM_INDEX", "0")))
    if source == "board":
        import ee105
        return ee105.connect_camera()
    raise ValueError(f"Unknown camera {source!r}: use 'board' or 'webcam'")

if __name__ == "__main__":
    from PIL import Image

    with Webcam() as cam:
        img = cam.snap(160, 120)
        print("shape", img.shape, "dtype", img.dtype, "min", img.min(), "max", img.max())
        assert img.shape == (120, 160) and img.dtype == np.uint8

        n, t0 = 30, time.time()
        for _ in range(n):
            cam.snap(160, 120)
        print(f"{n / (time.time() - t0):.1f} pictures per second")

    Image.fromarray(img).resize((480, 360), Image.NEAREST).save("webcam_test.png")
    Image.fromarray(blank_outside_box(img)).resize((480, 360), Image.NEAREST).save("webcame_test_masked.png")
    print("saved webcam_test.png and webcame_test_masked.png")