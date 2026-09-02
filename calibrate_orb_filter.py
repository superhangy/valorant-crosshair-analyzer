"""
Calibrate a new candidate teammate-filter signal: a small white marker/orb
that appears to float directly above ally players' heads (distinct from the
ring-outline and nameplate-color signals already tried and confirmed dead --
see feedback_ally_color_filter_ceiling memory / PIPELINE_STATE.md 2026-08-22
entries). This one targets the region ABOVE the head box, not around the
body or below the feet.

For every "good" (real enemy) and "teammate-as-target" (false positive) row
across one or more reviewed engagements folders, re-extracts the source
frame, reruns the same head+body box-selection logic
analyze_crosshair_placement.py uses to recover the exact HEAD box that got
scored, then measures a white-pixel fraction in a small band directly above
that head box.

Does NOT edit analyze_crosshair_placement.py -- prints good vs
teammate-as-target distributions plus a threshold sweep. Review before
deciding whether this signal is real and wiring it in.

Usage:
    python calibrate_orb_filter.py engagements_100t-asuna-pov-raze-on-split-valorant-ranked-gameplay engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay engagements_100t-asuna-pro-raze-valorant-ranked-gameplay-mvp-full-match-vod engagements_100t-cryo-s-phoenix-is-amazing-valorant-ranked-gameplay
"""

import csv
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from analyze_crosshair_placement import (
    HEAD_MODEL_PATH, BODY_MODEL_PATH, HEAD_CONF_THRESHOLD, BODY_CONF_THRESHOLD,
    TOP_EXCLUSION_HEIGHT_FRAC, BOTTOM_EXCLUSION_HEIGHT_FRAC,
    point_in_box,
)
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")

# Band searched directly above the recovered head box.
ORB_BAND_HEIGHT_PX = 40
ORB_SIDE_PAD_PX = 15
# "white-ish" HSV: low saturation, high value. Wide net on purpose --
# calibration sweep below finds the real cutoff, this is just the candidate
# pixel definition.
ORB_SAT_MAX = 60
ORB_VAL_MIN = 190


def orb_white_fraction(frame, head_box):
    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in head_box]
    bx1 = max(0, x1 - ORB_SIDE_PAD_PX)
    bx2 = min(w_img, x2 + ORB_SIDE_PAD_PX)
    by2 = max(0, y1)
    by1 = max(0, by2 - ORB_BAND_HEIGHT_PX)
    band = frame[by1:by2, bx1:bx2]
    if band.size == 0:
        return 0.0
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    white_pixels = (s <= ORB_SAT_MAX) & (v >= ORB_VAL_MIN)
    return int(white_pixels.sum()) / band.size * 3  # normalize vs 3-channel size roughly


def find_scored_head_box(frame, head_model, body_model, frame_w, frame_h):
    center_x, center_y = frame_w / 2, frame_h / 2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    head_input = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    head_results = head_model(head_input, conf=HEAD_CONF_THRESHOLD, verbose=False)
    head_boxes = head_results[0].boxes

    body_results = body_model(frame, conf=BODY_CONF_THRESHOLD, verbose=False)
    body_boxes_xyxy = [b.xyxy[0].tolist() for b in body_results[0].boxes]

    best_head_box = None
    best_dist = None
    for box in head_boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        hx, hy = (x1 + x2) / 2, (y1 + y2) / 2
        if hy < frame_h * TOP_EXCLUSION_HEIGHT_FRAC or hy > frame_h * BOTTOM_EXCLUSION_HEIGHT_FRAC:
            continue
        matching_body_box = next((bbox for bbox in body_boxes_xyxy if point_in_box(hx, hy, bbox)), None)
        if matching_body_box is None:
            continue
        dist = ((hx - center_x) ** 2 + (hy - center_y) ** 2) ** 0.5
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_head_box = (x1, y1, x2, y2)
    return best_head_box


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python calibrate_orb_filter.py <engagements_folder> [<folder> ...]")

    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    rows_by_label = {"good": [], "teammate-as-target": []}

    for folder_arg in sys.argv[1:]:
        folder = Path(folder_arg)
        slug = folder.name.removeprefix("engagements_")
        review_csv = folder.parent / f"{folder.name}_review.csv"
        if not review_csv.exists():
            print(f"SKIP {folder}: no review CSV")
            continue
        video = find_video_for_slug(slug)
        if video is None:
            print(f"SKIP {folder}: no matching source video in Downloads")
            continue

        with open(review_csv, newline="") as f:
            reader = csv.DictReader(f)
            wanted = [r for r in reader if r["label"] == "good" or r["category"] == "teammate-as-target"]

        print(f"{folder.name}: {len(wanted)} rows to measure ({video.name})")
        for row in wanted:
            m = TIMESTAMP_RE.match(row["filename"])
            if not m:
                continue
            ts = float(m.group(1))
            frame = extract_frame(video, ts)
            if frame is None:
                print(f"  SKIP (ffmpeg failed): {row['filename']}")
                continue
            frame_h, frame_w = frame.shape[:2]
            head_box = find_scored_head_box(frame, head_model, body_model, frame_w, frame_h)
            if head_box is None:
                print(f"  SKIP (couldn't recover scored head box): {row['filename']}")
                continue
            frac = orb_white_fraction(frame, head_box)
            label = "good" if row["label"] == "good" else "teammate-as-target"
            rows_by_label[label].append((row["filename"], frac))

    for label, rows in rows_by_label.items():
        print(f"\n{label} (n={len(rows)})")
        for filename, frac in rows:
            print(f"  {filename:20s} orb_white_fraction={frac:.4f}")
        if rows:
            vals = np.array([r[1] for r in rows])
            print(f"  orb_white_fraction: min={vals.min():.4f} mean={vals.mean():.4f} max={vals.max():.4f}")

    good = rows_by_label["good"]
    bad = rows_by_label["teammate-as-target"]
    if good and bad:
        print("\nthreshold sweep (orb_white_fraction >= T rejects as ally):")
        print(f"{'T':>8} {'good_wrongly_rejected':>24} {'teammates_caught':>18}")
        all_vals = sorted(set([r[1] for r in good] + [r[1] for r in bad]))
        for t in [0.0] + all_vals:
            fp = sum(1 for r in good if r[1] >= t)
            tp = sum(1 for r in bad if r[1] >= t)
            print(f"{t:>8.4f} {fp:>10}/{len(good):<12} {tp:>8}/{len(bad)}")


if __name__ == "__main__":
    main()
