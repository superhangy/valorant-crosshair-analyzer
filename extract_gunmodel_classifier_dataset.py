"""
Build an image dataset for a small good-vs-gun-viewmodel-as-target classifier.

Same approach as extract_ally_classifier_dataset.py (see that file for the
full rationale -- three hand-picked signals failed for teammate-as-target,
a trained crop classifier worked instead). For every "good" (real enemy) and
"gun-viewmodel-as-head" (false positive) row across the reviewed engagements
folders, re-extracts the source frame, recovers the scored box, crops the
box plus a padded margin, and saves it under
dataset_gunmodel_classifier/{good,gunmodel}/.

Usage:
    python extract_gunmodel_classifier_dataset.py engagements_<slug> [<folder> ...]
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
DATASET_DIR = REPO_ROOT / "dataset_gunmodel_classifier"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python extract_gunmodel_classifier_dataset.py <engagements_folder> [<folder> ...]")

    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    good_dir = DATASET_DIR / "good"
    gunmodel_dir = DATASET_DIR / "gunmodel"
    good_dir.mkdir(parents=True, exist_ok=True)
    gunmodel_dir.mkdir(parents=True, exist_ok=True)

    written = {"good": 0, "gunmodel": 0}
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
            wanted = [r for r in reader if r["label"] == "good" or r["category"] == "gun-viewmodel-as-head"]

        saved_boxes = load_boxes_from_engagements_csv(folder)

        print(f"{folder.name}: {len(wanted)} rows ({video.name})")
        for row in wanted:
            m = TIMESTAMP_RE.match(row["filename"])
            if not m:
                continue
            ts = float(m.group(1))
            cls = "good" if row["label"] == "good" else "gunmodel"
            out_dir = good_dir if cls == "good" else gunmodel_dir
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

    print(f"\nwritten: good={written['good']} gunmodel={written['gunmodel']} "
          f"| skipped(existing)={skipped} failed(ffmpeg)={failed_ffmpeg} "
          f"failed(no box)={failed_box}")
    print(f"-> {DATASET_DIR}")


if __name__ == "__main__":
    main()
