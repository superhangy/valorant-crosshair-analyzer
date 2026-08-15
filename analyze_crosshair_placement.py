# Crosshair Discipline Analyzer — the actual point of this whole project.
#
# For each moment an enemy head newly becomes visible (a "reveal"), measure
# how far the crosshair (screen center — Valorant always renders it there)
# was from that head. Small distance = good pre-aim (you were already
# looking at the spot they appeared, so you just click). Large distance =
# you'd need to flick your mouse to react, costing time.

import csv
import os

import cv2
import matplotlib.pyplot as plt
from ultralytics import YOLO

CLIP_PATH = r"C:\Users\alexh\Videos\NVIDIA\Valorant\Valorant 2026.08.14 - 19.49.11.07.mp4"
HEAD_MODEL_PATH = "runs/detect/runs/valorant_head_v1/weights/best.pt"
BODY_MODEL_PATH = "runs/detect/runs/valorant_enemy_v1-3/weights/best.pt"
OUTPUT_DIR = "engagements"

HEAD_CONF_THRESHOLD = 0.4  # how sure the head model must be
BODY_CONF_THRESHOLD = 0.3  # how sure the body model must be (used only to
                            # cross-check heads, so can run a bit looser)
PROCESS_FPS = 30           # sample rate — plenty precise for a ~200ms reaction window
GRACE_SECONDS = 0.5        # bridge brief detection flicker before resetting "visible" state

# The head detector alone turned out to be unreliable on full raw gameplay
# frames — it fires on the player's own gun/fist viewmodel, empty ground,
# doorway geometry, and small HUD elements (scoreboard portraits, kill
# banners), not just real heads. Its training images were likely pre-cropped
# close to a person, so it never learned what "not a person" looks like.
# Fix: only trust a head detection if it also falls inside a box from the
# separately-trained body/"enemies" detector (Phase 3) — a gun scope or a
# doorway is very unlikely to fool *both* independently-trained models at
# the same location.
HEAD_MUST_BE_INSIDE_BODY_BOX = True

# The scoreboard/timer bar and kill-feed panel (top) and the kill banner /
# ammo count / ability icons (bottom) all live in fixed HUD bands. Real
# enemies you're aiming at are essentially never up there or down there,
# since the crosshair sits at exact screen center — safe to exclude both.
TOP_EXCLUSION_HEIGHT_FRAC = 0.20
BOTTOM_EXCLUSION_HEIGHT_FRAC = 0.75


