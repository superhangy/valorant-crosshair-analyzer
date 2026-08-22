"""
Build an image dataset for a small good-vs-teammate-as-target classifier.

For every "good" (real enemy) and "teammate-as-target" (false positive) row
across the reviewed engagements folders, re-extracts the source frame,
recovers the scored box (same head+body detection logic
calibrate_ally_filter.py uses), crops the box plus a padded margin (so the
classifier can see outline color, nameplate area, and weapon/viewmodel
context -- not just the bare box), and saves it under
dataset_ally_classifier/{good,teammate}/.

Usage:
    python extract_ally_classifier_dataset.py engagements_100t-asuna-pov-raze-on-split-valorant-ranked-gameplay engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay
"""

import csv
import re
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

from analyze_crosshair_placement import HEAD_MODEL_PATH, BODY_MODEL_PATH
from calibrate_ally_filter import find_scored_box
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")
REPO_ROOT = Path(__file__).resolve().parent
DATASET_DIR = REPO_ROOT / "dataset_ally_classifier"
CROP_PAD_FRAC = 0.35  # padding around the box, as a fraction of box size


def padded_crop(frame, box):
    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    px, py = bw * CROP_PAD_FRAC, bh * CROP_PAD_FRAC
    cx1 = max(0, int(x1 - px))
    cy1 = max(0, int(y1 - py))
    cx2 = min(w_img, int(x2 + px))
    cy2 = min(h_img, int(y2 + py))
    return frame[cy1:cy2, cx1:cx2]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python extract_ally_classifier_dataset.py <engagements_folder> [<folder> ...]")

    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    good_dir = DATASET_DIR / "good"
    teammate_dir = DATASET_DIR / "teammate"
    good_dir.mkdir(parents=True, exist_ok=True)
    teammate_dir.mkdir(parents=True, exist_ok=True)

    written = {"good": 0, "teammate": 0}
    skipped = failed_ffmpeg = failed_box = 0

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

        print(f"{folder.name}: {len(wanted)} rows ({video.name})")
        for row in wanted:
            m = TIMESTAMP_RE.match(row["filename"])
            if not m:
                continue
            ts = float(m.group(1))
            cls = "good" if row["label"] == "good" else "teammate"
            out_dir = good_dir if cls == "good" else teammate_dir
            out_path = out_dir / f"{slug[:40]}_t{ts:08.2f}s.jpg"
            if out_path.exists():
                skipped += 1
                continue

            frame = extract_frame(video, ts)
            if frame is None:
                failed_ffmpeg += 1
                continue
            frame_h, frame_w = frame.shape[:2]
            box = find_scored_box(frame, head_model, body_model, frame_w, frame_h)
            if box is None:
                failed_box += 1
                continue

            crop = padded_crop(frame, box)
            if crop.size == 0:
                failed_box += 1
                continue
            cv2.imwrite(str(out_path), crop)
            written[cls] += 1

    print(f"\nwritten: good={written['good']} teammate={written['teammate']} "
          f"| skipped(existing)={skipped} failed(ffmpeg)={failed_ffmpeg} "
          f"failed(no box)={failed_box}")
    print(f"-> {DATASET_DIR}")


if __name__ == "__main__":
    main()
