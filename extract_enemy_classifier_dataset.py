"""
Build an image dataset for a general good-vs-bad ("is this actually an
enemy") classifier -- unlike extract_ally_classifier_dataset.py /
extract_gunmodel_classifier_dataset.py (which each isolate one specific
false-positive category), this pulls EVERY reviewed row regardless of
category: label=="good" or label=="bad" (teammate-as-target,
gun-viewmodel-as-head, scoreboard-portrait-as-head, spectate-killcam,
other-bad, yoru-clone-as-head, utility-as-head, map-geometry-as-head --
all of it). The head/body YOLO detector that generates candidate boxes in
the first place is the noisy part (2148 good vs 3635 bad across all
reviews) -- this classifier's job is to catch the whole false-positive
population in one model, not just the two biggest categories.

Saves crops to dataset_enemy_classifier/{good,bad}/.

Usage:
    python extract_enemy_classifier_dataset.py engagements_<slug> [<folder> ...]
"""

import csv
import re
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

from analyze_crosshair_placement import HEAD_MODEL_PATH, BODY_MODEL_PATH
from calibrate_ally_filter import find_scored_box, load_boxes_from_engagements_csv
from extract_ally_classifier_dataset import padded_crop
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")
REPO_ROOT = Path(__file__).resolve().parent
DATASET_DIR = REPO_ROOT / "dataset_enemy_classifier"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python extract_enemy_classifier_dataset.py <engagements_folder> [<folder> ...]")

    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    good_dir = DATASET_DIR / "good"
    bad_dir = DATASET_DIR / "bad"
    good_dir.mkdir(parents=True, exist_ok=True)
    bad_dir.mkdir(parents=True, exist_ok=True)

    written = {"good": 0, "bad": 0}
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
            wanted = [r for r in reader if r["label"] in ("good", "bad")]

        saved_boxes = load_boxes_from_engagements_csv(folder)

        print(f"{folder.name}: {len(wanted)} rows ({video.name})")
        for row in wanted:
            m = TIMESTAMP_RE.match(row["filename"])
            if not m:
                continue
            ts = float(m.group(1))
            cls = row["label"]  # "good" or "bad"
            out_dir = good_dir if cls == "good" else bad_dir
            out_path = out_dir / f"{slug[:40]}_t{ts:08.2f}s.jpg"
            if out_path.exists():
                skipped += 1
                continue

            frame = extract_frame(video, ts)
            if frame is None:
                failed_ffmpeg += 1
                continue
            frame_h, frame_w = frame.shape[:2]
            box = saved_boxes.get(row["filename"])
            if box is None:
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

    print(f"\nwritten: good={written['good']} bad={written['bad']} "
          f"| skipped(existing)={skipped} failed(ffmpeg)={failed_ffmpeg} "
          f"failed(no box)={failed_box}")
    print(f"-> {DATASET_DIR}")


if __name__ == "__main__":
    main()
