"""
coach_clip.py -- one-command crosshair-discipline coaching for your OWN clip.

    python coach_clip.py --clip "C:\\Users\\you\\Videos\\my_deathmatch.mp4"

Runs the whole pipeline nearly hands-off:

  1. analyze_crosshair_placement.py on the clip (~30-50 min, uses the GPU) --
     finds every "enemy head newly visible" moment and how far the crosshair
     was from it.
  2. auto-classify every detected reveal with the three trained classifiers
     (ally / gunmodel / enemy -- see train_*_classifier.py). Confident false
     positives are dropped automatically, confident real reveals kept
     automatically.
  3. spot-check GUI for ONLY the uncertain middle (combined bad-score between
     AUTO_KEEP_AT and AUTO_DROP_AT) -- normally a handful of frames, ~10s of
     clicking. Keys: K / Right = keep, D / Left = drop, U = undo, Esc = quit.
  4. compare your kept reveals against the locked pro baseline
     (analysis_output/engagements_pooled.csv) and write a coaching report.

Output lands in  coach_<slug>/ :
    engagements.csv, annotated t*.jpg frames   (from step 1)
    coach_scores.csv        per-reveal classifier scores
    coach_meta.json         clip width/height/fps
    spotcheck.csv           your keep/drop calls on the uncertain frames
    engagements_coached.csv the auto+spotcheck kept set
    coaching_report.md      the writeup

Re-running is cheap: steps 1 and 2 are skipped if their output already
exists (pass --reanalyze / --rescore to force), and the spot-check resumes
where you left off -- so quitting the GUI early and finishing later does not
repeat the 30-minute analysis.

IMPORTANT: the auto-filter is ~95% accurate, not a human reviewer. That is
fine for trend feedback on your own play. It is deliberately NOT good enough
to feed the pro baseline -- that still needs the full manual review gate
(review_engagements.py / filter_engagements.py). The kept file here is named
engagements_coached.csv, not engagements_filtered.csv, so
analyze_pro_baseline.py never picks it up by accident.
"""

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

import cv2

import predict_teammate_prob as ally_clf
import predict_gunmodel_prob as gun_clf
import predict_enemy_prob as enemy_clf
from extract_ally_classifier_dataset import padded_crop
from calibrate_ally_filter import find_scored_box
from extract_hard_negatives_from_review import extract_frame
from analyze_crosshair_placement import HEAD_MODEL_PATH, BODY_MODEL_PATH, analyze

REPO_ROOT = Path(__file__).resolve().parent
try:
    from app_paths import resource_path
    POOLED_CSV = resource_path("analysis_output/engagements_pooled.csv")
except Exception:  # pragma: no cover
    POOLED_CSV = REPO_ROOT / "analysis_output" / "engagements_pooled.csv"

# Locked pro baseline (2026-09-01: 100 VODs / 2741 engagements). Only used
# if analysis_output/engagements_pooled.csv is missing.
BASELINE_FALLBACK = {"median": 3.06, "mean": 6.31, "p90": 16.3, "preaimed_pct": 64.0}

PREAIMED_THRESHOLD_PCT = 5.0   # crosshair-to-head <= this counts as "pre-aimed"
AUTO_DROP_AT = 0.70            # combined bad-score >= this -> drop, no human look
AUTO_KEEP_AT = 0.30            # combined bad-score <= this -> keep, no human look

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return SLUG_RE.sub("-", name.lower()).strip("-")[:80]


# ---------------------------------------------------------------------------
# Step 1 -- analysis
# ---------------------------------------------------------------------------

