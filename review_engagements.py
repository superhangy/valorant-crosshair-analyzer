"""
Click-through reviewer for engagement frames.

Usage:
    python review_engagements.py engagements_demon1_chamber

Shows one annotated frame at a time. You judge whether the detected head/body
box is a real enemy or a false positive, and label it. Results are appended
to <folder>_review.csv as you go (one row per decision, flushed immediately -
if you close the window partway through, re-running the same command resumes
right where you left off).

Keys / buttons:
    G or Right arrow   -> Good (real detection)
    1  teammate-as-target
    2  gun/viewmodel-as-head
    3  scoreboard-portrait-as-head
    4  spectate/killcam contamination
    5  other bad detection
    U or Backspace      -> undo last decision (go back one frame)
    Esc                 -> save and quit
"""

import csv
import sys
from pathlib import Path

import tkinter as tk
from PIL import Image, ImageTk

MAX_DISPLAY_SIZE = (1400, 850)

BAD_CATEGORIES = {
    "1": "teammate-as-target",
    "2": "gun-viewmodel-as-head",
    "3": "scoreboard-portrait-as-head",
    "4": "spectate-killcam",
    "5": "other-bad",
}


class ReviewApp:
    def __init__(self, folder: Path):
        self.folder = folder
        self.csv_path = folder.parent / f"{folder.name}_review.csv"

        all_frames = sorted(folder.glob("t*.jpg"))
        if not all_frames:
            raise SystemExit(f"No t*.jpg frames found in {folder}")

        already_done = self._load_existing()
        self.frames = [f for f in all_frames if f.name not in already_done]
        self.total = len(all_frames)
        self.done_count = len(already_done)

        if not self.frames:
            print(f"All {self.total} frames already reviewed in {self.csv_path}")
            raise SystemExit(0)

        self.index = 0
        self.history = []  # (filename, label, category) for undo

        self.root = tk.Tk()
        self.root.title("Engagement review")

        self.image_label = tk.Label(self.root)
        self.image_label.pack()

        self.status_label = tk.Label(self.root, font=("Segoe UI", 12))
        self.status_label.pack(pady=4)

        button_row = tk.Frame(self.root)
        button_row.pack(pady=6)
        tk.Button(button_row, text="Good (G)", bg="#2e7d32", fg="white",
                  width=14, command=self.mark_good).pack(side=tk.LEFT, padx=4)
        for key, label in BAD_CATEGORIES.items():
            tk.Button(button_row, text=f"{key}: {label}", bg="#c62828", fg="white",
                      command=lambda k=key: self.mark_bad(k)).pack(side=tk.LEFT, padx=4)
        tk.Button(button_row, text="Undo (U)", command=self.undo).pack(side=tk.LEFT, padx=12)

        self.root.bind("<g>", lambda e: self.mark_good())
        self.root.bind("<Right>", lambda e: self.mark_good())
        for key in BAD_CATEGORIES:
            self.root.bind(key, lambda e, k=key: self.mark_bad(k))
        self.root.bind("<u>", lambda e: self.undo())
        self.root.bind("<BackSpace>", lambda e: self.undo())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.show_current()
        self.root.mainloop()

    def _load_existing(self) -> set:
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="") as f:
                csv.writer(f).writerow(["filename", "label", "category"])
            return set()
        with open(self.csv_path, newline="") as f:
            return {row["filename"] for row in csv.DictReader(f)}

    def show_current(self):
        path = self.frames[self.index]
        img = Image.open(path)
        img.thumbnail(MAX_DISPLAY_SIZE)
        self.photo = ImageTk.PhotoImage(img)
        self.image_label.configure(image=self.photo)

        seen = self.done_count + self.index
        self.status_label.configure(
            text=f"{path.name}   ({seen + 1}/{self.total})"
        )

    def _record(self, filename: str, label: str, category: str):
        with open(self.csv_path, "a", newline="") as f:
            csv.writer(f).writerow([filename, label, category])
        self.history.append((filename, label, category))

    def _advance(self):
        self.index += 1
        if self.index >= len(self.frames):
            print(f"Done - reviewed all remaining frames. Results in {self.csv_path}")
            self.root.destroy()
            return
        self.show_current()

    def mark_good(self):
        self._record(self.frames[self.index].name, "good", "")
        self._advance()

    def mark_bad(self, key: str):
        self._record(self.frames[self.index].name, "bad", BAD_CATEGORIES[key])
        self._advance()

    def undo(self):
        if not self.history or self.index == 0:
            return
        self.history.pop()
        self.index -= 1
        # rewrite csv without the last row
        rows = []
        with open(self.csv_path, newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        rows.pop()
        with open(self.csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        self.show_current()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python review_engagements.py <engagements_folder>")
    ReviewApp(Path(sys.argv[1]))