def point_in_box(px, py, box):
    x1, y1, x2, y2 = box
    return x1 <= px <= x2 and y1 <= py <= y2


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    cap = cv2.VideoCapture(CLIP_PATH)
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    frame_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    center_x, center_y = frame_w / 2, frame_h / 2

    step = max(round(source_fps / PROCESS_FPS), 1)
    grace_samples = max(round(GRACE_SECONDS * PROCESS_FPS), 1)

    engagements = []
    frames_since_seen = grace_samples + 1  # start "not visible"
    frame_index = 0
    sample_index = 0

    while True:
        ok = cap.grab()
        if not ok:
            break
        frame_index += 1
        if frame_index % step != 0:
            continue

        ok, frame = cap.retrieve()
        if not ok:
            break
        sample_index += 1
        timestamp = frame_index / source_fps

        head_results = head_model(frame, conf=HEAD_CONF_THRESHOLD, verbose=False)
        head_boxes = head_results[0].boxes

        body_boxes_xyxy = []
        if HEAD_MUST_BE_INSIDE_BODY_BOX:
            body_results = body_model(frame, conf=BODY_CONF_THRESHOLD, verbose=False)
            body_boxes_xyxy = [b.xyxy[0].tolist() for b in body_results[0].boxes]

        # Nearest-head heuristic: with multiple simultaneous enemies and no
        # frame-to-frame identity tracking, we can't cleanly tell "which one
        # is new" — so we treat "any head visible after none were" as one
        # reveal event, and score it against whichever head is closest to
        # the crosshair (the one the player would actually be reacting to).
        # HUD-region boxes are skipped entirely, and (if enabled) a head box
        # must also fall inside a body-detector box to count as real —
        # see the comments above HEAD_MUST_BE_INSIDE_BODY_BOX.
        best_box = None
        best_dist = None
        for box in head_boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            hx, hy = (x1 + x2) / 2, (y1 + y2) / 2
            if hy < frame_h * TOP_EXCLUSION_HEIGHT_FRAC or hy > frame_h * BOTTOM_EXCLUSION_HEIGHT_FRAC:
                continue
            if HEAD_MUST_BE_INSIDE_BODY_BOX:
                if not any(point_in_box(hx, hy, bbox) for bbox in body_boxes_xyxy):
                    continue
            dist = ((hx - center_x) ** 2 + (hy - center_y) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_box = (hx, hy, float(box.conf[0]))

        if best_box is None:
            frames_since_seen += 1
            continue

        was_visible = frames_since_seen <= grace_samples
        frames_since_seen = 0

        if not was_visible:
            hx, hy, conf = best_box
            dist_pct = best_dist / frame_w * 100
            engagements.append({
                "timestamp_s": round(timestamp, 2),
                "distance_px": round(best_dist, 1),
                "distance_pct_width": round(dist_pct, 2),
                "confidence": round(conf, 3),
            })

            # Draw both models' boxes so a human reviewer can see exactly
            # why a detection was (or wasn't) trusted — body boxes in
            # green, the winning head box in blue.
            annotated = frame.copy()
            for bx1, by1, bx2, by2 in body_boxes_xyxy:
                cv2.rectangle(annotated, (int(bx1), int(by1)), (int(bx2), int(by2)), (0, 200, 0), 2)
            hx1, hy1 = int(hx - 10), int(hy - 10)
            hx2, hy2 = int(hx + 10), int(hy + 10)
            cv2.rectangle(annotated, (hx1, hy1), (hx2, hy2), (255, 100, 0), 2)
            cv2.putText(annotated, f"head {conf:.2f}", (hx1, hy1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 0), 2, cv2.LINE_AA)
            cv2.drawMarker(annotated, (int(center_x), int(center_y)),
                            (255, 255, 0), cv2.MARKER_CROSS, 30, 2)
            out_path = os.path.join(OUTPUT_DIR, f"t{timestamp:07.2f}s.jpg")
            cv2.imwrite(out_path, annotated)

    cap.release()

    # Save results
    with open("engagements.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_s", "distance_px", "distance_pct_width", "confidence"])
        writer.writeheader()
        writer.writerows(engagements)

    print(f"Processed {sample_index} sampled frames ({frame_index} total frames in clip).")
    print(f"Found {len(engagements)} engagements (enemy reveal moments).")

    if engagements:
        distances = [e["distance_pct_width"] for e in engagements]
        avg = sum(distances) / len(distances)
        print(f"Average pre-aim distance: {avg:.2f}% of screen width")
        print(f"Best (smallest): {min(distances):.2f}%  Worst (largest): {max(distances):.2f}%")

        plt.figure(figsize=(8, 5))
        plt.hist(distances, bins=20, color="#4C72B0", edgecolor="white")
        plt.xlabel("Pre-aim distance at reveal (% of screen width)")
        plt.ylabel("Number of engagements")
        plt.title(f"Crosshair Pre-Aim Discipline — {len(engagements)} engagements")
        plt.axvline(avg, color="red", linestyle="--", label=f"Average: {avg:.1f}%")
        plt.legend()
        plt.tight_layout()
        plt.savefig("preaim_distribution.png", dpi=150)
        print("Saved chart: preaim_distribution.png")
        print("Saved per-engagement data: engagements.csv")
        print(f"Saved annotated frames: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