def run_analysis(clip: Path, outdir: Path, reanalyze: bool, progress=None) -> list:
    say = progress or print
    eng_csv = outdir / "engagements.csv"
    if eng_csv.exists() and not reanalyze:
        rows = _read_engagements(eng_csv)
        say(f"[1/4] reusing {eng_csv} ({len(rows)} reveals)")
        return rows

    say(f"[1/4] analyzing {clip.name} -- this takes ~30-50 min ...")
    # Call the analysis in-process (no python.exe in the portable build).
    analyze(str(clip), str(outdir), progress=progress)
    if not eng_csv.exists():
        raise SystemExit(f"no {eng_csv} was produced")
    rows = _read_engagements(eng_csv)
    if not rows:
        raise SystemExit("0 reveals detected in this clip -- nothing to coach")
    say(f"[1/4] {len(rows)} reveals detected")
    return rows


def _read_engagements(path: Path) -> list:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def frame_name(ts: float) -> str:
    # Matches the annotated-frame naming in analyze_crosshair_placement.py.
    return f"t{ts:07.2f}s.jpg"


# ---------------------------------------------------------------------------
# Step 2 -- classify every reveal
# ---------------------------------------------------------------------------

def score_reveals(clip: Path, outdir: Path, rows: list, rescore: bool) -> tuple:
    scores_csv = outdir / "coach_scores.csv"
    meta_path = outdir / "coach_meta.json"

    if scores_csv.exists() and meta_path.exists() and not rescore:
        with open(scores_csv, newline="") as f:
            scores = {r["filename"]: r for r in csv.DictReader(f)}
        meta = json.loads(meta_path.read_text())
        print(f"[2/4] reusing {scores_csv} ({len(scores)} scored)")
        return scores, meta

    import torch
    from ultralytics import YOLO
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[2/4] scoring {len(rows)} reveals with 3 classifiers (device={device}) ...")

    m_ally = ally_clf.build_model(device)
    m_gun = gun_clf.build_model(device)
    m_enemy = enemy_clf.build_model(device)
    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise SystemExit(f"could not open {clip}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    meta = {"clip": str(clip), "fps": fps, "frame_w": frame_w, "frame_h": frame_h}
    meta_path.write_text(json.dumps(meta, indent=2))

    fields = ("filename", "timestamp_s", "teammate_prob", "gunmodel_prob",
              "bad_prob", "bad_score", "box_ok")
    scores = {}
    no_crop = 0
    redetected = 0
    with open(scores_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for row in rows:
            ts = float(row["timestamp_s"])
            fname = frame_name(ts)
            frame = extract_frame(clip, ts)  # ffmpeg fast keyframe seek

            box = _row_box(row)  # saved by a post-2026-08-23 analysis run
            if box is None and frame is not None:
                # Old engagements.csv without box_* columns -- re-detect the
                # scored box the same way the predict_*_prob.py scripts do.
                box = find_scored_box(frame, head_model, body_model,
                                      frame.shape[1], frame.shape[0])
                if box is not None:
                    redetected += 1

            crop = None if (box is None or frame is None) else padded_crop(frame, box)
            if crop is None or crop.size == 0:
                no_crop += 1
                rec = _score_record(fname, ts, None, None, None, None, box_ok=False)
            else:
                t = ally_clf.predict_prob(m_ally, device, crop)
                g = gun_clf.predict_prob(m_gun, device, crop)
                b = enemy_clf.predict_prob(m_enemy, device, crop)
                rec = _score_record(fname, ts, t, g, b, max(t, g, b), box_ok=True)
            scores[fname] = rec
            w.writerow([rec[k] for k in fields])
    if redetected:
        print(f"[2/4] re-detected the box for {redetected} reveal(s) (no saved coords)")
    if no_crop:
        print(f"[2/4] {no_crop} reveal(s) had no usable crop -> sent to spot-check")
    return scores, meta


def _score_record(fname, ts, t, g, b, score, box_ok):
    def fmt(x):
        return "" if x is None else f"{x:.4f}"
    return {
        "filename": fname,
        "timestamp_s": f"{ts:.2f}",
        "teammate_prob": fmt(t),
        "gunmodel_prob": fmt(g),
        "bad_prob": fmt(b),
        "bad_score": fmt(score),
        "box_ok": "1" if box_ok else "0",
    }


def _row_box(row):
    try:
        return (float(row["box_x1"]), float(row["box_y1"]),
                float(row["box_x2"]), float(row["box_y2"]))
    except (KeyError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Step 3 -- split + spot-check the uncertain middle
# ---------------------------------------------------------------------------

def split_scores(scores: dict) -> tuple:
    auto_keep, auto_drop, uncertain = [], [], []
    for fname, rec in scores.items():
        s = rec["bad_score"]
        if s == "":
            uncertain.append(fname)      # no crop -> human decides
            continue
        s = float(s)
        if s >= AUTO_DROP_AT:
            auto_drop.append(fname)
        elif s <= AUTO_KEEP_AT:
            auto_keep.append(fname)
        else:
            uncertain.append(fname)
    return auto_keep, auto_drop, uncertain


def spot_check(outdir: Path, uncertain: list, scores: dict, headless: bool,
               gui=None) -> dict:
    sc_csv = outdir / "spotcheck.csv"
    verdicts = {}
    if sc_csv.exists():
        with open(sc_csv, newline="") as f:
            verdicts = {r["filename"]: r["verdict"] for r in csv.DictReader(f)}

    remaining = [f for f in uncertain if f not in verdicts]
    if not remaining:
        print(f"[3/4] spot-check: nothing to do ({len(uncertain)} uncertain, all recorded)")
        return verdicts

    if headless:
        for fname in remaining:
            s = scores[fname]["bad_score"]
            verdicts[fname] = "drop" if (s != "" and float(s) >= 0.5) else "keep"
        _write_spotcheck(sc_csv, verdicts)
        print(f"[3/4] spot-check: --headless, auto-split {len(remaining)} uncertain at 0.5")
        return verdicts

    print(f"[3/4] spot-check: {len(remaining)} uncertain frame(s) -- opening GUI")
    try:
        if gui:
            gui(outdir, remaining, scores, sc_csv, verdicts)
        else:
            _SpotCheckApp(outdir, remaining, scores, sc_csv, verdicts).run()
    except Exception as exc:  # noqa: BLE001  -- tkinter on a headless box, etc.
        print(f"      GUI unavailable ({exc}); falling back to 0.5 split")
        for fname in remaining:
            s = scores[fname]["bad_score"]
            verdicts.setdefault(fname, "drop" if (s != "" and float(s) >= 0.5) else "keep")
        _write_spotcheck(sc_csv, verdicts)
        return verdicts

    with open(sc_csv, newline="") as f:
        verdicts = {r["filename"]: r["verdict"] for r in csv.DictReader(f)}
    still = [f for f in uncertain if f not in verdicts]
    if still:
        print(f"      quit early -- {len(still)} uncertain frame(s) left unreviewed, "
              f"treated as DROP. Re-run to finish them.")
    return verdicts


def _write_spotcheck(path: Path, verdicts: dict):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "verdict"])
        for k, v in verdicts.items():
            w.writerow([k, v])


class _SpotCheckApp:
    """Minimal keep/drop reviewer for just the uncertain frames."""

    def __init__(self, outdir, frames, scores, csv_path, verdicts):
        import tkinter as tk
        from PIL import Image, ImageTk

        self._tk = tk
        self._Image = Image
        self._ImageTk = ImageTk
        self.outdir = outdir
        self.frames = frames
        self.scores = scores
        self.csv_path = csv_path
        self.verdicts = dict(verdicts)
        self.index = 0
        self.history = []

        self.root = tk.Tk()
        self.root.title("Spot-check uncertain reveals")
        self.image_label = tk.Label(self.root)
        self.image_label.pack()
        self.status = tk.Label(self.root, font=("Segoe UI", 12))
        self.status.pack(pady=4)
        bar = tk.Frame(self.root)
        bar.pack(pady=6)
        tk.Button(bar, text="Keep (K / \u2192)", bg="#2e7d32", fg="white",
                  command=self.keep).pack(side=tk.LEFT, padx=6)
        tk.Button(bar, text="Drop (D / \u2190)", bg="#c62828", fg="white",
                  command=self.drop).pack(side=tk.LEFT, padx=6)
        tk.Button(bar, text="Undo (U)", command=self.undo).pack(side=tk.LEFT, padx=12)
        self.root.bind("<k>", lambda e: self.keep())
        self.root.bind("<Right>", lambda e: self.keep())
        self.root.bind("<d>", lambda e: self.drop())
        self.root.bind("<Left>", lambda e: self.drop())
        self.root.bind("<u>", lambda e: self.undo())
        self.root.bind("<BackSpace>", lambda e: self.undo())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def run(self):
        self._show()
        self.root.mainloop()

    def _show(self):
        if self.index >= len(self.frames):
            self.root.destroy()
            return
        fname = self.frames[self.index]
        path = self.outdir / fname
        img = self._Image.open(path)
        img.thumbnail((1400, 850))
        self.photo = self._ImageTk.PhotoImage(img)
        self.image_label.configure(image=self.photo)
        rec = self.scores[fname]
        s = rec["bad_score"]
        s_txt = "no crop" if s == "" else f"bad-score {float(s):.2f}"
        self.status.configure(
            text=f"{fname}   ({self.index + 1}/{len(self.frames)})   {s_txt}   "
                 f"[t={rec['teammate_prob'] or '-'} g={rec['gunmodel_prob'] or '-'} "
                 f"b={rec['bad_prob'] or '-'}]   "
                 f"Is the blue/orange box on a REAL enemy head?")

    def _record(self, verdict):
        fname = self.frames[self.index]
        self.verdicts[fname] = verdict
        self.history.append(fname)
        _write_spotcheck(self.csv_path, self.verdicts)
        self.index += 1
        self._show()

    def keep(self):
        self._record("keep")

    def drop(self):
        self._record("drop")

    def undo(self):
        if not self.history:
            return
        fname = self.history.pop()
        self.verdicts.pop(fname, None)
        _write_spotcheck(self.csv_path, self.verdicts)
        self.index = max(0, self.index - 1)
        self._show()


# ---------------------------------------------------------------------------
# Step 4 -- build the kept set, compare to the pro baseline, write the report
# ---------------------------------------------------------------------------

def build_kept(rows: list, auto_keep: list, uncertain: set, spot_verdicts: dict) -> list:
    keep_names = set(auto_keep)
    keep_names |= {f for f, v in spot_verdicts.items()
                   if v == "keep" and f in uncertain}
    return [r for r in rows if frame_name(float(r["timestamp_s"])) in keep_names]


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def distro(values: list) -> dict:
    v = sorted(values)
    n = len(v)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "median": statistics.median(v),
        "mean": statistics.mean(v),
        "p90": _pct(v, 90),
        "worst": v[-1],
        "best": v[0],
        "preaimed_pct": 100.0 * sum(1 for x in v if x <= PREAIMED_THRESHOLD_PCT) / n,
    }


