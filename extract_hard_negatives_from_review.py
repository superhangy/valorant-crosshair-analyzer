"""
Turn "bad" rows from a review_engagements.py CSV into hard-negative training
frames for the head detector.

Usage:
    python extract_hard_negatives_from_review.py engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay

Reads <folder>_review.csv (produced by review_engagements.py), finds the
matching source video in Downloads (same slug-matching logic as
batch_analyze_downloads.py), pulls the exact frame for every "bad" timestamp
via ffmpeg, converts to grayscale (matches dataset_head_gray/ - see
make_grayscale_dataset.py), and writes it into dataset_head_gray/train/ as a
background image (empty label = no head box). Idempotent: already-extracted
frames are skipped, safe to re-run after more review sessions.
"""

import csv
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import cv2

FFMPEG = r"C:\Users\alexh\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"
DOWNLOADS_DIR = Path(r"C:\Users\alexh\Downloads")
REPO_ROOT = Path(__file__).resolve().parent

DST_IMAGES = REPO_ROOT / "dataset_head_gray" / "train" / "images"
DST_LABELS = REPO_ROOT / "dataset_head_gray" / "train" / "labels"
TMP = REPO_ROOT / "hardneg_tmp.jpg"

YOUTUBE_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def find_video_for_slug(slug: str) -> "Path | None":
    for ext in ("*.mp4", "*.webm"):
        for path in DOWNLOADS_DIR.glob(ext):
            m = YOUTUBE_ID_RE.search(path.name)
            if not m:
                continue
            title = path.name[: m.start()].strip()
            if slugify(title) == slug:
                return path
    return None


def extract_frame(video: Path, timestamp: float) -> "cv2.Mat | None":
    TMP.unlink(missing_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-ss", str(timestamp), "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(TMP)],
        check=True, capture_output=True,
    )
    if not TMP.exists():
        return None
    return cv2.imread(str(TMP))


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python extract_hard_negatives_from_review.py <engagements_folder>")

    folder = Path(sys.argv[1])
    slug = folder.name.removeprefix("engagements_")
    review_csv = folder.parent / f"{folder.name}_review.csv"
    if not review_csv.exists():
        raise SystemExit(f"No review CSV found at {review_csv} - run review_engagements.py first")

    video = find_video_for_slug(slug)
    if video is None:
        raise SystemExit(f"Could not find a Downloads video matching slug '{slug}'")
    print(f"source video: {video.name}")

    DST_IMAGES.mkdir(parents=True, exist_ok=True)
    DST_LABELS.mkdir(parents=True, exist_ok=True)

    with open(review_csv, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] == "bad"]

    written = skipped = failed = 0
    for row in rows:
        m = TIMESTAMP_RE.match(row["filename"])
        if not m:
            print(f"SKIP (bad filename format): {row['filename']}")
            continue
        ts = float(m.group(1))
        category = row["category"] or "other-bad"
        name = f"hardneg_{slug[:40]}_{category}_t{ts:08.2f}s"

        if (DST_IMAGES / f"{name}.jpg").exists():
            skipped += 1
            continue

        frame = extract_frame(video, ts)
        if frame is None:
            print(f"FAILED (ffmpeg produced no frame): {row['filename']}")
            failed += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        cv2.imwrite(str(DST_IMAGES / f"{name}.jpg"), gray_3ch)
        (DST_LABELS / f"{name}.txt").write_text("")
        written += 1

    TMP.unlink(missing_ok=True)
    print(f"\n{written} written, {skipped} already present, {failed} failed "
          f"(of {len(rows)} bad frames) -> {DST_IMAGES}")


if __name__ == "__main__":
    main()
