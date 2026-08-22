# Range-only live crosshair-placement overlay. NOT for live matches.
#
# Screen-captures the Range, runs the same trained head/body detectors as
# analyze_crosshair_placement.py on each frame, and draws a box on the
# currently-detected bot head — moves with your actual view, unlike a
# static calibrated line. No enemy tracking outside the Range, no
# match-state reads: this is literally your own screen through your own
# trained model, same as it already does offline in analyze_crosshair_placement.py.
#
# F10 toggles detection+overlay on/off. Starts OFF. F12 hard-quits.
# Range only. Turn OFF (F10) before queuing into any real match — the
# script does not know or care what mode you're in, that's on you.

import ctypes
import ctypes.wintypes

import cv2
import keyboard
import mss
import numpy as np
from ultralytics import YOLO

HEAD_MODEL_PATH = "runs/detect/runs/valorant_head_gray_v1/weights/best.pt"
BODY_MODEL_PATH = "runs/detect/runs/valorant_enemy_v1-3/weights/best.pt"
HEAD_CONF_THRESHOLD = 0.4
BODY_CONF_THRESHOLD = 0.3
HEAD_MUST_BE_INSIDE_BODY_BOX = True
TOP_EXCLUSION_HEIGHT_FRAC = 0.20
BOTTOM_EXCLUSION_HEIGHT_FRAC = 0.75
LOOP_INTERVAL_MS = 60  # ~16 fps live inference budget

BOX_COLOR = "cyan"
BOX_THICKNESS = 3

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
TRANSPARENT_COLOR = "magenta"
TRANSPARENT_COLORREF = 0x00FF00FF  # magenta, 0x00BBGGRR


def apply_window_styles(hwnd):
    # Any SetWindowLongW call resets a layered window's color-key, so it
    # must be reapplied right after, or the window renders solid black
    # (bit us once already). NOACTIVATE stops it stealing foreground focus
    # from Valorant every time it's shown/updated.
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, TRANSPARENT_COLORREF, 0, LWA_COLORKEY)


def point_in_box(px, py, box):
    x1, y1, x2, y2 = box
    return x1 <= px <= x2 and y1 <= py <= y2


def main():
    import tkinter as tk

    print("Loading detectors...")
    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    sct = mss.mss()
    monitor = sct.monitors[1]  # primary monitor, full bounds
    screen_w, screen_h = monitor["width"], monitor["height"]

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", TRANSPARENT_COLOR)
    root.geometry(f"{screen_w}x{screen_h}+0+0")

    canvas = tk.Canvas(root, width=screen_w, height=screen_h, bg=TRANSPARENT_COLOR, highlightthickness=0)
    canvas.pack()

    root.update_idletasks()
    apply_window_styles(root.winfo_id())

    state = {"active": False, "box_id": None, "after_id": None}

    def clear_box():
        if state["box_id"] is not None:
            canvas.delete(state["box_id"])
            state["box_id"] = None

    def detect_and_draw():
        if not state["active"]:
            return
        frame = np.array(sct.grab(monitor))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        head_input = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        head_results = head_model(head_input, conf=HEAD_CONF_THRESHOLD, verbose=False)
        head_boxes = head_results[0].boxes

        body_boxes_xyxy = []
        if HEAD_MUST_BE_INSIDE_BODY_BOX:
            body_results = body_model(frame, conf=BODY_CONF_THRESHOLD, verbose=False)
            body_boxes_xyxy = [b.xyxy[0].tolist() for b in body_results[0].boxes]

        best_box = None
        best_dist = None
        center_x, center_y = screen_w / 2, screen_h / 2
        for box in head_boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            hx, hy = (x1 + x2) / 2, (y1 + y2) / 2
            if hy < screen_h * TOP_EXCLUSION_HEIGHT_FRAC or hy > screen_h * BOTTOM_EXCLUSION_HEIGHT_FRAC:
                continue
            if HEAD_MUST_BE_INSIDE_BODY_BOX and not any(point_in_box(hx, hy, b) for b in body_boxes_xyxy):
                continue
            dist = ((hx - center_x) ** 2 + (hy - center_y) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_box = (x1, y1, x2, y2)

        clear_box()
        if best_box is not None:
            x1, y1, x2, y2 = best_box
            state["box_id"] = canvas.create_rectangle(x1, y1, x2, y2, outline=BOX_COLOR, width=BOX_THICKNESS)

        state["after_id"] = root.after(LOOP_INTERVAL_MS, detect_and_draw)

    def toggle_active():
        state["active"] = not state["active"]
        print(f"[live overlay] {'ON' if state['active'] else 'OFF'}")
        if state["active"]:
            detect_and_draw()
        else:
            if state["after_id"] is not None:
                root.after_cancel(state["after_id"])
                state["after_id"] = None
            clear_box()

    def quit_app():
        print("[live overlay] quitting")
        root.after(0, root.destroy)

    keyboard.add_hotkey("f10", toggle_active, suppress=True)
    keyboard.add_hotkey("f12", quit_app, suppress=True)

    print("Live head-detection overlay ready.")
    print("  F10 = toggle detection + overlay on/off (starts OFF)")
    print("  F12 = quit entirely (use this if anything looks wrong)")
    print("  Range only. Turn OFF (F10) before queuing into any real match.")

    root.mainloop()


if __name__ == "__main__":
    main()
