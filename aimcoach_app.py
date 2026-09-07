"""
Valorant Aim Coach -- friendly desktop front end.

Double-click the built AimCoach.exe (or run `python aimcoach_app.py`):
pick a gameplay clip, wait, get an HTML coaching report. No terminal, no
Python knowledge needed.

The heavy lifting is coach_clip.run_coaching(); this file is only the
window, the progress log, and marshalling the mid-run spot-check reviewer
back onto the main (tkinter) thread while the pipeline runs in a worker.
"""

import os
import queue
import re
import sys
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Valorant Aim Coach"
VIDEO_TYPES = [
    ("Video clips", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
    ("All files", "*.*"),
]
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


# ---------------------------------------------------------------------------
# Mid-run keep/drop reviewer -- a Toplevel so it shares the app's root.
# ---------------------------------------------------------------------------

class Reviewer(tk.Toplevel):
    def __init__(self, parent, outdir, frames, scores, csv_path, verdicts, on_done):
        super().__init__(parent)
        from PIL import Image, ImageTk  # lazy: keeps startup light
        self._Image, self._ImageTk = Image, ImageTk

        self.title("Quick check -- is this a real enemy?")
        self.outdir = Path(outdir)
        self.frames = list(frames)
        self.scores = scores
        self.csv_path = Path(csv_path)
        self.verdicts = dict(verdicts)
        self.on_done = on_done
        self.index = 0
        self.history = []

        self.protocol("WM_DELETE_WINDOW", self._finish)
        self.img_label = tk.Label(self)
        self.img_label.pack(padx=8, pady=8)
        self.status = tk.Label(self, font=("Segoe UI", 11), wraplength=900, justify="center")
        self.status.pack(pady=(0, 6))
        bar = tk.Frame(self)
        bar.pack(pady=(0, 10))
        tk.Button(bar, text="  Real enemy -- KEEP  (K / →)", bg="#2e7d32", fg="white",
                  font=("Segoe UI", 10, "bold"), command=self.keep).pack(side=tk.LEFT, padx=6)
        tk.Button(bar, text="  Not an enemy -- DROP  (D / ←)", bg="#c62828", fg="white",
                  font=("Segoe UI", 10, "bold"), command=self.drop).pack(side=tk.LEFT, padx=6)
        tk.Button(bar, text="Undo (U)", command=self.undo).pack(side=tk.LEFT, padx=16)
        self.bind("<k>", lambda e: self.keep())
        self.bind("<Right>", lambda e: self.keep())
        self.bind("<d>", lambda e: self.drop())
        self.bind("<Left>", lambda e: self.drop())
        self.bind("<u>", lambda e: self.undo())
        self.bind("<BackSpace>", lambda e: self.undo())

        self.remaining = [f for f in self.frames if f not in self.verdicts]
        self._show()
        self.grab_set()
        self.focus_force()

    def _show(self):
        if self.index >= len(self.remaining):
            self._finish()
            return
        fname = self.remaining[self.index]
        try:
            img = self._Image.open(self.outdir / fname)
        except OSError:
            # no frame on disk -> can't judge, default keep, move on
            self.verdicts[fname] = "keep"
            self.index += 1
            self._show()
            return
        img.thumbnail((1100, 680))
        self._photo = self._ImageTk.PhotoImage(img)
        self.img_label.configure(image=self._photo)
        n = len(self.remaining)
        self.status.configure(
            text=f"Frame {self.index + 1} of {n}   —   "
                 f"Is the BLUE box on a real enemy player's head? "
                 f"(not a teammate, not your own gun, not a UI element)")

    def _record(self, verdict):
        fname = self.remaining[self.index]
        self.verdicts[fname] = verdict
        self.history.append(fname)
        self._write()
        self.index += 1
        self._show()

    def keep(self):
        self._record("keep")

    def drop(self):
        self._record("drop")

    def undo(self):
        if not self.history:
            return
        fname = self.history.pop()
        self.verdicts.pop(fname, None)
        self._write()
        self.index = max(0, self.index - 1)
        self._show()

    def _write(self):
        import csv
        with open(self.csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["filename", "verdict"])
            for k, v in self.verdicts.items():
                w.writerow([k, v])

    def _finish(self):
        self._write()
        try:
            self.grab_release()
            self.destroy()
        finally:
            self.on_done()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("760x560")
        self.root.minsize(640, 460)

        self.clip = None
        self.msgq = queue.Queue()
        self.worker = None
        self.result = None
        self._sc_done = threading.Event()

        pad = dict(padx=16, pady=6)
        tk.Label(self.root, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(**pad)
        tk.Label(
            self.root, justify="left", wraplength=700,
            text="Pick a Valorant gameplay clip. The tool finds every moment an "
                 "enemy first appears, measures how far your crosshair was from "
                 "their head, and compares you to a pool of pro VODs.\n"
                 "Takes about 30-50 minutes. You can leave it running.",
        ).pack(**pad)

        row = tk.Frame(self.root)
        row.pack(**pad)
        self.choose_btn = tk.Button(row, text="Choose clip…", width=14,
                                    command=self.choose)
        self.choose_btn.pack(side=tk.LEFT)
        self.clip_label = tk.Label(row, text="no clip selected", fg="#666")
        self.clip_label.pack(side=tk.LEFT, padx=10)

        self.start_btn = tk.Button(self.root, text="Analyze", width=20, height=2,
                                   state=tk.DISABLED, font=("Segoe UI", 11, "bold"),
                                   command=self.start)
        self.start_btn.pack(pady=10)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=680)
        self.progress.pack(**pad)

        self.log = tk.Text(self.root, height=14, bg="#0f1117", fg="#cbd5e1",
                           font=("Consolas", 9), wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True, padx=16, pady=(6, 4))
        self.log.configure(state=tk.DISABLED)

        self.open_btn = tk.Button(self.root, text="Open report", state=tk.DISABLED,
                                  command=self.open_report)
        self.open_btn.pack(pady=(0, 12))

        self.root.after(120, self._pump)

    # -- user actions ------------------------------------------------------

    def choose(self):
        p = filedialog.askopenfilename(title="Choose your Valorant clip",
                                       filetypes=VIDEO_TYPES)
        if not p:
            return
        self.clip = Path(p)
        self.clip_label.configure(text=self.clip.name, fg="#111")
        self.start_btn.configure(state=tk.NORMAL)

    def start(self):
        if not self.clip or not self.clip.exists():
            messagebox.showerror(APP_TITLE, "Pick a clip first.")
            return
        self.choose_btn.configure(state=tk.DISABLED)
        self.start_btn.configure(state=tk.DISABLED)
        self.open_btn.configure(state=tk.DISABLED)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self._append(f"Analyzing {self.clip.name}\n")
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def open_report(self):
        if self.result and Path(self.result["report_html"]).exists():
            _open_file(self.result["report_html"])

    # -- worker thread ---------------------------------------------------

    def _run(self):
        try:
            from coach_clip import run_coaching
            res = run_coaching(self.clip, progress=self._progress,
                               spotcheck_gui=self._spotcheck)
            self.msgq.put(("done", res))
        except SystemExit as e:
            self.msgq.put(("error", str(e)))
        except Exception:
            self.msgq.put(("error", traceback.format_exc()))

    def _progress(self, line):
        self.msgq.put(("log", str(line)))

    def _spotcheck(self, outdir, frames, scores, csv_path, verdicts):
        # runs on the worker thread; hand off to the main thread and block
        self._sc_done.clear()
        self.msgq.put(("spotcheck", (outdir, frames, scores, csv_path, verdicts)))
        self._sc_done.wait()

    # -- main-thread pump ----------------------------------------------

    def _pump(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self._append(str(payload) + "\n")
                    self._update_bar(str(payload))
                elif kind == "spotcheck":
                    self._open_reviewer(*payload)
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._error(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._pump)

    def _open_reviewer(self, outdir, frames, scores, csv_path, verdicts):
        self._append(f"\nQuick check: {len(frames)} borderline frame(s) need your eye.\n")
        Reviewer(self.root, outdir, frames, scores, csv_path, verdicts,
                 on_done=self._sc_done.set)

    def _finish(self, res):
        self.result = res
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)
        self.open_btn.configure(state=tk.NORMAL)
        self.choose_btn.configure(state=tk.NORMAL)
        me, base = res["me"], res["base"]
        if me.get("n"):
            self._append(
                f"\nDone. Your median pre-aim {me['median']:.2f}% vs pro "
                f"{base['median']:.2f}%.  Opening report…\n")
        else:
            self._append("\nDone, but no reveals survived filtering. "
                         "Try a Deathmatch clip.\n")
        if Path(res["report_html"]).exists():
            _open_file(res["report_html"])

    def _error(self, msg):
        self.progress.stop()
        self.choose_btn.configure(state=tk.NORMAL)
        self.start_btn.configure(state=tk.NORMAL)
        self._append("\nSomething went wrong:\n" + msg + "\n")
        messagebox.showerror(APP_TITLE, "Analysis failed. See the log for details.")

    # -- helpers ---------------------------------------------------------

    def _append(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _update_bar(self, line):
        m = PCT_RE.search(line)
        if not m:
            return
        try:
            val = float(m.group(1))
        except ValueError:
            return
        if self.progress["mode"] != "determinate":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
        self.progress.configure(value=val)

    def run(self):
        self.root.mainloop()


def _open_file(path):
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


def main():
    # keep the OpenMP / thread pools from oversubscribing on a laptop
    os.environ.setdefault("OMP_NUM_THREADS", str(max(1, (os.cpu_count() or 4) // 2)))
    try:
        App().run()
    except Exception:
        # last-resort: show the traceback somewhere a non-technical user can
        # copy it, instead of a silent exit
        err = traceback.format_exc()
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(APP_TITLE, err)
        except Exception:
            print(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