def load_baseline() -> dict:
    if not POOLED_CSV.exists():
        b = dict(BASELINE_FALLBACK)
        b["source"] = "hardcoded fallback (analysis_output/engagements_pooled.csv missing)"
        return b
    dists, smoke_dists, clear_dists = [], [], []
    with open(POOLED_CSV, newline="") as f:
        for r in csv.DictReader(f):
            try:
                d = float(r["distance_pct"])
            except (KeyError, ValueError):
                continue
            dists.append(d)
            if str(r.get("smoke", "")).strip().lower() == "true":
                smoke_dists.append(d)
            else:
                clear_dists.append(d)
    b = distro(dists)
    b["source"] = f"analysis_output/engagements_pooled.csv ({len(dists)} pro reveals)"
    b["smoke_median"] = statistics.median(smoke_dists) if smoke_dists else None
    b["clear_median"] = statistics.median(clear_dists) if clear_dists else None
    return b


def vertical_offset(kept_rows: list, frame_h: int) -> float | None:
    """Median (box-center-y minus screen-center-y) as a fraction of frame height.

    Positive  -> heads sit BELOW the crosshair  -> crosshair rides too HIGH.
    Negative  -> heads sit ABOVE the crosshair  -> crosshair rides too LOW.
    """
    if not frame_h:
        return None
    offs = []
    for r in kept_rows:
        box = _row_box(r)
        if box is None:
            continue
        box_cy = (box[1] + box[3]) / 2
        offs.append((box_cy - frame_h / 2) / frame_h)
    return statistics.median(offs) if offs else None


