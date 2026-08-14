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
- Week 1 (Python fundamentals) in progress:
  - `day1_basics.py` created — covers variables, f-strings, if/else
    (indentation vs Java braces), lists, dicts, for-loops, functions with
    default args, all with inline Java-comparison comments.
  - Learner successfully ran it via Command Prompt (`python day1_basics.py`)
    and confirmed output.
  - Learner is a genuine beginner at using a terminal/text editor, not just
    Python — needed step-by-step help opening Notepad and running Command
    Prompt. Keep instructions concrete and small (one action at a time,
    confirm output before moving on).
  - Pending task: add `win_rates["Omen"] = 49` to the dict and re-run to
    see it appear in output. (Note: the original task also asked for a
    `best_agent()` function using `max(..., key=...)` — that's too advanced
    for this stage; simplify to a plain for-loop + if-comparison instead
    when we get there, since that only uses concepts already introduced.)

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
