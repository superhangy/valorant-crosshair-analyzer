# Pro-VOD recording + analysis pipeline — state

Extension of the crosshair analyzer: records pro-player Valorant VODs from
a YouTube channel, trims YouTube-inserted ads out, then runs the same
`analyze_crosshair_placement.py` pipeline on them for comparison against
the learner's own pre-aim data. Personal/research use only, not
redistributed — same offline-analysis spirit as the rest of the project
(see PLAN.md), extended to cover third-party footage responsibly.

Channel: https://www.youtube.com/@valorantdaily1976/videos ("Valorant DAILY",
a VOD-reposting/compilation channel, not the pros' own channels)

**Status as of 2026-08-16 ~12:00pm: ShadowPlay recording stage RETIRED.**
User is now downloading VODs directly via `yt-dlp.exe`
(`C:\Users\alexh\Downloads\yt-dlp.exe`, up to ~100 videos) instead of
recording live. The ALEKSANDAR Neon partial recording (below) is
abandoned — no more Alt+F9 recording, no more `trim_ads.py` (it needs a
live browser ad-event capture that downloaded VODs don't have).

New flow: `yt-dlp` downloads land in `C:\Users\alexh\Downloads` as
`<title> [<youtube-id>].<fmt>.<ext>` (`.mp4` or `.webm`; in-progress
downloads sit as `*.part` until done). `batch_analyze_downloads.py` (repo
root) scans Downloads, matches completed `.mp4`/`.webm` files by YouTube-ID
pattern, skips non-matching/non-gameplay files and anything already
processed, and runs `analyze_crosshair_placement.py --clip <path> --output
engagements_<slug>` directly on each — untrimmed, no ad removal. Progress
logged to `batch_analyze_log.txt`.

**User preference: one video per run, do not auto-chain.** Even though the
script loops over all matching candidates in one process, the user wants
each video watched/gated manually — stop and report after one video
finishes rather than letting it roll into the next. Re-invoke the script
(or resume it) per video, don't leave it unattended across multiple
videos.

**Known bug (unfixed):** `log()` in `batch_analyze_downloads.py` uses
plain `print()`, which throws `UnicodeEncodeError` on Windows' default
cp1252 console codepage for filenames containing non-cp1252 characters
(hit on a fullwidth `｜` in a video title). This crashed the script
right after finishing video 1, before it could start video 2 — fix with
`sys.stdout.reconfigure(encoding='utf-8', errors='replace')` (or similar)
before relying on it to run unattended across several videos.

**Run 1 result (2026-08-16, 12:03-13:30, ~87min):** "1000 IQ CYPHER! C9
OXY CYPHER VALORANT RANKED GAMEPLAY" (48min clip, 86,160 sampled frames)
→ 316 engagements, avg pre-aim 12.15% of screen width (best 0.21%, worst
49.16%), 107 near-smoke / 209 clear-sightline. Output:
`engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay\`.
Only 4 of ~100 planned downloads were complete as of this session (rest
still `.part`/queued).

## Pipeline (per video)

1. Open next unrecorded full-match VOD from the channel's Videos tab, set
   quality to max available, go fullscreen, seek to 0:00.
2. Inject the ad-skip watcher (see "Ad-skip" below) immediately before
   starting playback + pressing Alt+F9 (NVIDIA ShadowPlay), so the
   watcher's zero point matches the recording's zero point.
3. Start playback, Alt+F9 to start recording, launch a detached background
   PowerShell timer sized to the video's remaining duration + ~15-20s
   buffer that sends Alt+F9 again to stop.
4. **On stop-timer completion, start the next video's recording FIRST**
   (see "Continuous recording rule" below), then separately post-process
   the finished one:
   a. Pull `window.__adEvents` from the page, save as JSON.
   b. `python trim_ads.py --input <raw.mp4> --output <clean.mp4> --ad-events <events.json>`
      (run from this repo dir; stream-copy only, see "trim_ads.py" below).
   c. Verify with ffprobe before analyzing (see "Verification" below).
   d. `python analyze_crosshair_placement.py --clip <clean.mp4> --output engagements_<video_slug>`
      (system python already has torch/ultralytics, no venv needed).
5. Log results (engagement count, avg pre-aim %) here.

## Continuous recording rule (per user)

Recording/watching must never stall waiting on a previous video's trim or
analysis — those run as detached background tasks. As soon as one video's
stop-timer fires, immediately start the next video's recording in parallel
with the previous video's post-processing.

## trim_ads.py

Pure stream-copy — no re-encode. Extracts each "keep" interval (source
minus padded ad windows) via `-ss/-to` before `-i` (fast keyframe seek,
not frame-accurate, fine given the 0.5s pad) then concats losslessly via
ffmpeg's concat demuxer. ffmpeg path is hardcoded inside the script
(winget install location).

**Do not reintroduce nvenc/libx264 re-encoding.** First version used a
`filter_complex` trim+concat through `h264_nvenc` and it silently died
partway through a 31GB/34min source: exit code 0, but the video track only
had 6009 frames (50s) while the audio track ran the full 34 minutes.
ffmpeg did not surface this as an error. Caught by checking output
`nb_frames`/duration before running analysis on it.

## Verification (always do this before analyzing a trimmed clip)

```
ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,duration -of default=noprint_wrappers=1 <clean.mp4>
```

`nb_frames / duration` should ≈ source fps, and `duration` should be close
to `(raw duration - trimmed ad time)`. If it doesn't match, something
broke — stop and flag rather than analyzing garbage.

## Ad-skip (MutationObserver — v2, current)

A `setInterval`-only watcher was unreliable: Chrome throttles page timers
hard in backgrounded tabs, so a full ad played through once despite the
watcher supposedly running. Fix: a `MutationObserver` reacts to DOM
changes directly, not a timer, so background-tab throttling (which only
targets `setTimeout`/`setInterval`/`requestAnimationFrame`) doesn't affect
it. Inject this exact snippet at the start of every video, immediately
before playback + Alt+F9:

```js
if (window.__adSkipInterval) clearInterval(window.__adSkipInterval);
if (window.__adSkipObserver) window.__adSkipObserver.disconnect();
window.__adEvents = [];
window.__adWatcherStart = Date.now();
window.__adCurrentlyShowing = false;
function tryClickSkip() {
  const selectors = ['.ytp-ad-skip-button', '.ytp-ad-skip-button-modern', '.ytp-skip-ad-button', '.ytp-ad-overlay-close-button'];
  for (const sel of selectors) { const btn = document.querySelector(sel); if (btn) btn.click(); }
}
function checkAdState() {
  const player = document.querySelector('.html5-video-player');
  const isAd = player && player.classList.contains('ad-showing');
  const nowRel = (Date.now() - window.__adWatcherStart) / 1000;
  if (isAd && !window.__adCurrentlyShowing) { window.__adCurrentlyShowing = true; window.__adEvents.push({ start: nowRel, end: null }); }
  if (!isAd && window.__adCurrentlyShowing) { window.__adCurrentlyShowing = false; const last = window.__adEvents[window.__adEvents.length - 1]; if (last && last.end === null) last.end = nowRel; }
  tryClickSkip();
}
window.__adSkipObserver = new MutationObserver(checkAdState);
window.__adSkipObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
window.__adSkipInterval = setInterval(checkAdState, 2000); // rare-case backstop only, not primary
```

`window.__adEvents` gives `{start, end}` pairs in seconds relative to
`window.__adWatcherStart`, used directly as recording-relative cut points
for `trim_ads.py` since the watcher starts at the same moment as recording.

## Smoke tagging (analyze_crosshair_placement.py)

Mask-and-tag approach (non-destructive — doesn't filter/exclude any
engagement). Per engagement frame, an HSV threshold (low saturation,
mid-value — coarse heuristic, not a trained model; will false-positive on
some gray map geometry) builds a smoke mask. Adds three columns to
`engagements.csv`: `smoke_present` (bool, local coverage >5% within 150px
of the head box), `smoke_near_target_pct`, `smoke_frame_coverage_pct`
(whole-frame). Console output also prints near-smoke vs. clear-sightline
engagement counts + avg pre-aim %. No CLI flag needed — always active.
Runs done before this was added (Demon1) don't have these columns.

## Recorded / in-progress

1. **DONE** — https://www.youtube.com/watch?v=AL_JsILMW-I — "Valorant
   Demon1 Chamber Gameplay — Radiant Ranked Full Match" (34:05)
   - Raw: `Videos\NVIDIA\Desktop\Desktop 2026.08.16 - 01.23.02.02.mp4` (31.1GB)
   - Clean: `Videos\NVIDIA\Desktop\demon1_chamber_clean.mp4` (2 ads trimmed,
     verified: 245544 frames @ 120fps = 2046.23s, audio matched)
   - Results: 133 engagements, avg pre-aim distance 11.95% of screen width
     (best 0.40%, worst 33.91%). Output: `engagements_demon1_chamber\`.
     Pre-smoke-tagging run, no smoke_* columns.

2. **PARTIAL / PAUSED** — https://www.youtube.com/watch?v=lEmtlxxE-Bo —
   "ALEKSANDAR Went Full GOD MODE on Neon! (Radiant Ranked)" (28:56)
   - Recording started 02:08:25, manually stopped early ~02:26:34 (user
     asked to pause) — raw file is a partial/incomplete recording, NOT the
     full video. When resuming: decide whether to discard and re-record
     from scratch, or keep + note the truncation.
   - Ad watcher was injected fresh at this video's start (offset=0).

## Data-quality filtering (2026-08-18/19)

Discovered the demon1_chamber engagement data was heavily contaminated. Full
manual review (see `false_positives_demon1_chamber.txt`) of the 66-frame
post-filter set found only **11/66 (17%) were real engagements** — the rest
were teammates targeted as enemies, post-death spectate (crosshair belongs
to whoever's being followed, not demon1), Tab-scoreboard UI portraits
mistaken for heads, a second streamer's replay-overlay clip embedded in the
source VOD, and demon1's own gun viewmodel.

Built two new filters in `analyze_crosshair_placement.py` to catch the two
biggest categories (spectate + scoreboard, the ones the existing
ally-color/killcam/buy-phase filters didn't touch):
- `is_scoreboard_frame()` — cheap HSV check, no OCR (green/red translucent
  table halves when holding Tab).
- `is_spectate_frame()` + `is_combat_report_frame()` — OCR via pytesseract
  (installed via winget `UB-Mannheim.TesseractOCR`), reading the
  "SPECTATORS N" corner counter and the "COMBAT REPORT" death-recap card
  respectively (two different UI states in the first few seconds after
  dying vs. ongoing spectate — needed both, one frame slipped past the
  first check alone). Both gated to only run *after* a head candidate is
  already found, since OCR is too slow to run on all ~60k sampled frames
  in a full VOD (would add ~2hrs).

Reran full pipeline on demon1_chamber_clean.mp4 (34min, 245544 frames) with
both filters: **133 raw → 55 engagements**, avg pre-aim 12.55% of screen
width (10 near-smoke / 45 clear). Not yet spot-checked against the new
output.

**Next step:** spot-check the new 55-frame `engagements_demon1_chamber/`
output for remaining contamination before trusting the 12.55% number. One
known remaining gap already spotted: `t0060.33s` in the new output still
targets teammate Clove by nameplate — not a spectate/scoreboard/killcam
state, just the existing nameplate-color detector missing it. That's the
separate "hard-negative retrain the head/body models on confirmed teammate
frames" work, still not started — filtering alone won't fully solve
teammate-as-target since nameplate/color aren't always legible.

## 2026-08-22 session: review/filter gate applied, ally-color calibration

Reverted `HEAD_MODEL_PATH` to `valorant_head_gray_v1` for good (v1-2 and
v1-3 retrains both collapsed — see git history / prior session notes for
the root-cause writeup, training-data composition mismatch between narrow
head crops and full-frame gameplay screenshots). Retraining the head
detector is abandoned; `review_engagements.py` + `filter_engagements.py`
(human click-through gate, G/1-5 keys) is now the permanent quality filter.
Raw `engagements.csv` is never used directly for analysis — only
`engagements_filtered.csv`.

Discovered `engagements_demon1_chamber/` had been silently overwritten
(down to 3 frames) by an ad-hoc validation-frame extraction step on
2026-08-20 ~7:07pm, before `validate_head_models.py` existed in its current
form (that script now writes to separate `validation_frames_*/` dirs to
avoid this). Old 3-frame folder moved aside to
`engagements_demon1_chamber_spotcheck_backup/`. Reran full analysis on
`demon1_chamber_clean.mp4` — same result as the original 08-19 run (55
raw engagements, confirms the rerun isn't corrupted), then reviewed +
filtered.

Full reviewed/filtered state as of this session:

| Video | raw | kept (good) | dropped |
|---|---|---|---|
| demon1_chamber | 55 | 19 (35%) | 36 |
| 100t-asuna-pov-raze-on-split | 81 | 17 (21%) | 64 |
| 1000-iq-cypher-c9-oxy-cypher | 316 | 78 (25%) | 238 |

Dominant false-positive category across all three: teammate-as-target
(30/36, 38/64 respectively — biggest single category by far), followed by
gun-viewmodel-as-head. Spectate/scoreboard/combat-report OCR filters are
working fine — that contamination is gone.

Tried to fix teammate-as-target via color-threshold tuning instead of
retraining: built `calibrate_ally_filter.py`, which re-detects the exact
box that got scored for every reviewed "good" and "teammate-as-target"
frame and measures the raw `ally_ring_fraction` / `ally_nameplate_px`
signal (not just the boolean pass/fail `is_ally_outline`/
`has_ally_nameplate` currently compute). Result on n=57 good / n=101
teammate-as-target frames (asuna + cypher c9 oxy; demon1_chamber skipped —
its source video predates the yt-dlp Downloads workflow, not findable by
`find_video_for_slug`): **no separation**. `nameplate_px` is 0 for 56/57
good AND 100/101 teammate frames. `ring_fraction` overlaps heavily (mean
0.010 good vs 0.017 teammate). A full threshold sweep found no cutoff that
catches meaningfully more teammates without also rejecting goods. Conclusion:
the ally fresnel/nameplate color signal just isn't legible in most real
gameplay frames — not a miscalibration, a signal-absence problem.
**Do not retry threshold tuning here** — see
`feedback_ally_color_filter_ceiling` in Claude's memory. Only unexplored
angle: OCR the teammate name text directly, not attempted yet.

Note: `calibrate_ally_filter.py`'s box-recovery (re-running head+body
detection at the same timestamp via a fresh ffmpeg frame grab) missed a
lot of rows — e.g. only 101 of cypher's ~200+ teammate-category drops were
recovered, rest logged "couldn't recover scored box" (likely ffmpeg's
`-ss` keyframe seek landing on a slightly different frame than the
original video-stream read did). Didn't chase this further since the
recovered sample already showed a clean, decisive null result.

## 2026-08-22 (cont'd): OCR nameplate also failed, ally classifier shows real signal

Corrected cypher_c9_oxy review: `t2431.37s.jpg` was mislabeled
teammate-as-target on a re-review pass, user confirmed it's a real enemy,
flipped back to good and re-ran `filter_engagements.py` (78 kept again,
matches original). Lesson: re-running `review_engagements.py` on an
already-fully-reviewed folder does NOT resume/append — it's a no-op
(`SystemExit(0)`) unless the `_review.csv` is backed up and cleared first.

Tried the one remaining unexplored angle from the note above: OCR'ing the
ally nameplate text directly (`calibrate_ocr_nameplate.py`, same 57
good / 101 teammate recovered frames from asuna + cypher). Tested 4
candidate bands (30/50/70/100px) above the recovered box. Also zero
separation — hit rate ~0.19-0.28 for both classes at every band, and the
"text" OCR found was mostly 2-3 char noise, not real names. Updated
`feedback_ally_color_filter_ceiling` memory: three independent signals
(ring color, nameplate color, nameplate OCR) have now all failed on real
footage. **Automated teammate-as-target detection via hand-picked
pixel/OCR signals is a closed question — do not retry any variant of
this.**

**New direction that actually works:** `extract_ally_classifier_dataset.py`
+ `train_ally_classifier.py` — instead of hand-picking a signal, crop the
scored box (+35% padding for context) and train a small classifier: frozen
pretrained ResNet18 backbone + a small trainable head (2-layer MLP, class-
weighted loss for the 57/101 imbalance), heavy augmentation since the
dataset is tiny. Result on the same 158 crops (127 train / 31 val,
stratified): **87% val accuracy, 100% teammate recall, 83% precision**
(confusion: tp=20 fp=4 fn=0 tn=7). This is real separation where three
hand-picked signals found none — the model is picking up on something
(pose/lighting/weapon-skin/texture) that isn't reducible to a simple color
rule. Head weights saved to `ally_classifier_head.pt` (frozen backbone not
included, re-downloads from torchvision on load).

**Caveat — do not trust this yet:** val set is only 31 images (11 good).
87% could be noise from such a small split. Not wired into
`analyze_crosshair_placement.py` or the review GUI yet.

### Next session: grow the classifier dataset before trusting/using it

1. Box-recovery ceiling: `extract_ally_classifier_dataset.py` only
   recovered 158/323 possible crops (57/95 good, 101/228 teammate) — same
   ffmpeg `-ss` keyframe-seek miss noted in the calibration writeup above.
   Worth investigating whether a frame-accurate seek (decode + count
   frames instead of `-ss` fast seek) recovers more of the missed rows
   before assuming 158 is the ceiling.
2. More source videos = more data. Check the "Not yet recorded" list
   below (recheck the channel front page first, it may be stale) and/or
   resume the "not yet recorded" backlog through the yt-dlp -> 
   `batch_analyze_downloads.py` -> `review_engagements.py` ->
   `filter_engagements.py` pipeline (one video at a time, per the
   established user preference below) to get more reviewed good/teammate
   frames to extract crops from.
3. Once the dataset is meaningfully bigger (some multiple of 158), rerun
   `train_ally_classifier.py` and see if 87%/100%/83% holds or was a
   small-sample fluke. A proper k-fold cross-validation would also be more
   trustworthy than one random 80/20 split at this data size.
4. Only after that: decide how to actually use it. Given the current
   precision (4/11 good frames wrongly flagged in val), the right first
   integration is a review-GUI pre-sort/pre-flag (surface likely-bad
   frames first to speed up human review), not blind auto-rejection.
5. Separately, still on the shelf: the actual point of the project —
   trend/outlier analysis and a coaching-feedback layer on top of the 3
   already-filtered engagement CSVs (demon1_chamber 19, asuna 17,
   cypher_c9_oxy 78 good engagements). This got interrupted by the
   teammate-FP detour above; pick whichever the user prioritizes first.

## 2026-08-22/23 session: 10 more videos through the pipeline, new yoru-clone category, ally classifier grown + retrained, orb signal found, pre-flag wired into review GUI

Ran `batch_analyze_downloads.py` -> `review_engagements.py` -> `filter_engagements.py`
end-to-end on 10 more videos from the Downloads backlog (one at a time, per the
established rule -- analysis for the next video always kicked off in background
while the current one's review GUI was open, so nothing sat idle). Results:

| Video | raw | kept (good) | dropped |
|---|---|---|---|
| 100t-asuna-pro-raze-mvp-full-match-vod | 47 | 8 | 39 |
| 100t-cryo-phoenix | 38 | 15 | 23 |
| 100t-cryo-viper | 75 | 13 | 62 |
| 13-0-envy-ion-clove | 39 | 11 | 28 |
| 28-kills-demon1-yoru-flanks | 88 | 39 | 49 |
| 30-elims-mibr-zekken-chamber | 82 | 27 | 55 |
| 30-kills-c9-oxy-jett-full-match | 80 | 42 | 38 |
| 30-kills-oxy-neon | 73 | 42 | 31 |
| 35-kills-envy-eggsterr-yoru | 106 | 24 | 82 |
| 36-rank-c9-oxy-clove | 122 | 36 | 86 |

**257 new good engagements** added across these 10 (on top of the 3 existing
filtered sets: demon1_chamber 19, asuna-pov-raze-on-split 17, cypher_c9_oxy 78).
Full list of every reviewed/filtered folder now: 13 total (see
`engagements_*/engagements_filtered.csv` per slug above plus the original 3).

**User stopped the auto-chain after the 10th video** ("stop analyzing new
clips now") -- do not assume auto-chain-forever is the default next session,
confirm with user first. The 10th video's analysis was allowed to finish
(already in flight) and was reviewed/filtered before stopping.

**Downloads backlog:** 100 videos downloaded total (2026-08-16 batch via
yt-dlp). 12 processed through the Downloads-pipeline this way so far
(the 10 above + asuna-pov-raze-on-split + 1000-iq-cypher from earlier
sessions; demon1_chamber was ShadowPlay-recorded separately, not from this
backlog). **~88 videos still unprocessed** in `C:\Users\alexh\Downloads` --
just keep re-running `batch_analyze_downloads.py` per video.

**New false-positive category added:** `review_engagements.py` key **6 =
yoru-clone-as-head** (Yoru's decoy ability spawns a body-shaped NPC the head
detector flags as a real player). Added because demon1's Yoru-flank video hit
7/49 drops in this category on first pass -- had to kill+relaunch the GUI
mid-review to pick up the new key, then backed up and fully restarted that
one folder's review from scratch so every clone got the dedicated label
instead of being lumped into "other-bad" (backup at
`engagements_28-kills-insane-yoru-flanks-by-demon1-valorant-ranked-gameplay_review.csv.bak`).
On the full re-review, teammate-as-target (40) still dominated over
yoru-clone (7) for that video -- not the biggest FP category overall, but
real and now trackable per-video going forward.

**yt-dlp auto-download attempt failed, abandoned for now.** Tried
`--download-archive` + `--break-on-existing` to auto-pull new channel
uploads; all 54 pre-cutoff videos failed with YouTube's "sign in to confirm
you're not a bot" bot-check (0 new videos actually landed). Fix needs
`--cookies-from-browser chrome` (requires closing Chrome first, Windows
locks the cookie DB while it's running) -- user chose to work the existing
88-video backlog instead rather than fight this tonight. Archive file at
`C:\Users\alexh\Downloads\yt-dlp-archive.txt` (100 IDs marked done) is still
there if resuming the download angle later.

**New teammate-detection signal found: a small white/light marker above
ally heads.** User's insight, distinct from the three previously-failed
signals (ring color, nameplate color, nameplate OCR -- see
`feedback_ally_color_filter_ceiling` memory, still valid, this is a 4th
independent signal not covered by that ceiling). Built
`calibrate_orb_filter.py` (band directly above the recovered head box,
white-pixel HSV fraction). Real, non-trivial separation found and confirmed
at scale across 6 reviewed folders (n=81 good / n=152 teammate after
box-recovery, same ffmpeg `-ss` seek-miss limitation as always --  only
~233/494 candidate rows recoverable): T=0.0005 catches 80% of teammates at
16% good-frame cost; T=0.01 catches ~66% at 12% cost. Real but noisy (some
real enemies score 0.4-1.0, some teammates score 0.0 -- occlusion/distance/
HUD overlap). **Superseded in practice by the ally_classifier ML approach
below**, which is more accurate -- orb signal not wired into anything,
kept as a script in case it's useful as an extra feature later.

**ally_classifier retrained on a much bigger dataset -- 94.8% val accuracy,
up from 87%.** Ran `extract_ally_classifier_dataset.py` across all 10
reviewed folders above plus the original 3 -- dataset grew from 158 crops
(57 good/101 teammate) to **390 crops (181 good/209 teammate)**. Retrained
with `train_ally_classifier.py` (same architecture: frozen ResNet18 backbone
+ 2-layer MLP head, class-weighted loss, 30 epochs, 80/20 stratified split --
val set now n=77, much more trustworthy than the old n=31). Best epoch:
**94.8% val accuracy**, confusion tp=35 fp=2 fn=6 tn=34 (~85-100% teammate
recall / ~91-95% precision depending on epoch). Head weights overwritten at
`ally_classifier_head.pt`. This is a real result, not small-sample noise --
first signal (of 4 total attempts across two sessions) that's actually
strong enough to build on.

**Wired in as a pre-flag (not auto-filter) in review_engagements.py.**
User explicitly chose pre-flag over auto-tag (auto-tag would write
predictions into `engagements.csv` and let high-confidence predictions skip
human review entirely -- rejected as too risky at ~91-95% precision, that's
roughly 1-in-12-20 real enemies silently lost if trusted blindly). Built:
- `predict_teammate_prob.py <engagements_folder> [...]` -- runs the
  classifier over every raw frame in a folder (box-recovery via the same
  ffmpeg-reextract + head/body redetection as the calibration scripts),
  writes `<folder>_predictions.csv` (filename, teammate_prob). Doesn't touch
  engagements.csv or drop anything.
- `review_engagements.py` -- if a `<folder>_predictions.csv` exists
  alongside the engagements folder, unreviewed frames are sorted
  highest-teammate-probability first, and the score is shown in the status
  bar (red text if >=0.5). Every frame still gets manually reviewed and
  labeled by hand; this only changes review order/highlighting.

**Not yet tested end-to-end** -- built and syntax-checked
(`python -c "import ast; ast.parse(...)"` on both files) but never actually
run against a real engagements folder. **Next session: first thing to do is
run `predict_teammate_prob.py` on one of the 88 backlog videos after its
next `batch_analyze_downloads.py` pass, then open `review_engagements.py`
and confirm the sort/highlight actually works and the predicted scores look
sane against what gets manually labeled** before trusting it further.

## 2026-08-23 session: pre-flag classifier sanity-checked, 14th video reviewed/filtered, new FP categories added

Resumed the backlog with `predict_teammate_prob.py` + `review_engagements.py` on
**39-kills-dream-team-c9-oxy-xeppaa-ion-chamber**: 82 raw engagements, 48/82
box-recovered and scored (34 skipped/no-box, same ffmpeg `-ss` seek-miss as
always). Score distribution sane: 7 frames >0.5 (top score 0.95), clean tail
down to ~0.001 at the bottom. Sort-highest-first and red status-bar highlight
confirmed working against manual review. **Pre-flag integration verified
end-to-end for the first time** -- not yet auto-tagging anything, still
pre-sort/highlight only per the earlier precision caveat.

Reviewed and filtered: **82 raw -> 46 kept, 36 dropped**. Teammate-as-target
still dominant (31/36). Added two new `review_engagements.py` bad-categories
per user request: key **7 = utility-as-head** (ability effect mistaken for a
head) and key **8 = map-geometry-as-head** (coarse HSV/shape false-positive on
map geometry, distinct from the existing gray/smoke/scoreboard filters) --
both pure manual-judgment labels, no detection logic, same as all other
category keys. Not retroactively applied to earlier reviews; only affects
future review sessions. GUI needs a kill+relaunch to pick up new keys.

14th folder now reviewed/filtered (full list: demon1_chamber,
asuna-pov-raze-on-split, cypher_c9_oxy, + the 10 from 08-22/23, + this one).
~87 videos still unprocessed in Downloads backlog.

## 2026-08-23 (cont'd): box coords now saved, retrain wired into standard per-video flow

`analyze_crosshair_placement.py` now writes the scored box (`box_x1/y1/x2/y2`)
into `engagements.csv` for every engagement -- the same body-outline box
`find_scored_box()` used to have to re-derive by re-extracting the frame and
rerunning head+body detection. `predict_teammate_prob.py` and
`extract_ally_classifier_dataset.py` (via new `load_boxes_from_engagements_csv()`
in `calibrate_ally_filter.py`) now read the box straight from the CSV when
present, falling back to the old re-detect path only for `engagements.csv`
files written before this change. **Videos analyzed from here on should hit
~100% box-recovery instead of the ~35-65% seen so far** -- not yet confirmed
against a real post-fix video (none reviewed yet as of this note).

Retrained on all 15 valid reviewed folders (576 crops, up from 390) as a
sanity check: **93.9% val accuracy** (n=114 val) -- flat vs the prior 94.8%
(n=77 val), not a real climb, still using the old recovery path since none of
these 15 folders were analyzed after the box-coord fix landed. Real test of
whether the fix helps comes once a video analyzed after this point gets
reviewed and folded in.

**New standing workflow (per user request): after every `filter_engagements.py`
run, immediately re-run `extract_ally_classifier_dataset.py` (pass every valid
reviewed folder -- it's idempotent, skips already-extracted crops) then
`train_ally_classifier.py` to retrain on the grown dataset.** Do this
automatically going forward, no need to ask each time. Exclude
`engagements_demon1_chamber_spotcheck_backup` from the folder list -- corrupted
3-frame leftover, not real data (see 2026-08-22 note above).

Also added two new `review_engagements.py` bad-categories per user request:
key 7 = utility-as-head, key 8 = map-geometry-as-head (see above).

## 2026-08-23/24 session: 5 more videos reviewed/filtered, box-coord fix confirmed, classifier plateauing

Backlog loop ran unattended (per user's "keep analyzing them even after this one
is done") through: 40-rank-world-champion-s0m-s-raze, 42-rank-mvp-c9-oxy-neon,
ace-derrek-goes-perfect-on-neon, ace-florescent-crazy-waylay-on-ascent,
aim-machine-florescent-jett, aimer-aleksandar-na-cypher-map-control,
aleksandar-went-full-god-mode-on-neon. User stopped the loop after the last of
these finished (killed mid-analysis on the next one, aspas-aim-is-art -- partial
frames only, no engagements.csv, safe to leave/rerun later).

All 5 fully reviewed+filtered this session:

| Video | raw | kept | dropped |
|---|---|---|---|
| 40-rank-world-champion-s0m-s-raze | 65 | 27 | 38 |
| 42-rank-mvp-c9-oxy-neon | 64 | 39 | 25 |
| ace-derrek-goes-perfect-on-neon | 77 | 37 | 40 |
| ace-florescent-crazy-waylay-on-ascent | 83 | 35 | 48 |
| aim-machine-florescent-jett | 61 | 34 | 27 |
| aimer-aleksandar-na-cypher-map-control | 73 | 7 | 66 |
| aleksandar-went-full-god-mode-on-neon | 60 | 22 | 38 |

**aimer-aleksandar-na-cypher-map-control is an outlier -- 92% of its drops
(61/66) were teammate-as-target**, way above the usual ~40-50%. Root cause:
the video itself is a map-control/positioning tutorial, camera spends most of
its time near teammates rather than in real enemy engagements -- not a
detector problem, just very little real content to find in this particular
source video.

**Box-coord fix (from earlier this session) confirmed working on real data:**
aim-machine-florescent-jett, aimer-aleksandar, and aleksandar-neon (all
analyzed after the fix landed) hit **100% prediction coverage** (61/61, 73/73,
60/60 scored, 0 skipped) vs. 44%/36% for the two `ace-*` videos analyzed
before the fix. Confirms the box_x1/y1/x2/y2 columns are working as intended
-- going forward every newly-analyzed video should get full pre-flag coverage.

**Classifier retrained twice more this session (per new standing workflow),
plateauing around 93-94%:**
- 576 crops (293 good/283 teammate) -> 93.9% val acc (n=114)
- 814 crops (400 good/414 teammate) -> 93.8% val acc (n=162)

Essentially flat across the last 3 retrains (94.8% -> 93.9% -> 93.8%) despite
dataset more than doubling since the 94.8% run. Reasonable read: the model
has converged to whatever this architecture (frozen ResNet18 + small MLP head)
can extract from these crops, and more of the *same kind* of data isn't moving
it further. Confirms a real, useful, plateaued signal (~93% both ways) rather
than a fluke -- but don't expect gains from just running more videos through
the same pipeline. If pushing past ~94% matters later, would need a different
lever (unfreezing more of the backbone, a stronger augmentation set, or the
box-coord fix's higher-quality crops on entirely new data once enough of it
accumulates -- most of this batch's new crops still went through the old
recovery path except where box coords were already saved).

**21 reviewed/filtered folders total now** (excluding the corrupted
`engagements_demon1_chamber_spotcheck_backup`).

### Next session starting point (updated 2026-08-24)

1. **Standing instruction, no need to confirm: keep auto-chaining
   `batch_analyze_downloads.py` through the backlog continuously at session
   start**, one video after another, not stopping between videos (loop it --
   see the `while true` pattern used 2026-08-23, or just re-invoke the script
   per finished video). Only stop if the user explicitly says to. This
   supersedes the older "confirm before auto-chaining" note above.
2. Analysis and review/filter are still separate gates: the loop only runs
   `batch_analyze_downloads.py` (raw extraction). Each finished video still
   needs `predict_teammate_prob.py` -> `review_engagements.py` ->
   `filter_engagements.py` by hand before its data is usable -- keep
   surfacing "ready to review" folders as videos finish, per the review gate.
3. After every `filter_engagements.py` run, re-run
   `extract_ally_classifier_dataset.py` (pass every valid reviewed folder,
   excluding `engagements_demon1_chamber_spotcheck_backup`) then
   `train_ally_classifier.py` -- standing workflow from 2026-08-23, do this
   automatically, no need to ask.
4. ~85 videos left in the Downloads backlog as of 2026-08-24 (21 folders
   reviewed/filtered so far).
5. Classifier plateaued at ~93-94% val accuracy across the last 3 retrains
   despite dataset more than doubling -- don't expect gains from just running
   more videos through the same pipeline (see 2026-08-23/24 note above for
   what might actually move it further).
5. Still on the shelf, further deprioritized this session: the actual point
   of the project -- trend/outlier analysis and coaching-feedback layer on
   top of the now-13 filtered engagement CSVs. Growing at ~257
   engagements/session lately; probably worth picking this up soon rather
   than continuing to only grow the raw data pile.

## 2026-08-24 (cont'd): head detector hard-negative retrain attempted again (v1-4), collapsed a 3rd time — conclusively dead end

User reported gun-viewmodel-as-head scoring high teammate_prob from the ally
classifier pre-flag. Traced root cause: `extract_ally_classifier_dataset.py`
only pulls `label=="good"` or `category=="teammate-as-target"` rows, so
gun-viewmodel crops never enter classifier training at all — the classifier
just guesses on them. Two fix options were presented: (1) a cheap heuristic
filter in `analyze_crosshair_placement.py` targeting gun-viewmodel position/
shape directly (never touches the head detector), or (2) retry hard-negative
retraining of the head detector itself, since a memory-recorded root cause for
the earlier v1-2/v1-3 collapses ("tight head-crop positives vs full-frame
negative composition mismatch") looked worth re-checking. User chose option 2.

Verified the composition-mismatch theory first: inspected
`dataset_head_gray/train/images` directly — all 3029 images (positive and
negative alike) are already full 1920x1080/2560x1440 frames, no crop
mismatch. So the stated root cause for v1-2/v1-3 was wrong (likely a bad/
hallucinated summary from an earlier auto-observation, not verified fact).

Ran `extract_hard_negatives_from_review.py` across all 26 reviewed
Downloads-backlog folders (demon1_chamber skipped, predates the Downloads
workflow — no matching source video). Hit the known `UnicodeEncodeError`
print bug on 11 of them — but this time it crashed *before* any frames were
written (not after, as previously assumed) for those 11, so they initially
got **zero** hard negatives. Fixed the bug for real this time
(`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` added to
`extract_hard_negatives_from_review.py`) and reran all 11 successfully.
Dataset grew from ~35 hard negatives (v1-2/v1-3 era, essentially 1 video) to
**1487 across 26 videos** (3475 total training images, 1988 positive/1487
negative).

Renamed the fine-tune run to `valorant_head_gray_v1-4` (edited
`resume_train_head_gray.py`, was hardcoded to overwrite `v1-3`) and ran the
same low-LR resume fine-tune (15 epochs, lr0=0.0001, from v1 weights).
Training-time metrics looked healthy — final epoch precision 0.898, recall
0.82, mAP50 0.883 — no sign of collapse from the training log alone.

**Validated against v1 baseline with `validate_head_models.py` on an
independent frame set (ace-derrek-goes-perfect-on-neon, 57 frames, never
part of training) — v1-4 collapsed exactly like v1-3: 0/20 recall on "good",
0 detections across every bad category too (gun-viewmodel, teammate,
other-bad all show 0/N "still fires").** Complete reject-everything failure,
same as the prior two attempts, despite growing the negative set ~40x and
diversifying it across 26 videos instead of 1. Training-time mAP looked fine
because YOLO's internal val split is drawn from the same negative-heavy
dataset — it did not catch this. **HEAD_MODEL_PATH was NOT changed, still
`valorant_head_gray_v1`.**

**Conclusion (3rd confirmed collapse): hard-negative resume-retraining of
this head detector is a closed question at any dataset size — do not retry
this method again.** See `project_head_detector_retrain_dead_end` in
Claude's memory for the full writeup. The composition-mismatch theory that
motivated trying again is disproven; the real cause of the collapse is still
unknown, but empirically robust across 3 attempts. Any future attempt at
suppressing gun-viewmodel-as-head (or other) false positives should use the
cheap heuristic-filter route instead (option 1, not yet built), or extend the
ally-classifier-style crop+small-model approach to a 3rd class — not touch
the head detector's own training again. Always validate any future head-
detector change against `validate_head_models.py` on independently-extracted
frames before trusting training-time metrics.

## 2026-08-24 (cont'd): gun-viewmodel-as-head heuristic filter added (option 1, after option 2's 3rd collapse)

With head-detector retraining conclusively dead (see above), built the
fallback heuristic filter instead: `is_gun_viewmodel_box()` in
`analyze_crosshair_placement.py`, wired into the same per-candidate skip
gate as `is_ally_outline`/`has_ally_nameplate` (runs on the outline/body box
before a candidate becomes an engagement).

Calibrated by pooling `box_x1..y2` (from `engagements.csv`, post box-coord-
fix videos only) against `_review.csv` labels across all reviewed folders:
250 "good" boxes vs 56 "gun-viewmodel-as-head" boxes. Real enemy boxes are
narrow (median 2.3% of frame width) and centered near the crosshair (median
x-center ~50%, since that's where the player was aiming when the enemy
appeared). Gun-viewmodel boxes run much wider (median 6.6%) and sit
right-of-center (median x-center ~63%, weapon rendered on-screen right).
Combined rule -- reject if `width > 5% of frame width AND x-center > 55% of
frame width` -- catches **73% of gun-viewmodel false positives at ~3% cost
to real good engagements** (swept several single- and multi-feature
thresholds; this combo had the best catch/cost tradeoff found).

Not perfect by design (unlike the coarse near-100%-confidence scoreboard/
killcam/spectate filters) -- `gun-viewmodel-as-head` remains a manual review
category for what slips through (mainly ADS/scoped poses where the gun
model rides toward screen-center). Applies going forward to newly-analyzed
videos only, not retroactive to the 27 already-processed folders.

## 2026-08-25: match-end (victory/defeat) screen filter added

User spotted the post-match "VICTORY/DEFEAT" summary screen (huge stylized
text + MVP stat card) getting scored as a 95%+ teammate false positive --
found via `engagements_mibr-aspas-pro-waylay-on-lotus-vod-ranked/t1826.30s.jpg`.
A pure color-uniformity heuristic (dominant hue covering most of the frame)
was tried first but rejected -- a real gameplay frame with a large single-
color wall (Lotus's red temple interior) scored just as "flat" as the UI
screen, no clean cutoff. Switched to OCR: "KDA" on the MVP card is a clean,
locale-independent signal (this VOD's Chinese client renders "VICTORY" as
"胜利", but "KDA" stays English) -- zero false positives tested against real
gameplay, spectate, and Tab-scoreboard frames. Added `is_match_end_frame()`
to `analyze_crosshair_placement.py`, wired into the same OCR-tier gate as
`is_spectate_frame`/`is_combat_report_frame` (runs only after a head
candidate is found).

**Not fixed by this filter**: the adjacent agent-select screen
(`t1825.17s.jpg` in the same folder, one second before the victory frame --
solid flat-teal background, single character model, no KDA card) still
false-positives the same way. Separate signal needed if it turns out to be
a meaningful contamination source -- not yet quantified how often it occurs
across the backlog.

## 2026-08-26: gun-viewmodel filter demoted to prediction-only

User doesn't trust the gun-viewmodel heuristic's real-world accuracy yet
(only backtested against the 250/56 calibration sample, never validated at
scale like the ally classifier was). Per request, demoted from a hard reject
to a recorded prediction: removed the `continue` in the per-candidate loop,
added `gun_viewmodel_pred` (bool) to `engagements.csv` instead. Nothing gets
dropped based on it anymore -- every candidate that used to get silently
rejected now becomes a normal engagement again, with the prediction attached
so it can be spot-checked against real review labels later. Revisit turning
it back into a reject (or wiring it into the pre-flag sort like the ally
classifier) once there's enough reviewed data to actually measure its
precision/recall, same bar the ally classifier had to clear first.

## 2026-08-26: session wrap-up (supersedes the 2026-08-24 "Next session starting point" list above)

Long multi-day session (2026-08-24 through 2026-08-26) ran the Downloads
backlog down to **zero unreviewed folders** -- every downloaded video that
completed analysis has been reviewed and filtered. **77 reviewed/filtered
folders total** now (up from 21 at the start of this stretch).

**Ally classifier progression this session:** 93.8% (start) -> 94.6% ->
96.6% (peak, n=537 val) -> 95.9% (final, n=910 val, much larger/more
trustworthy val set). Holding steady in the mid-90s with real dataset
growth (922 -> 2251+ crops) -- this is the real, stable number now, not a
small-sample fluke.

**Head-detector hard-negative retraining is conclusively dead** (3rd
collapse, v1-4) -- see the 2026-08-24 entry above and
`project_head_detector_retrain_dead_end` in Claude's memory. Do not retry.

**Two new detection filters landed in `analyze_crosshair_placement.py`:**
- `is_match_end_frame()` -- OCR-based ("KDA" keyword, locale-independent),
  live hard reject. Catches the post-match victory/defeat summary screen
  that was scoring 95%+ teammate false positives. Does NOT catch the
  adjacent agent-select screen (same flat-background look, no KDA card) --
  still an open gap if it turns out to matter at scale.
- `is_gun_viewmodel_box()` -- backtested at ~73% catch / ~3% cost, but
  **demoted to prediction-only per user request (2026-08-26)** since real-
  world accuracy isn't proven yet. Writes `gun_viewmodel_pred` (bool) into
  `engagements.csv` instead of rejecting -- nothing is dropped based on it.
  Revisit turning it back into a reject (or into the pre-flag sort like the
  ally classifier) once enough reviewed data exists to actually measure its
  precision/recall against ground truth.

**Auto-chain backlog loop stopped per explicit user request** -- do not
resume unattended `batch_analyze_downloads.py` looping without asking
first; this reverses the 2026-08-24 "auto-chain by default" standing
instruction above.

**Known process gotcha from this session:** the review GUI (`tkinter`,
`review_engagements.py`) occasionally completes near-instantly with
plausible-looking but unreviewed data when launched via
`nohup python ... &` -- happened at least twice (kay-o run 1, an early
kay-o-suppression run). Root cause not fully pinned down (the code has no
auto-label path -- every row requires a real button/key event -- but the
window has, more than once, not actually been visible/interactive to the
user despite the process completing "normally"). **When re-opening a
review GUI, don't assume a fast completion means it was skipped -- but if
the user says they never saw a window, immediately back up the resulting
`_review.csv` as `.bak_unconfirmed`/`.bak_skipped` and relaunch fresh
rather than trusting it.** Both suspect runs from this session were backed
up, not deleted.

**Downloads backlog remaining:** ~104 videos total in
`C:\Users\alexh\Downloads`, most now processed (`engagements_<slug>/`
exists) -- did not recompute the exact unprocessed count this session, but
it should be small. Resuming: just re-run `batch_analyze_downloads.py`
per-video (or ask the user before looping it unattended again, per the
auto-chain-stopped note above).

## 2026-08-26 (cont'd): three pre-flag classifiers now live (ally retrained, gunmodel + enemy built new)

Session resumed same-day. User: keep the gunmodel filter as a trained
pre-flag classifier (same pattern as ally_classifier) instead of the
backtested-only heuristic, retrain ally classifier on the fully-grown
dataset if not already done, and separately build a general "is this
actually an enemy" classifier (good vs every bad category combined) since
the head/body YOLO detector that generates candidates in the first place is
clearly noisy (2148 good vs 3635 bad across all reviews). Auto-backlog
looping was also resumed mid-session, then explicitly stopped again later
in the same session ("stop backlog") -- see cleanup note below.

**All three classifiers use the identical architecture** (frozen ResNet18,
`layer4` unfrozen at a lower LR than the head, class-weighted
cross-entropy, heavy augmentation, 30 epochs, 80/20 stratified split) --
only the dataset differs:

| Classifier | Dataset (good/other) | Val acc | Val precision | Val recall | Weights file |
|---|---|---|---|---|---|
| `ally_classifier` | 1927 good / 2629 teammate (4556 total, n=910 val) | **96.3%** | 0.959 | 0.977 (teammate) | `ally_classifier_head.pt` |
| `gunmodel_classifier` | 1927 good / 179 gunmodel (2106 total, n=420 val) | **98.6%** | 0.968 | 0.857 (gunmodel) | `gunmodel_classifier_head.pt` |
| `enemy_classifier` | 1927 good / 2966 bad-any-category (4893 total, n=978 val) | **95.1%** | 0.952 | 0.968 (bad) | `enemy_classifier_head.pt` |

Ally classifier retrain was a true no-op extraction-wise (4556/4556 crops
already existed, idempotent skip) -- climbed 95.9% -> 96.3% purely from the
architecture/hyperparameters already in place, re-run as a sanity check per
the standing workflow.

**Gunmodel and enemy classifiers are brand new this session** -- new
scripts, mirroring the ally ones exactly:
- `extract_gunmodel_classifier_dataset.py` / `train_gunmodel_classifier.py`
  / `predict_gunmodel_prob.py` -- good vs `gun-viewmodel-as-head` only.
- `extract_enemy_classifier_dataset.py` / `train_enemy_classifier.py` /
  `predict_enemy_prob.py` -- good vs `label=="bad"` (any category:
  teammate, gunmodel, scoreboard, spectate, yoru-clone, utility,
  map-geometry, other-bad, all pooled). This is the general "would a human
  reviewer keep this at all" model, not tied to one FP category.

**Caveat on gunmodel_classifier:** val set has only 35 positive (gunmodel)
examples out of 420 -- the 98.6%/96.8%/85.7% numbers are from a much
thinner slice than the other two and should be treated as promising, not
proven, until the dataset grows past its current 179 positives (it'll grow
naturally as more videos get reviewed with the gun-viewmodel-as-head
category, same as every other classifier here).

**`review_engagements.py` now loads and displays/sorts by all three**
(`_predictions.csv`/teammate_prob, `_gunmodel_predictions.csv`/gunmodel_prob,
`_enemy_predictions.csv`/bad_prob) -- sort key is `max()` of whichever are
present, status bar shows every score that exists, red highlight if any
score >=0.5. Still pure pre-flag/pre-sort, nothing auto-rejected by any of
the three. **Standing workflow updated:** after every `filter_engagements.py`
run, re-run all three `extract_*_classifier_dataset.py` scripts then all
three `train_*_classifier.py` scripts (not just the ally ones) -- do this
automatically going forward, same "no need to ask" rule as before. For a
freshly-analyzed video ready to review, also run all three `predict_*_prob.py`
scripts before opening `review_engagements.py`, not just
`predict_teammate_prob.py`.

**Auto-backlog loop resumed then stopped again, same session -- do not
resume unattended without asking, this reaffirms the 2026-08-26 wrap-up note
above.** A driver script (`_auto_backlog_loop.sh`, now deleted) called
`batch_analyze_downloads.py` in a loop (it only does one video per
invocation by design) and fired `predict_teammate_prob.py` +
`predict_gunmodel_prob.py` in the background per finished video without
waiting on review, to preserve the continuity rule from
[[feedback_automation_pipeline_continuity]]. It processed effectively 0 new
videos this stretch before being stopped -- the one video it attempted
("Rank #1 APAC is Just INSANE -Primmie", `[DkCcsrFuAfc]`) **failed twice
with exit code 1, not yet root-caused.** When resuming: investigate that
failure first (rerun `analyze_crosshair_placement.py` directly on it, not
through the batch wrapper, to see the real traceback) before assuming the
loop itself is fine.

**Bug found in `_auto_backlog_loop.sh`'s own logic (relevant if rewriting a
similar loop later):** it detected "a new video was processed" by comparing
`ls -d engagements_*/ | wc -l` before/after each `batch_analyze_downloads.py`
call. This is unreliable -- `analyze_crosshair_placement.py` creates its
output directory up front (before or regardless of whether the run
ultimately succeeds), so a failed run can still register as "new folder
appeared" and the loop would wrongly treat it as success and fire the
predict scripts on an empty folder (confirmed: this happened once, on the
Rank #1 APAC failure -- harmless, predict scripts just wrote empty 0-row
CSVs, but the empty `engagements_rank-1-apac-*/` folder and its empty
`*_predictions.csv`/`*_gunmodel_predictions.csv` were cleaned up manually
after the fact). A correct check should look for the specific folder's
`engagements.csv` file existing, or grep `batch_analyze_log.txt` for a
`done:` line, not a raw folder count.

**Downloads backlog, recounted this session: 24 real videos still
unprocessed** (of 100 total candidates found via the youtube-id matching
logic; a 25th, "Valorant Demon1 Chamber Gameplay", shows as unprocessed by
this slug-based check but is a false flag -- that video was
ShadowPlay-recorded early on as `engagements_demon1_chamber`, a different
folder-naming scheme, and is genuinely already done). Resuming: same as
before, re-run `batch_analyze_downloads.py` per video (or ask before
looping it unattended again).

## 2026-08-29: analysis/coaching layer built, APAC failure resolved, backlog driver relaunched

Three things this session, all at user request ("do all of them"):

**1. Rank #1 APAC failure -- REAL root cause: a latent bug in
`analyze_crosshair_placement.py`, broken since 2026-08-26.** (An earlier
note this session guessed "transient incomplete download" -- WRONG,
retracted.) When `gun_viewmodel_pred` was added to the engagement dict on
2026-08-26, it was NOT added to the `csv.DictWriter(fieldnames=[...])` list
at what is now line ~584. So every run that finds >=1 engagement crashes at
`writer.writerows(engagements)` with `ValueError: dict contains fields not
in fieldnames: 'gun_viewmodel_pred'` -- AFTER 30-50min of GPU work, having
already written the annotated JPGs and a header-only `engagements.csv`.
Syntax checks (obs 718, Aug 26) passed because the bug is runtime-only.
**Consequence: the pipeline has produced zero usable new videos since
2026-08-26.** The 2026-08-26 wrap-up's "backlog down to zero" refers only to
folders analyzed on/before Aug 24-26 morning; the 24 "unprocessed" backlog
videos never actually got through.
**Fixed 2026-08-29:** added `"gun_viewmodel_pred"` to the fieldnames list
(after the smoke columns, before `box_x1`). Syntax OK. NOT yet run
end-to-end -- any real run is 30-50min. The 4 crash-junk folders from this
session's driver (`rank-1-apac...`, `rank-30-mvp-c9-oxy-jett...`,
`road-to-top-1-oxy...`, `s0m-literally-broken...` -- all header-only
engagements.csv) were deleted.

**2. Analysis/coaching layer finally built** -- `analyze_pro_baseline.py`
(repo root). Pools every `engagements_*/engagements_filtered.csv` (76 valid
folders, excludes `*_spotcheck_backup`), parses player/agent/map/role from
each folder slug, and writes to `analysis_output/`:
- `pro_baseline_report.md` -- headline numbers, by-agent / by-map / by-player
  / by-role tables, best/worst VODs, 25 worst individual reveals, 166
  per-video outliers.
- `preaim_distribution_all.png`, `by_agent.png`, `by_map.png`, `by_player.png`
- `engagements_pooled.csv` -- all 2,145 engagements, one row, with parsed metadata
- `baseline.html` -- standalone visual report (Chakra Petch / IBM Plex,
  inline-SVG histogram, dark+light). Built but NOT published -- the Artifact
  publish was blocked by the Claude Code auto-mode classifier. Publish
  manually if wanted; it's a self-contained file.

**Key baseline numbers (2,145 filtered engagements, 76 pro VODs):**
- Median crosshair-to-head distance at reveal: **3.10%** of screen width
  (mean 6.22%, p90 16.1%, p99 38.9%).
- **64.5%** of reveals are pre-aimed (<=5% width); 36% within 2%; 11.8% past 15%.
- Smoke barely matters: clear-sightline median 2.98% vs near-smoke 3.15%
  (n=1340 / 805). The "smokes wreck pre-aim" intuition does not hold.
- Duelist vs non-duelist median 3.14% vs 2.93% -- role predicts ~nothing.
- Map matters: Split 2.42% / Sunset 2.20% (tight) vs Ascent 4.77% / Breeze
  3.96% (open). Only 14/76 VODs name a map in the title though -- small n.
- Tightest players (>=20 eng): primmie 1.75, cryo 1.85, ion 1.87, aspas 2.32.
  Loosest: zekken 7.26 (n=27, chamber -- likely playstyle + small sample).
- Tightest agents: reyna 2.18, viper 2.24, clove 2.53. Loosest: sova 3.82,
  chamber 3.73, waylay 3.66.

**Caveat:** distance is 2D screen distance, not angular error -- a distant
and a close enemy at the same pixel gap score identically. Fine as a
relative baseline; note it if used in an essay. No learner-own-match data is
in the filtered set right now (earlier Deathmatch runs in PLAN.md aren't in
`engagements_*/`) -- this baseline is pro-only until the learner's own
recorded matches are run through the same pipeline and compared.

**3. Backlog driver relaunched, then STOPPED by user after it exposed bug
#1.** Ran videos 1-5 of 24; every one crashed on the `gun_viewmodel_pred`
fieldnames bug after 30-50min each (~3hrs wasted GPU time). 0 videos
produced. Driver logic itself is fine (corrected success check correctly
flagged all 5 FAILED). Driver saved into the repo as **`run_backlog.py`**
(was in scratchpad, would not have survived the session).

**Fix verified at the failure point 2026-08-29** (not yet a full run): a
standalone test builds the exact engagement dict the code appends and writes
it through the patched `fieldnames` list -- no missing fields, row writes
OK. A real end-to-end run is still the proper confirmation.

## 2026-08-30: backlog resumed with crash-resilient watchdog

Relaunched `run_backlog.py` (fieldnames fix now in place, `analyze_crosshair_placement.py`
line ~586 -- `gun_viewmodel_pred` added to DictWriter fieldnames). Video 1/24
(Rank #1 APAC -- Primmie) analyzing as of 01:39 EDT; this is the first real
end-to-end test of the fix. All 24 backlog videos queued.

Added `backlog_watchdog.py` (repo root) for unstable-wifi / crash resilience:
- Every 60s: if backlog videos still lack a complete `engagements.csv` AND
  neither `run_backlog.py` nor `analyze_crosshair_placement.py` is alive,
  relaunches `run_backlog.py` detached. Idles while healthy. Exits when all done.
- Lockfile `backlog_watchdog.lock` (pid); takes over a stale lock if the pid is dead.
- Relaunches the driver with a **console** python (pythonw has no stdout -> child
  print() crashes). `run_backlog.py` + watchdog both guard `sys.stdout.reconfigure`
  for pythonw.
- Progress granularity: per **video** (`engagements_<slug>/engagements.csv` >1 row).
  Mid-video crash loses only that video (~30-50min), restarts from 0.
- Reboot persistence: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\valorant_backlog_watchdog.bat`
  launches the watchdog at every logon (no admin needed -- Task Scheduler
  registration was access-denied). Self-exits if done or lock held.
- Manual restart if needed: `nohup python backlog_watchdog.py > /dev/null 2>&1 &`
  from the repo dir.

wifi dropping / Claude session dying does NOT affect the run -- it's nohup-detached
and fully local (GPU). Only a real machine reboot needs the startup .bat.

### 2026-08-30 backlog run: 22 of 24 analyzed, then user stopped it

The fieldnames fix (`gun_viewmodel_pred`) is CONFIRMED working end-to-end --
22 videos analyzed cleanly overnight (01:52 -> 15:49 EDT), 0 failures, raw
engagement counts 36-185 per video. The console-flash bug (watchdog's `wmic`
call every 60s stealing game focus) was fixed mid-run -- all subprocess calls
in `backlog_watchdog.py` + `run_backlog.py` now use `CREATE_NO_WINDOW`.

**User stopped all 3 processes (watchdog / driver / analysis) at ~15:50 on
2026-08-30.** Nothing is running now. Lockfile removed.

**State of the 24-video backlog:**
- **22 analyzed** -- `engagements_<slug>/` with `engagements.csv` + all 3
  `*_predictions.csv`. NONE reviewed yet.
- **Video 23** `yoru-but-with-oxy-s-aim-terrifying-ranked-gameplay` -- killed
  mid-analysis, NO `engagements.csv`, `run_backlog.py` will re-run it clean.
- **Video 24** `zekken-s-clove-is-an-unkillable-duelist-controller` -- never
  started.

**Startup `.bat` is STILL ARMED** (`%APPDATA%\...\Startup\valorant_backlog_watchdog.bat`)
-- a reboot will auto-resume videos 23+24. User was asked whether to disable
it; left armed as of this save. To disable: delete that .bat.

### Next session -- TASKS

1. **Resume the last 2 videos** (23, 24): `python run_backlog.py` (repo root).
   ~1.5hr. Or just reboot (startup .bat does it). Watchdog for unattended:
   `nohup python backlog_watchdog.py > /dev/null 2>&1 &`.
2. **REVIEW GATE -- 22 folders ready right now (~1,850 raw engagements).**
   Per folder, hand to user: `python review_engagements.py <folder>` then
   `python filter_engagements.py <folder>`. Pre-flag sort (3 predict CSVs
   already written) surfaces likely-bad frames first, red if any prob >=0.5.
   The 22 slugs (raw count): rank-1-apac-primmie 185, 5000-hours-yoru-eggsterr
   135, this-is-what-a-mastered-fade / summit-demon1-omen / s0m-broken-minds-waylay
   / demon1-yoru-champions ~36-53, road-to-top-1-oxy-reyna 117,
   nats-cypher-33-kills-mvp 138, florescent-raze-top-0.1 111, cryo-clove-100t 69,
   s0m-vyse-lotus 72, s0m-clove-champion-controller 55, demon1-yoru-fast-aim 70,
   + the rest listed in `backlog_driver_log.txt` "done in" lines for 2026-08-30.
3. After every `filter_engagements.py`: retrain all 3 classifiers (standing
   workflow -- `extract_*_classifier_dataset.py` x3 then `train_*_classifier.py` x3).
4. Once all 24 reviewed+filtered: rerun `analyze_pro_baseline.py` -- baseline
   n roughly doubles from 2,145. Then eyeball the 25 worst reveals in
   `analysis_output/pro_baseline_report.md` (real pro whiffs vs detector FPs).
5. Separate track, still open: get the learner's OWN recorded matches through
   the same pipeline -- pro baseline has nothing to coach against until then.

**READY FOR GUI REVIEW RIGHT NOW: 22 videos** (the 2026-08-30 backlog run --
see the "22 of 24 analyzed" section above). 77 older folders were already
reviewed+filtered before this run. `demon1_chamber_spotcheck_backup` is
corrupted, always excluded.

## 2026-09-01: full backlog reviewed + filtered, pro baseline locked, 3 classifiers retrained

Long single session. Picked up from the 22-of-24 state above.

**1. Last 2 backlog videos analyzed.** `run_backlog.py` finished videos 23 + 24
end-to-end (fieldnames fix holding, 0 failures):
- `yoru-but-with-oxy-s-aim-terrifying-ranked-gameplay` -- 83 raw engagements
- `zekken-s-clove-is-an-unkillable-duelist-controller` -- 71 raw engagements

All 24 backlog videos from the 2026-08-30 run are now analyzed.

**2. All 24 backlog folders reviewed + filtered this session** (GUI click-through,
one at a time, pre-flag sort active). Keep rate ~31% overall (596 kept / 1936
raw), consistent with prior batches -- teammate-as-target still the dominant
drop category. Per-video kept/raw:

| # | video (slug shorthand) | kept | raw |
|---|---|---|---|
| 1 | s0m-broken-minds-waylay | 18 | 36 |
| 2 | summit-envy-demon1-omen | 13 | 38 |
| 3 | champions-mvp-demon1-yoru-envy | 22 | 38 |
| 4 | mastered-fade-s0m | 19 | 53 |
| 5 | champion-controller-s0m-clove | 18 | 55 |
| 6 | nats-viper-full-match | 15 | 57 |
| 7 | oxy-neon-1acs | 32 | 65 |
| 8 | nats-cypher-masterclass | 18 | 65 |
| 9 | cryo-clove-100t | 10 | 69 |
| 10 | florescent-waylay-entry | 24 | 70 |
| 11 | demon1-yoru-fast-aim | 32 | 70 |
| 12 | zekken-clove | 23 | 71 |
| 13 | s0m-vyse-lotus | 7 | 72 |
| 14 | nats-viper-insane | 18 | 73 |
| 15 | s0m-waylay-champion-returns | 26 | 75 |
| 16 | s0m-yoru-setup | 30 | 82 |
| 17 | yoru-oxy-aim | 41 | 83 |
| 18 | florescent-jett-fastest | 29 | 85 |
| 19 | oxy-jett-rank30 | 33 | 93 |
| 20 | florescent-raze-top0.1 | 37 | 111 |
| 21 | oxy-reyna-road-to-1 | 43 | 117 |
| 22 | eggsterr-yoru-5000h | 36 | 135 |
| 23 | nats-cypher-33k | 36 | 138 |
| 24 | primmie-apac | 16 | 185 |

`s0m-vyse-lotus` (7/72) and `primmie-apac` (16/185) are near-teammate-heavy
source videos (positioning/utility content, camera rarely in a real duel) --
same pattern as the old `aimer-aleksandar-map-control` outlier, not a detector
regression.

**3. Pro baseline rerun + LOCKED.** `analyze_pro_baseline.py` ->
`analysis_output/` now pools **100 filtered VODs / 2,741 engagements** (was
76 / 2,145). Headline numbers barely moved through a 28% data increase --
the baseline is now stable, not small-sample:
- Median crosshair-to-head at reveal: **3.06%** of screen width (mean 6.31,
  p90 16.3, p99 ~39).
- **64%** of pro reveals pre-aimed (<=5% width).
- Smoke penalty: **+0.1%** median (3.03 clear vs 3.11 near-smoke, n=1702/1039)
  -- negligible, "smokes wreck pre-aim" still does not hold.
- Duelist 3.15 vs non-duelist 2.95 -- role predicts ~nothing.
- Map is the biggest lever: Split 2.42 / Sunset 2.20 (tight) vs Ascent 4.77
  / Breeze 3.96 (open). Still only 16/100 VODs name a map.
- Tightest players (>=20 eng): primmie 1.75, cryo 1.81, ion 1.87, aspas 2.32.
  Loosest: zekken 6.03 (n=50, chamber).
- Tightest agents: omen 2.10, kayo 2.33, reyna 2.38. Loosest: raze 3.89,
  sova 3.82, chamber 3.73.
- Caveat unchanged: 2D screen distance, not angular error.

**4. All 3 pre-flag classifiers retrained** on the grown review set (101
folders, `_retrain_classifiers.sh` saved to repo -- runs all 3
`extract_*_classifier_dataset.py` then all 3 `train_*_classifier.py`):

| Classifier | dataset (good / other) | val acc | val n | confusion (tp/fp/fn/tn) | weights |
|---|---|---|---|---|---|
| ally (teammate) | 2523 / 3709 | **94.9%** | 1245 | 697/28/44/476 | `ally_classifier_head.pt` |
| gunmodel | 2523 / 396 | **98.8%** | 583 | 77/6/2/498 | `gunmodel_classifier_head.pt` |
| enemy (any-bad) | 2523 / 4306 | **95.2%** | 1365 | 830/34/31/470 | `enemy_classifier_head.pt` |

All plateaued mid-90s (gunmodel higher but its positive class is still only
396, val n for positives ~79). Consistent with the documented plateau --
dataset roughly doubled since the last retrain, accuracy flat. Nothing is
auto-rejected by any of the three; still pure pre-flag sort/highlight in
`review_engagements.py`.

### Next session -- TASKS (supersedes all earlier "next session" lists)

1. **Downloads backlog is DONE** -- all 24 analyzed, reviewed, filtered.
   ~104 videos in `C:\Users\alexh\Downloads`, essentially all processed.
   Only new channel uploads would add more (yt-dlp bot-check still unsolved,
   see 2026-08-22/23 note).
2. **THE PROJECT GOAL, now unblocked: get the learner's OWN recorded matches
   through the same pipeline.** Pro baseline (3.06% median / 64% pre-aimed)
   is locked and has nothing to coach against until the learner's gameplay
   is measured the same way. Earlier Deathmatch runs in PLAN.md are not in
   `engagements_*/` -- need fresh recordings run through
   `analyze_crosshair_placement.py` -> review -> filter, then a learner-vs-pro
   comparison layer on top of `analyze_pro_baseline.py`.
3. Optional: eyeball the 25 worst reveals in `pro_baseline_report.md` (real
   pro whiffs vs detector FPs that slipped review).
4. Standing workflow still applies: after any new `filter_engagements.py`
   run, re-run `_retrain_classifiers.sh`.

## Not yet recorded (from channel front page, latest first, as of 2026-08-16)

- This Is What a MASTERED FADE Looks Like - NRG S0M RADIANT GAMEPLAY — 26:13
- NRG s0m's Skye is UNSTOPPABLE | Valorant Gameplay — 27:41
- mvp! World Champion NRG s0m's Clove is a MASTERCLASS | Valorant Ranked Gameplay — 30:53
- mvp | Eggsterr's Yoru is ABSOLUTE CINEMA | Valorant Gameplay — 32:20

(Re-check the channel's Videos tab when resuming — new videos get posted
frequently, this list may be stale.)