def make_tips(me: dict, base: dict, voff, kept_rows) -> list:
    tips = []
    if me["n"] == 0:
        return ["No reveals survived filtering -- nothing to analyse. "
                "Either the clip had very little real combat, or the detector "
                "struggled with it. Try a Deathmatch clip."]

    ratio = me["median"] / base["median"] if base.get("median") else None
    tips.append(
        f"**Pre-aim gap.** Your median crosshair-to-head at reveal is "
        f"**{me['median']:.1f}%** of screen width vs the pro baseline "
        f"**{base['median']:.1f}%**"
        + (f" ({ratio:.1f}x)." if ratio else ".")
    )
    if ratio is None:
        pass
    elif ratio <= 1.3:
        tips.append("You are already near pro level on pre-aim. Keep drilling to hold it.")
    elif ratio <= 2.0:
        tips.append("Noticeably wider than pros. You arrive on target but you are not "
                    "pre-placed -- pick the exact pixel an enemy will show at, and put "
                    "your crosshair there *before* you clear the angle, not as you swing.")
    elif ratio <= 3.5:
        tips.append("Well wide of pros -- you are reacting to enemies rather than "
                    "expecting them. Slow your entries down. Move corner to corner, "
                    "stopping with the crosshair pre-placed at head height on each new "
                    "angle before you expose yourself.")
    else:
        tips.append("Very wide. Crosshair discipline is the single highest-value thing "
                    "to drill right now: a Deathmatch with one rule -- never let the "
                    "crosshair drop off head height, and pre-aim every corner you walk past.")

    tips.append(
        f"**Pre-aimed rate.** {me['preaimed_pct']:.0f}% of your reveals were pre-aimed "
        f"(crosshair within {PREAIMED_THRESHOLD_PCT:.0f}% of the head) vs "
        f"**{base['preaimed_pct']:.0f}%** for pros."
    )
    if base.get("preaimed_pct") and me["preaimed_pct"] < base["preaimed_pct"] - 10:
        tips.append("That gap is where the time is lost -- a non-pre-aimed reveal costs "
                    "you a flick (~150-250 ms) before you can even start shooting.")

    if base.get("p90"):
        mr = me["median"] / base["median"]
        pr = me["p90"] / base["p90"]
        if pr > mr * 1.4:
            tips.append(
                f"**Consistency.** Your worst reveals are disproportionately bad "
                f"(your p90 {me['p90']:.0f}% vs pro p90 {base['p90']:.0f}%). This is "
                f"inconsistency, not a fixed offset -- usually panic-swinging or "
                f"wide-clearing when you get surprised. The floor matters more than the "
                f"ceiling here.")

    if voff is not None:
        if voff < -0.03:
            tips.append(
                f"**Crosshair height.** Enemy heads sat on average {abs(voff) * 100:.0f}% "
                f"of the screen height *above* your crosshair -- you are aiming low "
                f"(chest / floor). Raise your resting crosshair to head height. This is "
                f"the most common fixable mistake and it is costing you vertical flicks.")
        elif voff > 0.03:
            tips.append(
                f"**Crosshair height.** Enemy heads sat on average {voff * 100:.0f}% of "
                f"the screen height *below* your crosshair -- you are aiming high (over "
                f"their heads). Bring the resting crosshair down to head level.")
        else:
            tips.append("**Crosshair height.** Your resting height is good -- heads land "
                        "near crosshair level vertically. The gap is horizontal / timing.")

    if base.get("clear_median") and base.get("smoke_median") is not None:
        smoky = [float(r["distance_pct_width"]) for r in kept_rows
                 if str(r.get("smoke_present", "")).strip().lower() == "true"]
        clear = [float(r["distance_pct_width"]) for r in kept_rows
                 if str(r.get("smoke_present", "")).strip().lower() != "true"]
        if len(smoky) >= 6 and len(clear) >= 6:
            sm, cm = statistics.median(smoky), statistics.median(clear)
            pro_pen = base["smoke_median"] - base["clear_median"]
            my_pen = sm - cm
            if my_pen > pro_pen + 1.5:
                tips.append(
                    f"**Smokes.** You lose pre-aim through smoke far more than pros do "
                    f"(your smoke median {sm:.1f}% vs your clear {cm:.1f}%; pros only "
                    f"give up {pro_pen:+.1f}%). Pre-aim the smoke edge at head height and "
                    f"hold -- do not walk in swinging.")

    worst = sorted(kept_rows, key=lambda r: -float(r["distance_pct_width"]))[:5]
    if worst:
        lines = ", ".join(f"{frame_name(float(r['timestamp_s']))} ({float(r['distance_pct_width']):.0f}%)"
                          for r in worst)
        tips.append(
            f"**Look at your 5 worst reveals:** {lines}. Open those JPGs in the "
            f"`coach_*/` folder -- for each one decide: was the crosshair just badly "
            f"placed, or were you caught mid-rotate / mid-reload? Different fixes.")

    return tips


