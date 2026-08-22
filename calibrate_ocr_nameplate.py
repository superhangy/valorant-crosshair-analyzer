"""
Calibrate an OCR-based ally-nameplate filter against real labeled data.

The existing has_ally_nameplate() checks a solid-color band BELOW the box
for ally-green -- calibrate_ally_filter.py found that band reads ~0 pixels
for both good and teammate-as-target frames (56/57 good, 100/101 teammate),
which points at a wrong region, not a bad threshold: Valorant's floating
ally nametag renders ABOVE the player model, not below.

For every "good" and "teammate-as-target" row across the reviewed
engagements folders, re-extracts the source frame, recovers the scored box
(same head+body detection calibrate_ally_filter.py uses), then runs OCR
(same grayscale/upscale/Otsu/tesseract recipe as is_spectate_frame) on
several candidate bands ABOVE the box at increasing heights, and reports
how often each band reads legible text for good vs teammate-as-target.
Does NOT edit analyze_crosshair_placement.py.

Usage:
    python calibrate_ocr_nameplate.py engagements_demon1_chamber engagements_100t-asuna-pov-raze-on-split-valorant-ranked-gameplay engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay
"""

import csv
import re
import sys
from pathlib import Path

import cv2
import pytesseract
from ultralytics import YOLO

from analyze_crosshair_placement import (
    HEAD_MODEL_PATH, BODY_MODEL_PATH,
)
from calibrate_ally_filter import find_scored_box
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")

# Candidate bands above the box top edge, in pixels, tried independently.
BAND_HEIGHTS_PX = [30, 50, 70, 100]
SIDE_MARGIN_PX = 30
MIN_ALNUM_CHARS = 2  # ignore single stray-character OCR noise


def ocr_band_above(frame, box, band_height_px):
    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bx1 = max(0, x1 - SIDE_MARGIN_PX)
    bx2 = min(w_img, x2 + SIDE_MARGIN_PX)
    by1 = max(0, y1 - band_height_px)
    by2 = y1
    band = frame[by1:by2, bx1:bx2]
    if band.size == 0:
        return ""
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(binary, config="--psm 7")
    return "".join(c for c in text if c.isalnum())


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python calibrate_ocr_nameplate.py <engagements_folder> [<folder> ...]")

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
            texts = {h: ocr_band_above(frame, box, h) for h in BAND_HEIGHTS_PX}
            label = "good" if row["label"] == "good" else "teammate-as-target"
            rows_by_label[label].append((row["filename"], texts))

    for label, rows in rows_by_label.items():
        print(f"\n{label} (n={len(rows)})")
        for filename, texts in rows:
            hits = {h: t for h, t in texts.items() if len(t) >= MIN_ALNUM_CHARS}
            summary = ", ".join(f"{h}px={t!r}" for h, t in hits.items()) or "no text any band"
            print(f"  {filename:20s} {summary}")

    print("\nband-height summary (fraction of rows with legible text, len>=%d):" % MIN_ALNUM_CHARS)
    print(f"{'band_px':>8} {'good_hit_rate':>16} {'teammate_hit_rate':>20}")
    for h in BAND_HEIGHTS_PX:
        good = rows_by_label["good"]
        bad = rows_by_label["teammate-as-target"]
        good_hits = sum(1 for _, texts in good if len(texts[h]) >= MIN_ALNUM_CHARS)
        bad_hits = sum(1 for _, texts in bad if len(texts[h]) >= MIN_ALNUM_CHARS)
        good_rate = good_hits / len(good) if good else 0.0
        bad_rate = bad_hits / len(bad) if bad else 0.0
        print(f"{h:>8} {good_hits:>6}/{len(good):<8} {bad_hits:>6}/{len(bad):<8} ({good_rate:.2f} vs {bad_rate:.2f})")


if __name__ == "__main__":
    main()
