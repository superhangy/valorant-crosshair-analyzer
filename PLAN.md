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
Valorant gameplay clip, detects enemy **heads** frame-by-frame with a
fine-tuned object-detection model, and measures how close the player's
crosshair (screen center) was to the enemy's head the moment they became
visible — a proxy for "pre-aim" / crosshair placement quality. Head, not
just body/torso — that's the actual target real aim discipline cares
about. Outputs a report/chart of habits across a session.

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

## Plan (no fixed weekly schedule — learner wants to move at whatever pace
## fits each day, not stick to a week-by-week structure)
| Phase | Focus |
|---|---|
| 1 (done) | Python fundamentals (fast — leveraging Java background) |
| 2 (done) | Understand object detection conceptually; run an *existing* pretrained model on sample frames (no training yet) so the pipeline makes sense before fine-tuning |
| 3 (done) | Fine-tune YOLOv8n on the public Valorant-enemy dataset; evaluate it |
| 4 (done — core deliverable working, minor refinements possible later) | Build the analysis pipeline on the learner's own recorded clips: extract frames, run the model, compute crosshair-to-enemy offsets, chart results |

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
- Phase 3 (fine-tuning) in progress: this machine has a local NVIDIA RTX
  4070 SUPER (12GB VRAM) — confirmed via `nvidia-smi`. **Plan changed: train
  locally instead of Google Colab.** `pip install ultralytics` pulled in a
  CPU-only PyTorch build by default; reinstalled with the CUDA 12.8 wheel
  index (`pip install torch torchvision --index-url
  https://download.pytorch.org/whl/cu128`) to get GPU support — confirmed
  via `torch.cuda.is_available()`.
- Dataset: `syz-bakray/valorant-enemy-detection-m8r8n` v4 from Roboflow
  Universe (public, CC BY 4.0) — 1,170 images, single `enemies` class
  (chosen over a 24-per-agent-class alternative dataset since this project
  only needs "is there an enemy here", not which agent). Downloaded via
  `download_dataset.py` using the `roboflow` pip package; API key lives in
  `.env` (gitignored, never committed) not hardcoded. Lands in `dataset/`
  (also gitignored — it's a large third-party dataset, not ours to
  redistribute in the repo; `download_dataset.py` re-fetches it on a new
  machine).
- `finetune.py` — fine-tunes `yolov8n.pt` on this dataset (50 epochs,
  imgsz 640, batch 16) on the local GPU via `ultralytics`. Output lands in
  `runs/` (gitignored — large binary weights/logs). Needed a
  `if __name__ == "__main__":` guard around the training call — Windows
  starts DataLoader worker processes by re-importing the script, which
  crashes without the guard.
