"""
game_window.py - Rock Paper Scissors with a live camera window

Shows the camera picture and, live, the gesture the model thinks you are showing.
Keys (click the window first):
  Space or Enter   play a round: countdown, then your gesture is read from the camera
  Q or Esc         quit

Run:  python game_window.py            (EE 105 board camera)
      python game_window.py --webcam   (the computer's webcam)

NOTE: This file was generated with the help of AI to make the the visaulization of the game.
"""

import threading
import time
from collections import deque
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

import game
import model
from main import print_statistics

SCALE = 3                 # the 160 x 120 camera picture is shown at 480 x 360
FRAMES_PER_ROUND = 3      # same as model.detect_gesture()
MIN_CONFIDENCE = 0.45     # same as model.detect_gesture()
CROP = 0.8                # the center square the model looks at (see model.predict_frame)
COUNTDOWN = ["Rock...", "Paper...", "Scissors...", "Shoot!"]
COUNTDOWN_MS = 1500        # time per countdown word (4 words = 3.2 s to get ready)
HOLD_MS = 600             # after "Shoot!": time to make the gesture and hold still before pictures count
PREDICT_EVERY_S = 0.1     # run the model at most 10 times per second (a webcam sends ~30 pictures/s;
                          # the board's ~2.5 pictures/s are all predicted)

GREEN, RED, GRAY, ORANGE = "#2e7d32", "#c62828", "#555555", "#e65100"


def vote(predictions):
    """The gesture most frames agree on (same rule as model.detect_gesture), or None."""
    votes = [label for label, p in predictions if label != "none" and p.max() >= MIN_CONFIDENCE]
    if not votes:
        return None
    best = max(set(votes), key=votes.count)
    return best if votes.count(best) > len(predictions) // 2 else None


class CameraThread(threading.Thread):
    """Takes pictures and predicts them continuously, so the window never waits for the camera."""

    def __init__(self, cam, kind, net):
        super().__init__(daemon=True)
        self.cam, self.kind, self.net = cam, kind, net
        self.lock = threading.Lock()
        self.count = 0                       # pictures taken so far
        self.latest = None                   # (count, picture, label, probabilities)
        self.history = deque(maxlen=30)      # (count, label, probabilities) of recent pictures
        self.times = deque(maxlen=10)        # when recent pictures arrived (for the frame rate)
        self.error = None
        self.running = True

    def run(self):
        label, p, last_prediction = None, None, 0.0
        try:
            while self.running:
                img = self.cam.snap(160, 120)
                now = time.perf_counter()
                predicted = label is None or now - last_prediction >= PREDICT_EVERY_S
                if predicted:                 # other pictures are shown with the last prediction
                    label, p = model.predict_frame(self.net, self.kind, img)
                    last_prediction = now
                with self.lock:
                    self.count += 1
                    self.latest = (self.count, img, label, p)
                    if predicted:             # only real predictions count in a round's vote
                        self.history.append((self.count, label, p))
                    self.times.append(now)
        except Exception as e:                # shown in the window instead of a silent stop
            self.error = e

    def fps(self):
        with self.lock:
            t = list(self.times)
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 else 0.0

    def predictions_after(self, count):
        with self.lock:
            return [(label, p) for c, label, p in self.history if c > count]


