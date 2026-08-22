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

## Not yet recorded (from channel front page, latest first, as of 2026-08-16)

- This Is What a MASTERED FADE Looks Like - NRG S0M RADIANT GAMEPLAY — 26:13
- NRG s0m's Skye is UNSTOPPABLE | Valorant Gameplay — 27:41
- mvp! World Champion NRG s0m's Clove is a MASTERCLASS | Valorant Ranked Gameplay — 30:53
- mvp | Eggsterr's Yoru is ABSOLUTE CINEMA | Valorant Gameplay — 32:20

(Re-check the channel's Videos tab when resuming — new videos get posted
frequently, this list may be stale.)