- **Phase 3 fine-tuning result (done, strong):** 50 epochs took only ~6
  minutes on the RTX 4070. Final validation: precision 0.938, recall 0.930,
  mAP50 0.952, mAP50-95 0.606. Best weights at
  `runs/detect/runs/valorant_enemy_v1-3/weights/best.pt` (not committed —
  gitignored, re-trainable via `finetune.py`).
  Re-ran the same two frames that fooled the pretrained model in Phase 2:
  `sample_frame.jpg` (killcam frame, pretrained model misboxed the
  player's own viewmodel as `person`) — fine-tuned model correctly reports
  zero detections (`finetuned_sample_frame_annotated.jpg`), that false
  positive is fixed. `dense_t099.0s.jpg` (pretrained model missed a real
  character entirely) — fine-tuned model now detects something there
  (`finetuned_dense_t099.0s.jpg`, `enemies` conf 0.54) **but see the
  correction below: that detection is itself a false positive on a
  teammate, not a genuine fix.**
- **Correction / bigger finding (learner caught this by inspecting the
  annotated image closely — I had wrongly assumed the detected character
  in `finetuned_dense_t099.0s.jpg` was the enemy "thrower" from the
  scoreboard, without actually verifying it):** Learner confirmed the game
  mechanic: enemies always render with a colored outline; teammates never
  do. Zoomed into the detected character (`zoom_check.jpg`) — no outline
  at all, just a plain "spotted"-ping dot above their head. By the
  outline rule, this is almost certainly a **teammate**, meaning that
  "correct" detection was actually a false positive that happened to look
  right at a glance.
  Why this matters beyond one wrong box: outline presence/absence may be
  the single most reliable visual signal for enemy-vs-ally in this game
  (character models/poses are identical for both teams — only the outline
  and UI color-coding differ). The public Roboflow training dataset came
  from other players' footage with unknown/inconsistent outline-color
  settings, so the model likely never learned to key off outline
  presence specifically, and partly learned a weaker proxy instead
  ("person-shaped, holding a gun, mid-combat pose") — which teammates
  satisfy just as well as enemies. This would explain both this false
  positive and is a plausible contributor to fragility in general.
  Not yet resolved — flagging as the most important open question before
  trusting this model's enemy detections at face value. Learner is going
  to record footage cycling through different Enemy Highlight Color
  settings so we can test detection confidence against real (not
  synthetic) outline colors and check how much the model's confidence
  tracks outline presence specifically.
- Also ran a synthetic version of this test on `dense_t099.0s.jpg` (global
  HSV hue-shifts via OpenCV, not isolated to just the outline — a blunter
  approximation): confidence on the (now known to be mislabeled) detected
  character dropped from 0.542 at original color to 0.094/0.038 (cyan
  shift) and 0 (green shift, red shift) — strong evidence the model is
  very sensitive to color/hue generally, consistent with the outline
  hypothesis even though this particular test wasn't a clean isolation of
  it.
- **Researched Valorant's actual rendering mechanics to ground the above
  (web search + Riot's own technical blog,
  technology.riotgames.com/news/valorant-shaders-and-gameplay-clarity)
  — refines the "outline present = enemy" theory into something more
  precise:**
  - It's called the **"Friend-or-Foe Fresnel"** effect (fresnel = extra
    rim-lighting on grazing/edge angles, used to create a silhouette).
    **Both teams get an outline** — the color is the actual signal, not
    presence/absence: enemies get a **red** fresnel (default; user-
    customizable via Settings > General > Accessibility >
    "Enemy Highlight Color" — options: red, purple, or one of two yellow
    variants for colorblind modes), allies get a fixed **neutral blue**
    fresnel (no equivalent "Ally Highlight Color" customization found).
    So the earlier framing ("enemies always outlined, teammates never")
    was learner's simplification of a more specific mechanic — corrected
    here to: color of the fresnel is the team signal, not its presence.
  - The effect is **not uniformly applied**: Riot deliberately favors
    "up-facing grazing angles" and "the upper regions of a character",
    and scales it up (brighter, larger) at distance for readability. So
    depending on pose/camera angle/distance, the effect can be strong or
    nearly invisible in a given frame — explains why `zoom_check.jpg`
    showed no obvious outline even on a fully-lit, unobstructed
    character (fresnel may have just been faint at that angle, not
    necessarily absent).
  - Also relevant to the Phase 2 pretrained-model finding: Valorant's art
    direction is explicitly **not photorealistic** — Riot's art director
    called it "illustrative visual design", blending PBR textures with
    hand-painted elements and a stylized (non-physically-accurate)
    lighting model extended from Half-Lambert shading (originated at
    Valve for TF2), chosen deliberately to prioritize gameplay clarity
    over realism. Gives a concrete, sourced, technical reason (beyond
    "it's a video game") for why a model pretrained on real photographs
    (COCO) generalizes poorly to Valorant frames.
  - Revised plan for the outline-color test footage: since fresnel
    visibility is pose/angle/distance-dependent (not just a color swap),
    footage should ideally include a few different poses/distances per
    color setting, not just one static repeated shot, to see whether the
    model's confidence tracks fresnel color specifically or just overall
    hue.
- **Confirmed directly from the training data (`check_training_colors.py`,
  contact sheet `training_color_check.jpg`):** sampled 20 labeled `enemies`
  crops from `dataset/train/` at random — **every single one** shows a
  clear red rim-light outline (18/20 had >5% reddish pixels by HSV
  threshold, mean 10.1% of crop area). The training dataset is
  effectively 100% default "Enemy Highlight Color: Red." This fully
  explains the earlier synthetic hue-shift collapse (confidence 0.542 ->
  ~0 when hue was shifted away from red) and strongly predicts the
  fine-tuned model will underperform on any non-red highlight color —
  the real footage test (next) should confirm this directly. Practical
  implication for project scope: this model likely only works reliably
  with the default red Enemy Highlight Color setting — a reasonable,
  documentable caveat rather than something to necessarily fix.