def write_report(outdir: Path, clip: Path, me: dict, base: dict, voff,
                 counts: dict, tips: list) -> Path:
    md = outdir / "coaching_report.md"
    L = []
    w = L.append
    w(f"# Crosshair coaching -- {clip.name}\n")
    w(f"_Pro baseline source: {base['source']}_\n")
    w("## Your numbers vs pro\n")
    w("| metric | you | pro baseline |")
    w("|---|---|---|")
    if me["n"]:
        w(f"| reveals analysed | {me['n']} | {base.get('n', '-')} |")
        w(f"| median pre-aim (% screen width) | **{me['median']:.2f}** | {base['median']:.2f} |")
        w(f"| mean | {me['mean']:.2f} | {base.get('mean', float('nan')):.2f} |")
        w(f"| p90 (worst 10%) | {me['p90']:.2f} | {base.get('p90', float('nan')):.2f} |")
        w(f"| pre-aimed rate (<= {PREAIMED_THRESHOLD_PCT:.0f}%) | **{me['preaimed_pct']:.0f}%** | {base['preaimed_pct']:.0f}% |")
        w(f"| best / worst single reveal | {me['best']:.1f}% / {me['worst']:.1f}% | - |")
    w("")
    w("## How the reveals were filtered\n")
    w(f"- detected by the pipeline: **{counts['total']}**")
    w(f"- auto-kept (confident real): {counts['auto_keep']}")
    w(f"- auto-dropped (confident false positive): {counts['auto_drop']}")
    w(f"- sent to spot-check: {counts['uncertain']}  "
      f"(you kept {counts['spot_keep']}, dropped {counts['spot_drop']})")
    w(f"- **final kept set: {counts['kept']}**  -> `engagements_coached.csv`")
    w("")
    w("## Coaching\n")
    for t in tips:
        w(f"- {t}")
    w("")
    w("---")
    w("_Auto-filtered with the ally / gunmodel / enemy classifiers (~95% accurate). "
      "Good for tracking your own trend; not clean enough to feed the pro baseline._")
    md.write_text("\n".join(L), encoding="utf-8")
    return md


