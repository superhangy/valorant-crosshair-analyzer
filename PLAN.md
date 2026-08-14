# Project Plan: Valorant Crosshair Discipline Analyzer

## Who this is for / why
Learner is new to both Python and ML, but experienced in Java. Goal is a
personal project (not for anyone else, not related to any scholarship/son
matter mentioned earlier — this is the learner's own thing) that can genuinely
be talked about in a college application essay: something real, self-built,
and explainable in an interview, not a copy-pasted tutorial.

Timeline: a few weeks, tight. Learner wants Claude to write most of the code,
but needs to understand it well enough to explain and defend it — not fluent
in Python syntax, but conceptually solid.

## What we're building
**Crosshair Discipline Analyzer**: an offline tool that takes a *recorded*
Valorant gameplay clip, detects enemies frame-by-frame with a fine-tuned
object-detection model, and measures how close the player's crosshair
(screen center) was to the enemy the moment they became visible — a proxy
for "pre-aim" / crosshair placement quality. Outputs a report/chart of
habits across a session.

**Hard design constraint: OFFLINE ONLY.** This analyzes video files you
already recorded (e.g. via OBS) after the fact. It never reads the live
game while it's running, never touches game memory, never acts as an
overlay. This keeps it completely clear of Riot's anti-cheat (Vanguard)
and ToS, and keeps it honestly an analytics/coaching tool rather than
anything resembling an aim-assist/cheat tool (worth noting: the same
underlying tech — enemy detection — is also used by actual cheats; the
offline-only framing is the deliberate ethical/legal line and should be
mentioned explicitly if this comes up in an essay/interview).

## Why this project (context on how it was chosen)
Considered and rejected as "not novel enough" (already well-covered by
Tracker.gg, Blitz.gg, Mobalytics, ValTracker, Aimlabs/KovaaK's):
- generic stat tracking / win-rate dashboards
- agent or comp recommenders
- AI "coaching verdict" tools
- aim trainers (those are synthetic drills, not analysis of real matches)

This project is different because no consumer tool analyzes crosshair
discipline from a player's *own real match footage*.

## Data & tech approach
- Public Roboflow "Valorant enemy detection" datasets exist (several,
  2,000+ labeled images with enemy bounding boxes) — no need to hand-label
  a large dataset from scratch.
- Fine-tune YOLOv8n (via the `ultralytics` Python package) on one of these
  datasets using a free Google Colab GPU (CPU-only training would be too
  slow on a personal laptop).
- Then build an analysis pipeline: extract frames from the learner's own
  recorded clips (OpenCV), run the fine-tuned model on each frame, compute
  pixel distance between frame-center (crosshair) and detected enemy
  bounding boxes, aggregate into stats/charts (matplotlib).

## 4-week rough plan
| Week | Focus |
|---|---|
| 1 | Python fundamentals (fast — leveraging Java background) + basics of images-as-arrays with OpenCV |
| 2 | Understand object detection conceptually; run an *existing* pretrained model on sample frames (no training yet) so the pipeline makes sense before fine-tuning |
| 3 | Fine-tune YOLOv8n on the public Valorant-enemy dataset via free Colab GPU; evaluate it |
| 4 | Build the analysis pipeline on the learner's own recorded clips: extract frames, run the model, compute crosshair-to-enemy offsets, chart results |

## Progress so far
- Environment: Python 3.12 installed (via winget). Project lives in
  `Documents\valorant-crosshair-analyzer` (originally set up on a different
  Windows PC; now continuing on this one via GitHub).
- GitHub: private repo at `github.com/superhangy/valorant-crosshair-analyzer`.
  Git identity configured to use the GitHub noreply email (privacy —
  avoids exposing real email in commit history, relevant since repo may
  go public later for an application).
- Week 1 (Python fundamentals):
  - `day1_basics.py` created — covers variables, f-strings, if/else
    (indentation vs Java braces), lists, dicts, for-loops, functions with
    default args, all with inline Java-comparison comments.
  - Learner successfully ran it via Command Prompt (`python day1_basics.py`)
    and confirmed output.
  - Learner is a genuine beginner at using a terminal/text editor, not just
    Python — needed step-by-step help opening Notepad and running Command
    Prompt. Keep instructions concrete and small (one action at a time,
    confirm output before moving on).
  - Learner reported having taught themselves enough Python independently
    to move on — Week 1 considered done, the `win_rates["Omen"]` /
    `best_agent()` exercise was skipped rather than completed.
- Week 2 (object detection concepts, pretrained model — no training yet)
  in progress:
  - Installed `ultralytics` (pulls in `torch`/`torchvision`), `opencv-python`,
    `matplotlib`.
  - `week2_pretrained_test.py` — grabs one frame from a recorded clip via
    OpenCV, runs pretrained YOLOv8n (`yolov8n.pt`, COCO-trained) on it,
    prints detections, saves an annotated image. Proves the pipeline
    (video -> frame -> model -> boxes) works end-to-end.
  - `extract_candidates.py` — helper to pull several frames from a
    timestamp range of a clip (for manually finding a frame with a real
    enemy visible, since Claude can only view still images, not video).
  - `clip_options.py` — helper to preview one late-clip frame from several
    candidate clips at once, to pick which clip to sample from.
  - **Finding (important, not a bug to fix):** across every real gameplay
    frame tested, the pretrained COCO model failed to reliably detect
    enemies. It repeatedly boxed the player's own first-person hand/weapon/
    ability viewmodel as `person` (once even as `motorcycle`), and
    separately missed clearly-visible real enemies entirely (a downed body,
    a running enemy in the open) — a consistent pattern of both false
    positives on the viewmodel and false negatives on actual enemies. This
    is the expected/desired result for this stage: it confirms the
    pipeline works and demonstrates concretely why Week 3's fine-tuning on
    a Valorant-specific dataset is necessary — a generic COCO model cannot
    reliably tell a glowing ability-fist from a person, or spot small/
    distant enemies. Worth keeping this framing (and maybe one of these
    annotated frames) for the essay: it's a clean before/after story.
  - Since Claude has no video-understanding capability (only single still
    images via the Read tool), finding a frame with a real visible enemy
    required manually extracting and eyeballing many candidate frames per
    clip — this is expected/normal for this project, not a workaround to
    "fix". A more scalable approach for Week 3+ (once fine-tuning makes
    detection reliable) is to run the model across every frame
    programmatically and only inspect the frames it flags, rather than
    scanning blindly.

## How to continue on a new machine / new Claude Code session
1. Install Python (winget: `winget install --id Python.Python.3.12`) and
   Git if not already present.
2. `git clone https://github.com/superhangy/valorant-crosshair-analyzer.git`
3. Tell Claude Code to read this PLAN.md for full context, then resume at
   the "pending task" noted above.

## Working style notes
- Claude should write most of the actual project code (especially the ML/CV
  parts later on), but explain concepts as it goes so the learner can
  genuinely explain the project, not just present it.
- Learner needs OS-level hand-holding (opening apps, running terminal
  commands) — don't assume familiarity with basic dev environment tasks.
- Keep exercises small: one new concept, one small edit, run it, confirm
  output, then move on. Avoid multi-part tasks introducing several new
  ideas at once.