- **Real in-game outline-color test (learner recorded footage in the
  Shooting Range, cycling Enemy Highlight Color through all 4 options
  against the same practice bots) — result was surprising, revised the
  hypothesis above.** Extracted matched frames per color
  (`clipB_t016.0s.jpg` = Yellow/Deuteranopia, `clipB_t032.0s.jpg` =
  Purple/Tritanopia, `clipB_t064.0s.jpg` = Red/Default; confirmed via the
  settings dropdown visible in the footage) and ran the fine-tuned model
  at conf=0.01:
  | Color | Detections | Best conf |
  |---|---|---|
  | Yellow (Deuteranopia) | 0 | — (total miss) |
  | Purple (Tritanopia) | 10 | 0.868 |
  | Red (Default) | 4 | 0.440 |
  Purple performed *best*, not red — contradicts the naive
  "trained-on-red-so-red-wins" theory from the training-data check above.
  Visually confirmed (`colortest_real_Purple.jpg` vs
  `colortest_real_Yellow.jpg`): same bots, same distance/pose, purple
  gets 9 tight high-confidence boxes, yellow gets literally nothing.
  **Revised theory: outline-vs-background contrast, not hue-distance from
  red, is the likely real driver.** The Shooting Range walls are warm
  tan/beige. Purple is near-complementary to warm tan -> strong contrast,
  outline "pops." Yellow is close in hue to the tan wall itself -> outline
  nearly blends into the background, weak edge signal for the model (or a
  human) to key off. Red sits in between on both contrast and result,
  consistent with this theory. Under this theory the earlier synthetic
  hue-shift collapse was likely also really about breaking contrast
  against that frame's specific background, not distance-from-red per se.
  **Not fully clean yet** — the Red sample was captured from a different
  camera distance than Yellow/Purple (further back, bots smaller/seen
  through an archway), so Red's true performance at matched distance is
  still uncertain; Yellow-vs-Purple is the reliable comparison so far.
  Next: ideally get a same-distance Red comparison, and/or test the
  contrast theory directly against different-colored real Valorant maps
  (not just this one tan-walled range) since map wall color varies a lot
  across the game and the contrast theory predicts the *same* highlight
  color could perform differently on a different-colored map.
