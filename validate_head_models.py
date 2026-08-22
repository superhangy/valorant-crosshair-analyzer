"""
Compare head-detector model(s) against a labeled ground-truth set built from
a review_engagements.py CSV - replaces the old one-off "legit_check_t*.jpg"
approach (those were temp files, deleted after use, not reusable).

Ground truth: "good" rows = should detect a head (recall check). "bad" rows
(per category: teammate-as-target, gun-viewmodel-as-head, etc.) = should NOT
detect a head (false-positive check). Frames are pulled fresh via ffmpeg from
the source video - NEVER read from the engagements folder's annotated JPGs,
since those already have a detection box drawn on them (a past session
mis-calibrated exactly this way once).

Preprocessing matches analyze_crosshair_placement.py's head_model call
exactly: grayscale -> back to 3-channel BGR, so results reflect production
behavior.

Usage:
    python validate_head_models.py engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay \
        --models runs/detect/runs/valorant_head_gray_v1/weights/best.pt \
                 runs/detect/runs/valorant_head_gray_v1-3/weights/best.pt \
        --sample 15
"""

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import cv2
from ultralytics import YOLO

from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

HEAD_CONF_THRESHOLD = 0.4  # must match analyze_crosshair_placement.py
PROBE_CONF = 0.05  # low floor so we can see what confidence a model *would* fire at

REPO_ROOT = Path(__file__).resolve().parent


def sample_rows(rows, n, seed=0):
    groups = defaultdict(list)
    for row in rows:
        key = "good" if row["label"] == "good" else row["category"]
        groups[key].append(row)
    rng = random.Random(seed)
    sampled = []
    for key, group in groups.items():
        rng.shuffle(group)
        sampled.extend(group[:n])
    return sampled


def gray_for_model(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="engagements_<slug> folder (needs a matching _review.csv)")
    ap.add_argument("--models", nargs="+", required=True, help="one or more .pt weight paths to compare")
    ap.add_argument("--sample", type=int, default=15, help="max frames per category (good + each bad category)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    folder = Path(args.folder)
    slug = folder.name.removeprefix("engagements_")
    review_csv = folder.parent / f"{folder.name}_review.csv"
    if not review_csv.exists():
        raise SystemExit(f"No review CSV found at {review_csv} - run review_engagements.py first")

    video = find_video_for_slug(slug)
    if video is None:
        raise SystemExit(f"Could not find a Downloads video matching slug '{slug}'")

    with open(review_csv, newline="") as f:
        all_rows = list(csv.DictReader(f))
    chosen = sample_rows(all_rows, args.sample, args.seed)
    print(f"validating on {len(chosen)} frames ({args.sample}/category max) from {video.name}")

    frames_dir = REPO_ROOT / f"validation_frames_{slug[:40]}"
    frames_dir.mkdir(exist_ok=True)

    cached = {}
    for row in chosen:
        ts_str = row["filename"][1:-5]  # "t0656.11s.jpg" -> "0656.11"
        cache_path = frames_dir / row["filename"]
        if cache_path.exists():
            frame = cv2.imread(str(cache_path))
        else:
            frame = extract_frame(video, float(ts_str))
            if frame is None:
                print(f"SKIP (ffmpeg failed): {row['filename']}")
                continue
            cv2.imwrite(str(cache_path), frame)
        cached[row["filename"]] = (frame, row)

    models = {Path(p).parent.parent.name: YOLO(p) for p in args.models}

    results = []
    for filename, (frame, row) in cached.items():
        gray_input = gray_for_model(frame)
        category = "good" if row["label"] == "good" else row["category"]
        record = {"filename": filename, "category": category}
        for model_name, model in models.items():
            preds = model(gray_input, conf=PROBE_CONF, verbose=False)
            confs = preds[0].boxes.conf.tolist() if len(preds[0].boxes) else []
            best_conf = max(confs) if confs else 0.0
            record[model_name] = round(best_conf, 3)
        results.append(record)

    out_csv = REPO_ROOT / f"validation_results_{slug[:40]}.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "category", *models.keys()])
        writer.writeheader()
        writer.writerows(results)
    print(f"per-frame results -> {out_csv}\n")

    by_category = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r)

    header = f"{'category':<28}{'n':>4}" + "".join(f"{m:>22}" for m in models)
    print(header)
    for category, rows in sorted(by_category.items()):
        line = f"{category:<28}{len(rows):>4}"
        for model_name in models:
            fired = sum(1 for r in rows if r[model_name] >= HEAD_CONF_THRESHOLD)
            if category == "good":
                line += f"{f'{fired}/{len(rows)} recall':>22}"
            else:
                line += f"{f'{fired}/{len(rows)} still fires':>22}"
        print(line)

    print("\n'good' rows: higher recall is better. bad-category rows: lower "
          "'still fires' count is better (that's the false-positive fix working).")


if __name__ == "__main__":
    main()
