# One-shot backlog driver: analyze every unprocessed Downloads VOD, then run
# the three pre-flag predict scripts on each. Analysis only -- no review.
# Corrected success check (engagements.csv with >0 rows), per PIPELINE_STATE.md.

import csv
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass  # pythonw.exe / no real stdout

DL = Path(r"C:\Users\alexh\Downloads")
REPO = Path(r"C:\Users\alexh\PycharmProjects\valorant-crosshair-analyzer")
LOG = REPO / "backlog_driver_log.txt"
ID = re.compile(r"\[([A-Za-z0-9_-]{11})\]")

# already done under a different naming scheme (ShadowPlay), false-flag by slug
SKIP_SLUGS = {"valorant-demon1-chamber-gameplay-radiant-ranked-full-match"}


# run child scripts with no flashing console window (steals game focus otherwise)
_NO_WINDOW = 0x08000000


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.strip().lower()).strip("-")[:80]


def candidates():
    by_id = {}
    for ext in ("*.mp4", "*.webm"):
        for p in DL.glob(ext):
            m = ID.search(p.name)
            if not m:
                continue
            vid = m.group(1)
            slug = slugify(p.name[:m.start()]) or vid
            cur = by_id.get(vid)
            if cur is None or (cur[0].suffix == ".webm" and p.suffix == ".mp4"):
                by_id[vid] = (p, slug)
    return by_id


def ok(out_dir):
    csv_path = out_dir / "engagements.csv"
    if not csv_path.exists():
        return False
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) > 1  # header + >=1 row


def main():
    todo = []
    for vid, (path, slug) in sorted(candidates().items(), key=lambda kv: kv[1][1]):
        if slug in SKIP_SLUGS:
            continue
        if ok(REPO / f"engagements_{slug}"):
            continue
        todo.append((slug, path))

    log(f"backlog driver start: {len(todo)} videos to analyze")
    done, failed = [], []

    for i, (slug, path) in enumerate(todo, 1):
        out = f"engagements_{slug}"
        out_dir = REPO / out
        if ok(out_dir):
            log(f"[{i}/{len(todo)}] already done, skip: {slug}")
            continue
        log(f"[{i}/{len(todo)}] analyzing: {path.name} -> {out}")
        t0 = time.time()
        r = subprocess.run(
            [sys.executable, "analyze_crosshair_placement.py",
             "--clip", str(path), "--output", out],
            cwd=str(REPO), creationflags=_NO_WINDOW,
        )
        dt = time.time() - t0

        if r.returncode == 0 and ok(out_dir):
            with open(out_dir / "engagements.csv", encoding="utf-8") as fh:
                n = sum(1 for _ in fh) - 1
            log(f"[{i}/{len(todo)}] done in {dt/60:.1f}min: {n} raw engagements")
            for pred in ("predict_teammate_prob.py", "predict_gunmodel_prob.py",
                         "predict_enemy_prob.py"):
                pr = subprocess.run([sys.executable, pred, out], cwd=str(REPO),
                                    creationflags=_NO_WINDOW)
                log(f"    {pred}: exit {pr.returncode}")
            log(f"    REVIEW REQUIRED: python review_engagements.py {out} "
                f"&& python filter_engagements.py {out}")
            done.append(slug)
        else:
            log(f"[{i}/{len(todo)}] FAILED (exit {r.returncode}, ok={ok(out_dir)}) "
                f"after {dt/60:.1f}min: {slug}")
            failed.append(slug)

    log(f"backlog driver complete: {len(done)} analyzed, {len(failed)} failed")
    if failed:
        log("failed: " + ", ".join(failed))
    log("NEXT: review + filter each analyzed folder, then retrain all 3 classifiers")


if __name__ == "__main__":
    main()