- **Another flagged-but-not-yet-tested variable (learner's catch):**
  Valorant has separate graphics settings — **Texture Quality** (texture
  detail, most relevant to character skin/clothing appearance),
  **Detail Quality** (map-level clutter like grass), and **Material
  Quality** (reflections/ability VFX density, e.g. smoke thickness,
  recon-dart brightness) — confirmed via research that Riot explicitly
  "scales environments, characters, and weapons differently" across
  quality tiers, so character rendering fidelity genuinely varies with
  these settings, not just the environment. Same category of issue as
  the outline-color finding: another player-configurable rendering
  variable with an unknown/uncontrolled value in the training footage's
  source, that may not match the learner's own settings. Not tested yet
  — would need its own comparison clip (same scene/bots, cycling
  Texture/Detail/Material Quality) similar to the outline-color test.
- **Known limitation found (also essay-worthy, not urgent to fix):** tested
  the fine-tuned model on a fresh frame (`demo_frame.jpg`) with a fully
  visible, unobstructed enemy standing in the open — total miss, 0
  detections even down to conf=0.01 (a genuine miss, not a near-threshold
  call). Immediate cause: the enemy was rendered under Reyna's ultimate
  ("Empress") screen-wide gold/yellow color-grading effect.
  Learner clarified the broader/more important point: Valorant has a
  player-configurable **"Enemy Highlight Color"** setting (an outline
  color shown on enemies through walls/smoke/behind cover) — this is a
  *persistent per-player setting*, not a rare situational ability proc
  like an ult. Whatever color the footage in the training dataset happened
  to use (likely each contributing player's own default/choice) may not
  match another player's chosen color, or the learner's own — a much more
  structural source of domain mismatch than one-off ability VFX, since it
  can affect a large fraction of frames rather than a few seconds per
  round. (Ability-specific recolors — Sova Recon, Fade reveal, Skye
  reveal, vulnerable-status pulses, etc. — are a related but separate,
  smaller-scale version of the same underlying issue: rendering states
  that are underrepresented relative to "default" enemy rendering in any
  general-gameplay dataset.)
  Good, concrete essay material either way — a real generalization-gap
  example — but not something that needs fixing for this project's scope.
- **Scope correction (learner's catch): the project needs crosshair
  distance to the enemy's HEAD, not a generic full-body box.** Re-scoped
  from the `enemies` (whole-body) fine-tune to a dedicated head detector.
  Found and downloaded a better dataset for this specific need:
  `valorant-detection/head-detector-tqndi` v1 (Roboflow, public, CC BY
  4.0) — 2,836 images, single `head` class, 1988/564/284 train/valid/test
  split. (Considered but rejected a 620-image multi-class alternative
  with `crosshair`/`enemy`/`enemyhead`/`teammate` classes — appealing
  because it also had a `teammate` class that could've fixed the
  enemy-vs-ally false positive, but its self-reported metrics were much
  weaker — mAP50 51.6% vs 99.4% — given the class split. Note: we don't
  need a `crosshair` class at all, since Valorant's crosshair always
  renders at exact screen center — that's geometry, not something to
  detect with ML.) `download_head_dataset.py` downloads it into
  `dataset_head/` (gitignored). `finetune_head.py` fine-tunes `yolov8n.pt`
  on it (same GPU setup as before). Trained in ~10 min; validation:
  precision 0.936, recall 0.885, mAP50 0.929, mAP50-95 0.487 — comparable
  to the earlier body detector, slightly lower (expected — heads are
  smaller targets). Weights at
  `runs/detect/runs/valorant_head_v1/weights/best.pt` (gitignored).
  Spot-checked on `dense_t099.0s.jpg`: tight, correctly-placed box right
  on the character's head (`head_test_dense_t099.jpg`, conf 0.558) —
  localization quality looks good. Caveat: this is the same character
  flagged earlier as likely a teammate, so this confirms precise head
  localization, not that enemy-vs-teammate disambiguation is fixed —
  that's still the open, documented limitation from before, just now
  operating on a head detector instead of a body detector.
- **Phase 4: the actual crosshair-analysis pipeline, built and validated
  (`analyze_crosshair_placement.py`).** Learner recorded a 5:06 Deathmatch
  clip specifically for this (Deathmatch = free-for-all, no teams, so
  every other player is a valid target — sidesteps the enemy-vs-teammate
  problem for this clip specifically). Pipeline: sample the clip at 30fps
  (native was 120fps — 30 is plenty precise for a ~200ms human reaction
  window), run the head detector on each sampled frame, and whenever a
  head becomes visible after not being visible ("a reveal"), record the
  pixel distance from screen center (the crosshair — Valorant always
  renders it there) to that head. Small distance = good pre-aim (you were
  already looking where they appeared, just click); large = you'd need to
  flick your mouse first. With multiple simultaneous enemies and no
  frame-to-frame identity tracking, we score the *nearest* head to the
  crosshair as a simplifying assumption (documented, not hidden).
  **First run found a serious problem the learner caught by eyeballing
  the output images (not something I verified before reporting — I only
  spot-checked the two distribution extremes and missed that the middle
  was bad; important lesson, see feedback memory):** the head detector
  alone is unreliable on full raw gameplay frames — it fired on the
  player's own gun/fist viewmodel, empty ground, doorway geometry, the
  scoreboard/killfeed player-portrait icons, and the kill-banner text
  ("SINGLE KILL" etc.) popup, not just real heads. Root cause: its
  training images were likely pre-cropped close to a person, so it never
  learned what "not a person" looks like — validation-set metrics looked
  strong (93.6%/88.5%/92.9%) but that measured the wrong thing for real
  deployment on full 2560x1440 frames full of HUD/viewmodel/environment
  clutter never well-represented in training.
  **Fix, implemented and re-validated:** (1) exclude top 20% and bottom
  25% of the frame (scoreboard/killfeed/timer live at top; kill banner/
  ammo/ability icons live at bottom — real enemies you're aiming at are
  essentially never rendered there since the crosshair is fixed at exact
  center); (2) require a head detection to also fall inside a box from
  the separately-trained Phase 3 body/`enemies` detector before trusting
  it — a gun scope or door frame is very unlikely to fool *two*
  independently-trained models at the same screen location at once.
  Result: engagement count dropped from 129 (contaminated) to 41 (clean).
  This time audited properly before reporting anything: 11 engagements
  spot-checked across the *entire* distribution (both extremes, the main
  cluster, and the tail) — all 11 confirmed genuine, including one frame
  (`t0137.07s` in `engagements/`, filename changes each pipeline run)
  where the fix visibly corrected a previous mislocalization (box had
  been on the ground; now correctly on the character's head). Learner
  independently reviewed all 41 output images too and confirmed they
  look right.
  **Final validated result: 41 real engagements, average pre-aim distance
  7.91% of screen width**, with a large genuine cluster of near-0%
  (crosshair essentially already on target) — plausible for Deathmatch
  specifically, since the same few chokepoints/angles repeat constantly
  within one session, rewarding pre-aim on those specific spots. Outputs:
  `engagements.csv` (per-engagement data), `preaim_distribution.png`
  (histogram chart), `engagements/` (annotated frames — gitignored,
  regenerate by rerunning the script; green box = body detector, blue box
  = head detector, yellow cross = crosshair/screen-center).
  **Known minor limitation, not urgent:** in some saved frames the head
  box is a little off-center from the actual head (not badly wrong, just
  imprecise) — worth revisiting later, possibly by adjusting the
  confidence threshold or examining whether specific poses/angles cause
  it, but not blocking since the core result is validated and working.
- Learner no longer wants a fixed week-by-week schedule — prefers to just
  make as much progress as fits each day/session. Phase labels above are
  loose ordering, not a calendar.

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
