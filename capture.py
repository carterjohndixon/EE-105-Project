"""
capture.py - Take training pictures with the OV7675 camera

Shows the live camera (the same view and yellow box as game_window.py) and saves pictures into
the class folders used for training:

    data/ours/<class>/   training pictures   (the model learns from these)
    data/test/<class>/   test pictures       (only for measuring accuracy; take them in a separate session)

Keys (click the window first):
  R  P  S  N   start recording rock / paper / scissors / none: every new camera picture is saved
               (press the same key again, or Space, to stop)
  1            save just one picture of the class you recorded last
  T            switch between data/ours and data/test
  Q or Esc     quit

Run:  python capture.py
"""

import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

ROOT = Path(__file__).resolve().parent
TARGETS = {"ours": ROOT / "data" / "ours", "test": ROOT / "data" / "test"}
CLASSES = {"r": "rock", "p": "paper", "s": "scissors", "n": "none"}
WIDTH, HEIGHT = 160, 120   # what the game uses (model.detect_gesture / game_window.py)
SCALE = 3
CROP = 0.8                 # the center square the model looks at (see model.predict_frame)
GOAL = {"ours": 150, "test": 30}   # suggested pictures per class

RED, GRAY = "#c62828", "#555555"


class Camera(threading.Thread):
    """Takes pictures continuously so the window never waits for the camera."""

    def __init__(self, cam):
        super().__init__(daemon=True)
        self.cam = cam
        self.lock = threading.Lock()
        self.count, self.latest, self.error, self.running = 0, None, None, True

    def run(self):
        try:
            while self.running:
                img = self.cam.snap(WIDTH, HEIGHT)
                with self.lock:
                    self.count += 1
                    self.latest = (self.count, img)
        except Exception as e:
            self.error = e


class CaptureWindow:
    def __init__(self, root, camera):
        self.root, self.camera = root, camera
        self.target = "ours"
        self.recording = None        # class being recorded, or None
        self.last_class = None
        self.shown = 0               # last picture shown (and saved, while recording)
        self.font = ImageFont.load_default(size=18)

        root.title("Capture training pictures")
        root.configure(bg="white")
        self.video = tk.Label(root, bg="black", width=WIDTH * SCALE, height=HEIGHT * SCALE)
        self.status = tk.Label(root, font=("Helvetica", 15, "bold"), bg="white")
        self.counts = tk.Label(root, font=("Courier", 12), bg="white", justify="left")
        self.help = tk.Label(root, font=("Helvetica", 11), bg="white", fg=GRAY, justify="left",
                             text="R / P / S / N: start or stop recording rock / paper / scissors / none\n"
                                  "Space: stop     1: save one picture     T: switch ours/test     Q: quit")
        for w in (self.video, self.status, self.counts, self.help):
            w.pack(padx=12, pady=4)

        for key, cls in CLASSES.items():
            for k in (key, key.upper()):
                root.bind(k, lambda e, c=cls: self.toggle(c))
        root.bind("<space>", lambda e: self.stop())
        root.bind("1", lambda e: self.save_one())
        for k in ("t", "T"):
            root.bind(k, lambda e: self.switch_target())
        for k in ("q", "Q", "<Escape>"):
            root.bind(k, lambda e: root.destroy())
        self.update_labels()
        root.after(40, self.refresh)

    # ------------------------------------------------------------ actions
    def toggle(self, cls):
        self.recording = None if self.recording == cls else cls
        self.last_class = cls
        self.update_labels()

    def stop(self):
        self.recording = None
        self.update_labels()

    def switch_target(self):
        self.stop()
        self.target = "test" if self.target == "ours" else "ours"
        self.update_labels()

    def save_one(self):
        if self.last_class and self.camera.latest is not None:
            self.save(self.camera.latest[1], self.last_class)
            self.update_labels()

    def save(self, img, cls):
        folder = TARGETS[self.target] / cls
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{cls}_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        Image.fromarray(img).save(folder / name)     # the raw 160 x 120 picture, no box drawn

    # --------------------------------------------------------- live view
    def refresh(self):
        if self.camera.error is not None:
            self.status.config(text=f"Camera error: {self.camera.error}", fg=RED)
            return
        latest = self.camera.latest
        if latest is not None and latest[0] != self.shown:
            self.shown, img = latest
            if self.recording:
                self.save(img, self.recording)
                self.update_labels()
            self.show(img)
        self.root.after(40, self.refresh)

    def show(self, img):
        pic = Image.fromarray(img).resize((WIDTH * SCALE, HEIGHT * SCALE), Image.BILINEAR).convert("RGB")
        draw = ImageDraw.Draw(pic)
        s = int(round(HEIGHT * CROP)) * SCALE
        x0, y0 = (pic.width - s) // 2, (pic.height - s) // 2
        color = (230, 40, 40) if self.recording else (255, 200, 0)
        draw.rectangle([x0, y0, x0 + s, y0 + s], outline=color, width=3)
        if self.recording:
            draw.text((8, 6), f"REC {self.recording}", fill=(255, 60, 60), font=self.font,
                      stroke_width=2, stroke_fill=(0, 0, 0))
        draw.text((8, pic.height - 26), f"mean brightness {img.mean():.0f}", fill=(255, 255, 0),
                  font=self.font, stroke_width=2, stroke_fill=(0, 0, 0))
        self.photo = ImageTk.PhotoImage(pic)
        self.video.config(image=self.photo)

    def update_labels(self):
        where = f"data/{self.target}"
        if self.recording:
            self.status.config(text=f"Recording {self.recording} into {where}", fg=RED)
        else:
            self.status.config(text=f"Saving into {where}  (not recording)", fg="black")
        lines = []
        for cls in CLASSES.values():
            folder = TARGETS[self.target] / cls
            n = sum(1 for p in folder.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")) if folder.exists() else 0
            lines.append(f"{cls:<9}{n:>5} / {GOAL[self.target]}")
        self.counts.config(text="\n".join(lines))


def main():
    import ee105
    print("Connecting to the camera...")
    try:
        cam = ee105.connect_camera()
    except RuntimeError as e:
        print(f"Can't start: {e}")
        return
    camera = Camera(cam)
    camera.start()
    root = tk.Tk()
    CaptureWindow(root, camera)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        camera.running = False
        camera.join(timeout=2)
        cam.close()
    for target, folder in TARGETS.items():
        counts = {c: len(list((folder / c).glob("*.png"))) if (folder / c).exists() else 0 for c in CLASSES.values()}
        print(f"data/{target}: {counts}")


if __name__ == "__main__":
    main()
