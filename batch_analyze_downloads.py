# Batch-feeds already-downloaded VODs (yt-dlp, C:\Users\alexh\Downloads) into
# analyze_crosshair_placement.py, replacing the ShadowPlay live-recording
# stage. No ad-trimming here — trim_ads.py needs a browser ad-event capture
# that only exists for the live-recording flow, so downloaded VODs skip
# straight to analysis untrimmed.

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOWNLOADS_DIR = Path(r"C:\Users\alexh\Downloads")
REPO_ROOT = Path(__file__).resolve().parent
LOG_PATH = REPO_ROOT / "batch_analyze_log.txt"

YOUTUBE_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def slugify(title):
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80]


def find_candidates():
    """Map youtube_id -> chosen video path, preferring .mp4 over .webm."""
    by_id = {}
    for ext in ("*.mp4", "*.webm"):
        for path in DOWNLOADS_DIR.glob(ext):
            m = YOUTUBE_ID_RE.search(path.name)
            if not m:
                continue
            vid = m.group(1)
            title = path.name[: m.start()].strip()
            slug = slugify(title) or vid
            existing = by_id.get(vid)
            if existing is None or (existing[0].suffix == ".webm" and path.suffix == ".mp4"):
                by_id[vid] = (path, slug)
    return by_id


def already_processed(slug):
    out_dir = REPO_ROOT / f"engagements_{slug}"
    return (out_dir / "engagements.csv").exists()


def run_pass():
    candidates = find_candidates()
    if not candidates:
        log("scan: no matching downloaded videos found")
        return 0

    processed = 0
    for vid, (path, slug) in sorted(candidates.items(), key=lambda kv: kv[1][1]):
        if already_processed(slug):
            continue

        out_dir_name = f"engagements_{slug}"
        log(f"processing: {path.name} -> {out_dir_name}")
        result = subprocess.run(
            [sys.executable, "analyze_crosshair_placement.py",
             "--clip", str(path), "--output", out_dir_name],
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            log(f"done: {out_dir_name}")
            log(f"REVIEW REQUIRED before this data is used in any analysis:")
            log(f"    python review_engagements.py {out_dir_name}")
            log(f"    python filter_engagements.py {out_dir_name}")
            processed += 1
        else:
            log(f"FAILED (exit {result.returncode}): {path.name}")

        # one video per run — user preference, don't auto-chain (see PIPELINE_STATE.md)
        break

    return processed


if __name__ == "__main__":
    count = run_pass()
    log(f"pass complete: {count} video(s) newly processed")
