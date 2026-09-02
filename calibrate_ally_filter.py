"""
Calibrate the ally-outline/nameplate color thresholds against real labeled
data instead of guessing constants.

For every "good" (real enemy) and "teammate-as-target" (false positive) row
across one or more reviewed engagements folders, re-extracts the source
frame, reruns the SAME box-selection logic analyze_crosshair_placement.py
uses (head+body model match, HUD exclusion, nearest-to-center) to recover
the exact box that got scored, then measures the raw ally_ring_fraction and
ally_nameplate_pixels for that box (the pipeline only stores the boolean
reject decision, not the underlying numbers).

Prints good vs teammate-as-target distributions for both signals, then
sweeps candidate thresholds to report best achievable separation. Does NOT
edit analyze_crosshair_placement.py -- review the printout and decide
whether to update ALLY_NAMEPLATE_PIXEL_THRESHOLD / ALLY_RING_FRACTION_THRESHOLD
by hand.

Usage:
    python calibrate_ally_filter.py engagements_demon1_chamber engagements_100t-asuna-pov-raze-on-split-valorant-ranked-gameplay engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay
"""

import csv
import re
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

from analyze_crosshair_placement import (
    HEAD_MODEL_PATH, BODY_MODEL_PATH, HEAD_CONF_THRESHOLD, BODY_CONF_THRESHOLD,
    TOP_EXCLUSION_HEIGHT_FRAC, BOTTOM_EXCLUSION_HEIGHT_FRAC,
    OUTLINE_RING_PX, ALLY_HUE_RANGE, OUTLINE_SAT_MIN, OUTLINE_VAL_MIN,
    NAMEPLATE_BAND_HEIGHT_PX, NAMEPLATE_SIDE_MARGIN_PX,
    ALLY_NAMEPLATE_HUE_RANGE, NAMEPLATE_SAT_MIN, NAMEPLATE_VAL_MIN,
    ring_mask_for_box, point_in_box,
)
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

import numpy as np

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")


def ally_ring_fraction(frame, box):
    mask = ring_mask_for_box(frame.shape, box, OUTLINE_RING_PX)
    ring_total = int(mask.sum())
    if ring_total == 0:
        return 0.0
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    ally_pixels = (
        (h >= ALLY_HUE_RANGE[0]) & (h <= ALLY_HUE_RANGE[1])
        & (s >= OUTLINE_SAT_MIN) & (v >= OUTLINE_VAL_MIN) & (mask == 1)
    )
    return int(ally_pixels.sum()) / ring_total


def ally_nameplate_pixels(frame, box):
    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bx1 = max(0, x1 - NAMEPLATE_SIDE_MARGIN_PX)
    bx2 = min(w_img, x2 + NAMEPLATE_SIDE_MARGIN_PX)
    by1 = max(0, y2)
    by2 = min(h_img, y2 + NAMEPLATE_BAND_HEIGHT_PX)
    band = frame[by1:by2, bx1:bx2]
    if band.size == 0:
        return 0
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    ally_pixels = (
        (h >= ALLY_NAMEPLATE_HUE_RANGE[0]) & (h <= ALLY_NAMEPLATE_HUE_RANGE[1])
        & (s >= NAMEPLATE_SAT_MIN) & (v >= NAMEPLATE_VAL_MIN)
    )
    return int(ally_pixels.sum())


def find_scored_box(frame, head_model, body_model, frame_w, frame_h):
    center_x, center_y = frame_w / 2, frame_h / 2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    head_input = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    head_results = head_model(head_input, conf=HEAD_CONF_THRESHOLD, verbose=False)
    head_boxes = head_results[0].boxes

    body_results = body_model(frame, conf=BODY_CONF_THRESHOLD, verbose=False)
    body_boxes_xyxy = [b.xyxy[0].tolist() for b in body_results[0].boxes]

    best_box = None
    best_dist = None
    for box in head_boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        hx, hy = (x1 + x2) / 2, (y1 + y2) / 2
        if hy < frame_h * TOP_EXCLUSION_HEIGHT_FRAC or hy > frame_h * BOTTOM_EXCLUSION_HEIGHT_FRAC:
            continue
        matching_body_box = next((bbox for bbox in body_boxes_xyxy if point_in_box(hx, hy, bbox)), None)
        if matching_body_box is None:
            continue
        outline_box = matching_body_box
        dist = ((hx - center_x) ** 2 + (hy - center_y) ** 2) ** 0.5
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_box = outline_box
    return best_box


def load_boxes_from_engagements_csv(folder: Path) -> dict:
    """filename -> (x1, y1, x2, y2) for every row that has box coords saved.

    engagements.csv written by analyze_crosshair_placement.py (post-2026-08-23)
    stores the exact scored box per engagement, so callers can crop directly
    instead of re-extracting the frame and rerunning find_scored_box -- which
    misses rows whenever ffmpeg's -ss seek lands on a slightly different frame
    than the original video-stream read did. Older engagements.csv files
    without the box_* columns return an empty dict (callers should fall back
    to find_scored_box in that case).
    """
    csv_path = folder / "engagements.csv"
    if not csv_path.exists():
        return {}
    boxes = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "box_x1" not in reader.fieldnames:
            return {}
        for row in reader:
            if not row.get("box_x1"):
                continue
            ts = float(row["timestamp_s"])
            filename = f"t{ts:07.2f}s.jpg"
            boxes[filename] = (
                float(row["box_x1"]), float(row["box_y1"]),
                float(row["box_x2"]), float(row["box_y2"]),
            )
    return boxes


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python calibrate_ally_filter.py <engagements_folder> [<folder> ...]")

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
            box = find_scored_box(frame, head_model, body_model, frame_w, frame_h)
            if box is None:
                print(f"  SKIP (couldn't recover scored box): {row['filename']}")
                continue
            ring_frac = ally_ring_fraction(frame, box)
            nameplate_px = ally_nameplate_pixels(frame, box)
            label = "good" if row["label"] == "good" else "teammate-as-target"
            rows_by_label[label].append((row["filename"], ring_frac, nameplate_px))

    for label, rows in rows_by_label.items():
        print(f"\n{label} (n={len(rows)})")
        for filename, ring_frac, nameplate_px in rows:
            print(f"  {filename:20s} ring_fraction={ring_frac:.3f}  nameplate_px={nameplate_px}")
        if rows:
            ring_vals = np.array([r[1] for r in rows])
            plate_vals = np.array([r[2] for r in rows])
            print(f"  ring_fraction:  min={ring_vals.min():.3f} mean={ring_vals.mean():.3f} max={ring_vals.max():.3f}")
            print(f"  nameplate_px:   min={plate_vals.min()} mean={plate_vals.mean():.1f} max={plate_vals.max()}")

    good = rows_by_label["good"]
    bad = rows_by_label["teammate-as-target"]
    if good and bad:
        print("\nthreshold sweep (nameplate_px >= T rejects as ally):")
        print(f"{'T':>4} {'good_wrongly_rejected':>24} {'teammates_caught':>18}")
        all_vals = sorted(set(r[2] for r in good + bad))
        for t in [0] + all_vals:
            fp = sum(1 for r in good if r[2] >= t)
            tp = sum(1 for r in bad if r[2] >= t)
            print(f"{t:>4} {fp:>10}/{len(good):<12} {tp:>8}/{len(bad)}")


if __name__ == "__main__":
    main()