# ---------------------------------------------------------------------------

def run_coaching(clip: Path, outdir: Path = None, *, reanalyze=False,
                 rescore=False, headless=False, progress=None,
                 spotcheck_gui=None) -> dict:
    """Full pipeline for one clip. Returns a result dict (paths + numbers).

    progress:       optional callable(str) for status lines.
    spotcheck_gui:  optional callable(outdir, frames, scores, csv_path,
                    verdicts) that runs the keep/drop reviewer. Defaults to
                    the built-in tkinter app; pass a no-op / custom one from
                    another UI. Ignored when headless.
    """
    say = progress or print
    clip = Path(clip)
    if not clip.exists():
        raise SystemExit(f"clip not found: {clip}")
    # Default: a coach_<clipname> folder right next to the user's clip, so
    # the results land somewhere they can actually find (not buried in the
    # frozen app's _internal/).
    outdir = Path(outdir) if outdir else clip.parent / f"coach_{slugify(clip.stem)}"
    outdir.mkdir(parents=True, exist_ok=True)

    rescore = rescore or reanalyze  # new analysis -> new scores
    if rescore:
        (outdir / "spotcheck.csv").unlink(missing_ok=True)

    rows = run_analysis(clip, outdir, reanalyze, progress=progress)
    scores, meta = score_reveals(clip, outdir, rows, rescore)
    auto_keep, auto_drop, uncertain = split_scores(scores)
    spot_verdicts = spot_check(outdir, uncertain, scores, headless,
                               gui=spotcheck_gui)
    uncertain_set = set(uncertain)

    kept_rows = build_kept(rows, auto_keep, uncertain_set, spot_verdicts)
    out_csv = outdir / "engagements_coached.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(kept_rows)

    me = distro([float(r["distance_pct_width"]) for r in kept_rows])
    base = load_baseline()
    voff = vertical_offset(kept_rows, meta.get("frame_h"))
    counts = {
        "total": len(rows),
        "auto_keep": len(auto_keep),
        "auto_drop": len(auto_drop),
        "uncertain": len(uncertain),
        "spot_keep": sum(1 for f, v in spot_verdicts.items()
                         if v == "keep" and f in uncertain_set),
        "spot_drop": sum(1 for f, v in spot_verdicts.items()
                         if v == "drop" and f in uncertain_set),
        "kept": len(kept_rows),
    }
    tips = make_tips(me, base, voff, kept_rows)
    report = write_report(outdir, clip, me, base, voff, counts, tips)
    from report_html import write_html_report
    html_report = write_html_report(outdir, clip, me, base, voff, counts, tips, kept_rows)

    say("")
    say("=" * 60)
    say(f"[4/4] {counts['kept']} / {counts['total']} reveals kept after filtering")
    if me["n"]:
        say(f"      your median pre-aim: {me['median']:.2f}%   pro: {base['median']:.2f}%")
        say(f"      your pre-aimed rate: {me['preaimed_pct']:.0f}%   pro: {base['preaimed_pct']:.0f}%")
    say(f"      report:  {report}")
    say(f"      html:    {html_report}")
    say(f"      kept set: {out_csv}")
    say("=" * 60)
    for t in tips:
        say(" - " + re.sub(r"\*\*", "", t))

    return {
        "outdir": outdir,
        "report_md": report,
        "report_html": html_report,
        "kept_csv": out_csv,
        "me": me,
        "base": base,
        "counts": counts,
        "tips": tips,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", required=True, help="path to your gameplay clip")
    ap.add_argument("--output", default=None,
                    help="output dir (default: coach_<clip-slug>/)")
    ap.add_argument("--reanalyze", action="store_true",
                    help="force step 1 even if engagements.csv already exists")
    ap.add_argument("--rescore", action="store_true",
                    help="force step 2 even if coach_scores.csv already exists")
    ap.add_argument("--headless", action="store_true",
                    help="skip the spot-check GUI; split the uncertain frames at 0.5")
    args = ap.parse_args()
    run_coaching(Path(args.clip), args.output, reanalyze=args.reanalyze,
                 rescore=args.rescore, headless=args.headless)


if __name__ == "__main__":
    main()