class GameWindow:
    def __init__(self, root, camera):
        self.root, self.camera = root, camera
        self.score = {"user": 0, "computer": 0, "tie": 0}
        self.busy = False                     # True while a round is running
        self.shown = 0                        # last picture shown
        self.font = ImageFont.load_default(size=16)

        root.title("Rock Paper Scissors")
        root.configure(bg="white")
        big, mid, small = ("Helvetica", 22, "bold"), ("Helvetica", 15), ("Helvetica", 11)

        self.video = tk.Label(root, bg="black", width=160 * SCALE, height=120 * SCALE)
        self.live = tk.Label(root, font=mid, bg="white", text="Starting the camera...")
        self.result = tk.Label(root, font=big, bg="white", text="Press Space to play")
        self.moves = tk.Label(root, font=mid, bg="white", text="")
        self.scoreboard = tk.Label(root, font=mid, bg="white")
        self.help = tk.Label(root, font=small, bg="white", fg=GRAY,
                             text="Space / Enter: play a round      Q / Esc: quit")
        for w in (self.video, self.live, self.result, self.moves, self.scoreboard, self.help):
            w.pack(padx=12, pady=4)
        self.update_scoreboard()

        for key in ("<space>", "<Return>"):
            root.bind(key, lambda e: self.start_round())
        for key in ("q", "Q", "<Escape>"):
            root.bind(key, lambda e: root.destroy())
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.after(40, self.refresh)

    # ---------------------------------------------------------- live view
    def refresh(self):
        if self.camera.error is not None:
            self.live.config(text=f"Camera error: {self.camera.error}", fg=RED)
            return
        latest = self.camera.latest
        if latest is not None and latest[0] != self.shown:
            count, img, label, p = latest
            self.shown = count
            self.show_picture(img, label, p)
            sure = label != "none" and p.max() >= MIN_CONFIDENCE
            guess = f"{label} ({p.max():.0%})" if sure else "not sure"
            self.live.config(text=f"Model sees: {guess}      {self.camera.fps():.1f} pictures/s",
                             fg="black" if sure else GRAY)
        self.root.after(40, self.refresh)

    def show_picture(self, img, label, p):
        pic = Image.fromarray(img).resize((160 * SCALE, 120 * SCALE), Image.BILINEAR).convert("RGB")
        draw = ImageDraw.Draw(pic)
        s = int(round(120 * CROP)) * SCALE                       # the square the model looks at
        x0, y0 = (pic.width - s) // 2, (pic.height - s) // 2
        draw.rectangle([x0, y0, x0 + s, y0 + s], outline=(255, 200, 0), width=3)
        lines = [f"{c:<9}{p[i]:4.0%}" for i, c in enumerate(model.CLASSES) if c != "none"]
        for k, text in enumerate(lines):                         # probabilities, top left
            draw.text((8, 6 + 20 * k), text, fill=(255, 255, 0), font=self.font,
                      stroke_width=2, stroke_fill=(0, 0, 0))
        self.photo = ImageTk.PhotoImage(pic)                     # keep a reference or Tk drops it
        self.video.config(image=self.photo)

    # ------------------------------------------------------------- rounds
    def start_round(self):
        if self.busy or self.camera.error is not None:
            return
        self.busy = True
        self.moves.config(text="")
        self.countdown(0)

    def countdown(self, step):
        if step < len(COUNTDOWN):
            self.result.config(text=COUNTDOWN[step], fg="black")
            self.root.after(COUNTDOWN_MS, self.countdown, step + 1)
        else:                                 # after "Shoot!": give the hand time to stop moving
            self.result.config(text="Hold it!", fg="black")
            self.root.after(HOLD_MS, lambda: self.collect(self.camera.count, time.perf_counter()))

    def collect(self, after_count, t0):
        predictions = self.camera.predictions_after(after_count)
        if len(predictions) >= FRAMES_PER_ROUND:
            self.finish_round(vote(predictions[:FRAMES_PER_ROUND]))
        elif time.perf_counter() - t0 > 5:    # the camera stopped sending pictures
            self.finish_round(None)
        else:
            self.root.after(50, self.collect, after_count, t0)

    def finish_round(self, user_move):
        self.busy = False
        if not game.is_valid_move(user_move):
            self.result.config(text="Couldn't read your gesture, try again", fg=ORANGE)
            return
        computer_move, result = game.play_round(user_move)
        self.score[result] += 1
        text, color = {"user": ("You win!", GREEN), "computer": ("Computer wins!", RED),
                       "tie": ("It's a tie!", GRAY)}[result]
        self.result.config(text=text, fg=color)
        self.moves.config(text=f"You: {user_move}      Computer: {computer_move}")
        self.update_scoreboard()

    def update_scoreboard(self):
        s = self.score
        rounds = s["user"] + s["computer"] + s["tie"]
        rate = s["user"] / rounds * 100 if rounds else 0.0
        self.scoreboard.config(text=f"You {s['user']}   Computer {s['computer']}   Ties {s['tie']}"
                                    f"      ({rounds} rounds, you win {rate:.0f}%)")


def main():
    print("Loading the model and connecting to the camera...")
    try:
        kind, net = model.load_best()
        from webcam import open_camera
        cam = open_camera()                  # the board, or the webcam with --webcam / RPS_CAMERA=webcam
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"Can't start the game: {e}")
        return

    camera = CameraThread(cam, kind, net)
    camera.start()
    root = tk.Tk()
    window = GameWindow(root, camera)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        camera.running = False
        camera.join(timeout=2)               # let the last picture finish before closing the port
        cam.close()
    print("Thanks for playing!")
    print_statistics(window.score, title="Final Statistics")


if __name__ == "__main__":
    main()
