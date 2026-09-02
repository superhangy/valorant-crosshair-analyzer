# Crosshair Discipline Analyzer — the actual point of this whole project.
#
# For each moment an enemy head newly becomes visible (a "reveal"), measure
# how far the crosshair (screen center — Valorant always renders it there)
# was from that head. Small distance = good pre-aim (you were already
# looking at the spot they appeared, so you just click). Large distance =
# you'd need to flick your mouse to react, costing time.

import argparse
import csv
import os
import shutil

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pytesseract
from ultralytics import YOLO

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEFAULT_CLIP_PATH = r"C:\Users\alexh\Videos\NVIDIA\Valorant\Valorant 2026.08.14 - 19.49.11.07.mp4"
HEAD_MODEL_PATH = "runs/detect/runs/valorant_head_gray_v1/weights/best.pt"
BODY_MODEL_PATH = "runs/detect/runs/valorant_enemy_v1-3/weights/best.pt"
DEFAULT_OUTPUT_DIR = "engagements"

HEAD_CONF_THRESHOLD = 0.4  # how sure the head model must be
BODY_CONF_THRESHOLD = 0.3  # how sure the body model must be (used only to
                            # cross-check heads, so can run a bit looser)
PROCESS_FPS = 30           # sample rate — plenty precise for a ~200ms reaction window
GRACE_SECONDS = 0.5        # bridge brief detection flicker before resetting "visible" state

# The head detector alone turned out to be unreliable on full raw gameplay
# frames — it fires on the player's own gun/fist viewmodel, empty ground,
# doorway geometry, and small HUD elements (scoreboard portraits, kill
# banners), not just real heads. Its training images were likely pre-cropped
# close to a person, so it never learned what "not a person" looks like.
# Fix: only trust a head detection if it also falls inside a box from the
# separately-trained body/"enemies" detector (Phase 3) — a gun scope or a
# doorway is very unlikely to fool *both* independently-trained models at
# the same location.
HEAD_MUST_BE_INSIDE_BODY_BOX = True

# The scoreboard/timer bar and kill-feed panel (top) and the kill banner /
# ammo count / ability icons (bottom) all live in fixed HUD bands. Real
# enemies you're aiming at are essentially never up there or down there,
# since the crosshair sits at exact screen center — safe to exclude both.
TOP_EXCLUSION_HEIGHT_FRAC = 0.20
BOTTOM_EXCLUSION_HEIGHT_FRAC = 0.75

# Gun-viewmodel-as-head heuristic reject (see is_gun_viewmodel_box below for
# the calibration this was derived from).
GUN_VIEWMODEL_MIN_WIDTH_FRAC = 0.05
GUN_VIEWMODEL_MIN_CENTER_X_FRAC = 0.55

# Smoke tagging (additive metadata only — does not filter/exclude any
# engagement, just labels it so smoke vs. no-smoke pre-aim can be sliced
# later). HSV threshold, not a trained model: Valorant smokes read as a
# low-saturation, mid-to-high-value translucent cloud. This is a coarse
# first pass — will also fire on some gray map geometry/concrete, so treat
# the tag as approximate, not ground truth.
SMOKE_SAT_MAX = 40      # low saturation = washed-out/grayish
SMOKE_VAL_MIN = 100     # not near-black
SMOKE_VAL_MAX = 240     # not blown-out white (HUD, sky glare)
SMOKE_PRESENT_THRESHOLD_PCT = 5.0  # local coverage above this counts as "near a smoke"
SMOKE_LOCAL_RADIUS_PX = 150        # how far around the head box counts as "near"

# Team-color outline filter (CPU-only HSV heuristic, no GPU/model involved).
# Valorant renders a rim-light "Friend-or-Foe Fresnel" outline on every
# character: allies always render a fixed neutral BLUE outline regardless of
# settings; enemies render RED (default) or PURPLE/YELLOW depending on the
# viewer's own "Enemy Highlight Color" accessibility setting. Sampling the
# outline color directly is a much cheaper and more targeted team signal
# than hoping the detector learned it implicitly (it didn't -- see
# false_positives_demon1_chamber.txt for a confirmed teammate hit).
# NOTE: thresholds below are a first-pass estimate, not yet calibrated
# against real footage (clipB_t016/032/064.0s.jpg are real reference frames
# per outline color, from the earlier color-sensitivity experiments) --
# treat as coarse, same spirit as the smoke heuristic above. Fresnel
# intensity is pose/angle/distance-dependent and can be faint or absent in
# a given frame (see PLAN.md), so this only REJECTS a box when the
# ally-blue signal is strong and unambiguous; anything else is left
# unfiltered rather than risk a new false negative.
ALLY_HUE_RANGE = (100, 125)          # OpenCV HSV hue (0-179) -- neutral blue
OUTLINE_SAT_MIN = 60
OUTLINE_VAL_MIN = 80
OUTLINE_RING_PX = 6                  # how far outside the box edge to sample
ALLY_RING_FRACTION_THRESHOLD = 0.35  # fraction of ring pixels that must read
                                      # ally-blue to reject the box

# Second, stronger signal: Valorant's fixed ally/enemy UI color scheme
# (health bar / nameplate underline -- always green for your own team, red
# for enemies, not a settings option like Enemy Highlight Color). User
# confirmed in-game that the fresnel rim above is barely visible in
# practice, so this nameplate check is the primary catch and the outline
# check above is a secondary/complementary one. Calibrated directly against
# a real confirmed-teammate frame (Skye, t1023.25s.jpg): the bright pixels
# of her nameplate bar measured hue~60, sat~224, val~183.
NAMEPLATE_BAND_HEIGHT_PX = 40   # UI band checked below a box's bottom edge
NAMEPLATE_SIDE_MARGIN_PX = 20
ALLY_NAMEPLATE_HUE_RANGE = (50, 70)
NAMEPLATE_SAT_MIN = 150
NAMEPLATE_VAL_MIN = 120
ALLY_NAMEPLATE_PIXEL_THRESHOLD = 20  # raw qualifying-pixel count, not a
                                      # fraction -- the band is mostly empty
                                      # space around the thin colored bar

# Killcam / death-replay filter. When you're dead and watching the replay
# of who killed you, the crosshair isn't under your control -- any "head
# reveal" detected during that replay isn't a real pre-aim data point and
# was contaminating the results (see t0835.08s.jpg in
# engagements_demon1_chamber, a killcam frame that got scored as a real
# engagement). Valorant renders a solid red "KILLED BY <agent>" banner with
# a matching red name bar in the upper-right during this state -- checked
# as fractions of frame size so it isn't tied to one video's resolution.
# Calibrated against a real raw (unannotated) frame: the name bar measured
# hue~176 (red wraps near 0/180), sat~201, val~238 over ~70% of its area.
KILLCAM_BANNER_Y_FRAC = (0.40, 0.47)
KILLCAM_BANNER_X_FRAC = (0.75, 1.0)
KILLCAM_RED_HUE_LOW = (0, 10)
KILLCAM_RED_HUE_HIGH = (170, 179)
KILLCAM_SAT_MIN = 120
KILLCAM_VAL_MIN = 120
KILLCAM_RED_FRACTION_THRESHOLD = 0.15

# Buy-phase filter, same idea as the killcam one: round hasn't started,
# nobody's a real combat target yet (teammates walk freely near spawn --
# see t0197.04s.jpg in engagements_demon1_chamber, a buy-phase frame that
# scored a teammate, "Clove", as an engagement). The "BUY PHASE" banner is
# large bold white/near-white text -- checked as fractions of frame size.
# Calibrated against a real raw frame: ~24% of the banner region reads as
# white text (low saturation, high value); threshold set well below that
# for margin against ordinary gameplay backgrounds in the same region.
BUYPHASE_BANNER_Y_FRAC = (0.133, 0.258)
BUYPHASE_BANNER_X_FRAC = (0.4125, 0.580)
BUYPHASE_WHITE_SAT_MAX = 40
BUYPHASE_WHITE_VAL_MIN = 180
BUYPHASE_WHITE_FRACTION_THRESHOLD = 0.12

# Spectate-state filter. Once demon1 dies, the client switches to spectating
# a teammate -- the crosshair on screen belongs to whoever's being followed,
# not demon1, so any "head reveal" measured during this state is scoring the
# wrong player's aim entirely (see false_positives_demon1_chamber.txt: 19 of
# 66 post-filter frames were this, the single largest contamination source).
# Valorant renders a small "SPECTATORS N" counter fixed in the top-right
# corner for the whole time you're dead -- unlike the other HUD banners
# above, this is small text on a busy/varying background, so a pixel-color
# heuristic isn't reliable here; OCR on a tight crop of just that corner is
# cheap (small image) and much more robust. NOTE: this misses the rare frame
# where something else fully occludes that corner (e.g. a stray Chrome
# automation banner baked into one early frame of the demon1_chamber source
# recording) -- accepted as a known miss rather than something worth solving.
SPECTATORS_CORNER_Y_FRAC = (0.0, 0.04)
SPECTATORS_CORNER_X_FRAC = (0.85, 0.99)

# Right in the first few seconds after dying, Valorant shows a "COMBAT
# REPORT" death-recap card instead of the "SPECTATORS N" counter (the
# counter only appears once that card fades) -- confirmed on a real frame
# (t1379.02s) that slipped through the SPECTATORS-only check because at
# that exact instant the corner where the counter would go was occupied by
# an unrelated stream overlay instead. Same OCR approach, different region
# and phrase; still gated behind an already-found head candidate.
COMBAT_REPORT_Y_FRAC = (0.30, 0.60)
COMBAT_REPORT_X_FRAC = (0.78, 0.99)

# Scoreboard (Tab-menu) filter. Holding Tab overlays the full scoreboard --
# a big fixed-layout table with a translucent green tint over the ally rows
# (top half) and red tint over the enemy rows (bottom half). The head
# detector sometimes fires on a player-portrait thumbnail inside that table,
# which isn't a real 3D character at all (see false_positives_demon1_chamber.txt).
# Unlike the spectate counter, this is a big, high-contrast, consistently
# colored region, so a plain HSV fraction check (same style as the killcam/
# buy-phase filters above) works well -- calibrated against two real
# scoreboard frames (t0181.54s, t0705.38s: top-half green_frac ~0.66-0.71,
# bottom-half red_frac ~0.69-0.73) against two real non-scoreboard frames
# (green_frac ~0.08-0.16, red_frac ~0.002-0.09), leaving a wide margin.
SCOREBOARD_REGION_Y_FRAC = (0.28, 0.70)
SCOREBOARD_REGION_X_FRAC = (0.28, 0.72)
SCOREBOARD_GREEN_HUE_RANGE = (40, 85)
SCOREBOARD_RED_HUE_LOW = (0, 10)
SCOREBOARD_RED_HUE_HIGH = (170, 179)
SCOREBOARD_SAT_MIN = 30
SCOREBOARD_GREEN_FRACTION_THRESHOLD = 0.35
SCOREBOARD_RED_FRACTION_THRESHOLD = 0.35


def point_in_box(px, py, box):
    x1, y1, x2, y2 = box
    return x1 <= px <= x2 and y1 <= py <= y2


def compute_smoke_mask(frame, frame_h, top_frac, bottom_frac):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    mask = ((sat < SMOKE_SAT_MAX) & (val > SMOKE_VAL_MIN) & (val < SMOKE_VAL_MAX)).astype(np.uint8)
    top, bottom = int(frame_h * top_frac), int(frame_h * bottom_frac)
    mask[:top, :] = 0
    mask[bottom:, :] = 0
    return mask


def smoke_coverage_pct(mask, x1, y1, x2, y2):
    region = mask[y1:y2, x1:x2]
    if region.size == 0:
        return 0.0
    return 100.0 * cv2.countNonZero(region) / region.size


def ring_mask_for_box(frame_shape, box, ring_px):
    # Boolean mask of a thin band just outside the given box, clipped to
    # the frame -- the box interior is carved out so only the rim is
    # sampled, not the character's base clothing/skin color.
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    ox1, oy1 = max(0, x1 - ring_px), max(0, y1 - ring_px)
    ox2, oy2 = min(w, x2 + ring_px), min(h, y2 + ring_px)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[oy1:oy2, ox1:ox2] = 1
    mask[y1:y2, x1:x2] = 0
    return mask


def is_ally_outline(color_frame, box):
    # Sample the rim-light ring around a box on the COLOR frame (not the
    # grayscale head-model input) and check for the neutral-blue ally
    # fresnel. True means "reject -- this looks like a teammate."
    mask = ring_mask_for_box(color_frame.shape, box, OUTLINE_RING_PX)
    ring_total = int(mask.sum())
    if ring_total == 0:
        return False
    hsv = cv2.cvtColor(color_frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    ally_pixels = (
        (h >= ALLY_HUE_RANGE[0]) & (h <= ALLY_HUE_RANGE[1])
        & (s >= OUTLINE_SAT_MIN) & (v >= OUTLINE_VAL_MIN) & (mask == 1)
    )
    return (int(ally_pixels.sum()) / ring_total) >= ALLY_RING_FRACTION_THRESHOLD


def has_ally_nameplate(color_frame, box):
    # Check the band just below a box for Valorant's ally-team UI green
    # (health bar / nameplate underline). True means "reject -- this looks
    # like a teammate."
    h_img, w_img = color_frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bx1 = max(0, x1 - NAMEPLATE_SIDE_MARGIN_PX)
    bx2 = min(w_img, x2 + NAMEPLATE_SIDE_MARGIN_PX)
    by1 = max(0, y2)
    by2 = min(h_img, y2 + NAMEPLATE_BAND_HEIGHT_PX)
    band = color_frame[by1:by2, bx1:bx2]
    if band.size == 0:
        return False
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    ally_pixels = (
        (h >= ALLY_NAMEPLATE_HUE_RANGE[0]) & (h <= ALLY_NAMEPLATE_HUE_RANGE[1])
        & (s >= NAMEPLATE_SAT_MIN) & (v >= NAMEPLATE_VAL_MIN)
    )
    return int(ally_pixels.sum()) >= ALLY_NAMEPLATE_PIXEL_THRESHOLD


def is_gun_viewmodel_box(box, frame_w, frame_h):
    # The player's own gun/fist viewmodel sometimes fools both the head and
    # body detectors at once (see HEAD_MUST_BE_INSIDE_BODY_BOX comment above)
    # so cross-checking alone doesn't catch it. Calibrated against 250
    # reviewed "good" vs 56 "gun-viewmodel-as-head" scored boxes: real
    # enemy boxes cluster narrow (median 2.3% of frame width) and centered
    # near the crosshair (median x-center ~50%), since that's where the
    # player was aiming. Viewmodel boxes run much wider (median 6.6%) and
    # sit right-of-center (median x-center ~63%, weapon held on-screen
    # right). Backtested at ~73% catch / ~3% cost on that sample, but not
    # yet trusted against real accuracy at scale -- per user request
    # (2026-08-26) this is prediction-only for now (see gun_viewmodel_pred
    # in the engagements.csv output), not a reject. gun-viewmodel-as-head
    # stays a manual review category either way.
    x1, y1, x2, y2 = box
    width_frac = (x2 - x1) / frame_w
    center_x_frac = ((x1 + x2) / 2) / frame_w
    return width_frac > GUN_VIEWMODEL_MIN_WIDTH_FRAC and center_x_frac > GUN_VIEWMODEL_MIN_CENTER_X_FRAC


def is_killcam_frame(frame):
    h_img, w_img = frame.shape[:2]
    y1 = int(h_img * KILLCAM_BANNER_Y_FRAC[0])
    y2 = int(h_img * KILLCAM_BANNER_Y_FRAC[1])
    x1 = int(w_img * KILLCAM_BANNER_X_FRAC[0])
    x2 = int(w_img * KILLCAM_BANNER_X_FRAC[1])
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return False
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = (
        ((h <= KILLCAM_RED_HUE_LOW[1]) | (h >= KILLCAM_RED_HUE_HIGH[0]))
        & (s >= KILLCAM_SAT_MIN) & (v >= KILLCAM_VAL_MIN)
    )
    return float(red.mean()) >= KILLCAM_RED_FRACTION_THRESHOLD


def is_buy_phase_frame(frame):
    h_img, w_img = frame.shape[:2]
    y1 = int(h_img * BUYPHASE_BANNER_Y_FRAC[0])
    y2 = int(h_img * BUYPHASE_BANNER_Y_FRAC[1])
    x1 = int(w_img * BUYPHASE_BANNER_X_FRAC[0])
    x2 = int(w_img * BUYPHASE_BANNER_X_FRAC[1])
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return False
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    white = (s <= BUYPHASE_WHITE_SAT_MAX) & (v >= BUYPHASE_WHITE_VAL_MIN)
    return float(white.mean()) >= BUYPHASE_WHITE_FRACTION_THRESHOLD


def is_spectate_frame(frame):
    h_img, w_img = frame.shape[:2]
    y1 = int(h_img * SPECTATORS_CORNER_Y_FRAC[0])
    y2 = int(h_img * SPECTATORS_CORNER_Y_FRAC[1])
    x1 = int(w_img * SPECTATORS_CORNER_X_FRAC[0])
    x2 = int(w_img * SPECTATORS_CORNER_X_FRAC[1])
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    # Otsu threshold rather than a fixed cutoff -- the corner's background
    # varies a lot (sky, wall, HUD panel), but Otsu adapts per-crop and
    # tesseract reads cleanly off the resulting binary image either way.
    _, binary = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(binary, config="--psm 7")
    return "SPECTATOR" in text.upper()


def is_combat_report_frame(frame):
    h_img, w_img = frame.shape[:2]
    y1 = int(h_img * COMBAT_REPORT_Y_FRAC[0])
    y2 = int(h_img * COMBAT_REPORT_Y_FRAC[1])
    x1 = int(w_img * COMBAT_REPORT_X_FRAC[0])
    x2 = int(w_img * COMBAT_REPORT_X_FRAC[1])
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(binary, config="--psm 6").upper()
    return "COMBAT REPORT" in text


def is_match_end_frame(frame):
    # Post-round/post-match victory-defeat summary screen (huge stylized
    # "VICTORY"/"DEFEAT" art + an MVP stat card) and the pre-match agent-
    # select screen both got mistaken for real engagements -- a character
    # model standing against a near-flat colored background reads as a
    # legit head+body to both detectors. Tried a pure color-uniformity
    # heuristic first (checking how much of the frame one dominant hue
    # covers) but it wasn't reliable -- some real gameplay frames with a
    # large single-color wall (e.g. Lotus's red temple interior) score just
    # as "flat" as these UI screens. "KDA" on the MVP card is a clean,
    # locale-independent signal instead (unlike "VICTORY", which is
    # rendered in the client's language -- this VOD's Chinese client shows
    # "胜利" there, not the English word) -- confirmed zero false positives
    # against real gameplay, spectate, and Tab-scoreboard frames. Only
    # catches the post-match screen, not the agent-select screen (no KDA
    # card there) -- that's a separate, still-open false-positive source.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray)
    return "KDA" in text.upper()


def is_scoreboard_frame(frame):
    h_img, w_img = frame.shape[:2]
    y1 = int(h_img * SCOREBOARD_REGION_Y_FRAC[0])
    y2 = int(h_img * SCOREBOARD_REGION_Y_FRAC[1])
    x1 = int(w_img * SCOREBOARD_REGION_X_FRAC[0])
    x2 = int(w_img * SCOREBOARD_REGION_X_FRAC[1])
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return False
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mid = hsv.shape[0] // 2
    top_h, top_s = hsv[:mid, :, 0], hsv[:mid, :, 1]
    bot_h, bot_s = hsv[mid:, :, 0], hsv[mid:, :, 1]
    green = (
        (top_h >= SCOREBOARD_GREEN_HUE_RANGE[0]) & (top_h <= SCOREBOARD_GREEN_HUE_RANGE[1])
        & (top_s >= SCOREBOARD_SAT_MIN)
    )
    red = (
        ((bot_h <= SCOREBOARD_RED_HUE_LOW[1]) | (bot_h >= SCOREBOARD_RED_HUE_HIGH[0]))
        & (bot_s >= SCOREBOARD_SAT_MIN)
    )
    return (
        float(green.mean()) >= SCOREBOARD_GREEN_FRACTION_THRESHOLD
        and float(red.mean()) >= SCOREBOARD_RED_FRACTION_THRESHOLD
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default=DEFAULT_CLIP_PATH, help="Path to the gameplay clip to analyze")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="Directory for engagements.csv, preaim_distribution.png, and annotated frames")
    args = parser.parse_args()
    clip_path = args.clip
    output_dir = args.output

    # Clear old annotated frames first - otherwise a rerun (e.g. after
    # swapping models) leaves stale frames from the previous run mixed in
    # with the new ones, since filenames are timestamp-based and rarely
    # collide.
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)
    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    cap = cv2.VideoCapture(clip_path)
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    frame_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    center_x, center_y = frame_w / 2, frame_h / 2

    step = max(round(source_fps / PROCESS_FPS), 1)
    grace_samples = max(round(GRACE_SECONDS * PROCESS_FPS), 1)

    engagements = []
    frames_since_seen = grace_samples + 1  # start "not visible"
    frame_index = 0
    sample_index = 0

    while True:
        ok = cap.grab()
        if not ok:
            break
        frame_index += 1
        if frame_index % step != 0:
            continue

        ok, frame = cap.retrieve()
        if not ok:
            break
        sample_index += 1
        timestamp = frame_index / source_fps

        if is_killcam_frame(frame) or is_buy_phase_frame(frame) or is_scoreboard_frame(frame):
            # Dead-replay, pre-round buy phase, or Tab-scoreboard overlay --
            # crosshair isn't in a real combat context in any of these
            # states, so this can't be a real reveal. Treated the same as
            # "no head found" (not just skipped) so the grace-period timer
            # doesn't go stale across the gap and wrongly suppress a genuine
            # reveal once the round starts. All three checks here are cheap
            # pixel/HSV math -- safe to run on every sampled frame. The
            # spectate check below is OCR (much slower), so it's deferred
            # until a head candidate is actually about to be scored instead
            # of running on all ~60k sampled frames in a full VOD.
            frames_since_seen += 1
            continue

        # Head model was trained on grayscale-only images (see
        # make_grayscale_dataset.py) to reduce sensitivity to Enemy
        # Highlight Color - must feed it grayscale input too, or it sees
        # a different input distribution than it trained on. Body model
        # below stays color, since it's still the color-trained detector.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        head_input = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        head_results = head_model(head_input, conf=HEAD_CONF_THRESHOLD, verbose=False)
        head_boxes = head_results[0].boxes

        body_boxes_xyxy = []
        if HEAD_MUST_BE_INSIDE_BODY_BOX:
            body_results = body_model(frame, conf=BODY_CONF_THRESHOLD, verbose=False)
            body_boxes_xyxy = [b.xyxy[0].tolist() for b in body_results[0].boxes]

        # Nearest-head heuristic: with multiple simultaneous enemies and no
        # frame-to-frame identity tracking, we can't cleanly tell "which one
        # is new" — so we treat "any head visible after none were" as one
        # reveal event, and score it against whichever head is closest to
        # the crosshair (the one the player would actually be reacting to).
        # HUD-region boxes are skipped entirely, and (if enabled) a head box
        # must also fall inside a body-detector box to count as real —
        # see the comments above HEAD_MUST_BE_INSIDE_BODY_BOX.
        best_box = None
        best_dist = None
        best_outline_box = None
        for box in head_boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            hx, hy = (x1 + x2) / 2, (y1 + y2) / 2
            if hy < frame_h * TOP_EXCLUSION_HEIGHT_FRAC or hy > frame_h * BOTTOM_EXCLUSION_HEIGHT_FRAC:
                continue
            matching_body_box = None
            if HEAD_MUST_BE_INSIDE_BODY_BOX:
                matching_body_box = next((bbox for bbox in body_boxes_xyxy if point_in_box(hx, hy, bbox)), None)
                if matching_body_box is None:
                    continue
            # Prefer the (larger) body box for the outline check -- more
            # silhouette edge to sample than the small head box gives.
            outline_box = matching_body_box if matching_body_box is not None else (x1, y1, x2, y2)
            if is_ally_outline(frame, outline_box) or has_ally_nameplate(frame, outline_box):
                continue
            dist = ((hx - center_x) ** 2 + (hy - center_y) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_box = (hx, hy, float(box.conf[0]), x1, y1, x2, y2)
                best_outline_box = outline_box

        if best_box is None:
            frames_since_seen += 1
            continue

        if is_spectate_frame(frame) or is_combat_report_frame(frame) or is_match_end_frame(frame):
            # OCR is slow, so this only runs on frames that already cleared
            # every cheap check and found a head candidate -- a few hundred
            # times per video rather than tens of thousands. Post-death
            # spectate (ongoing "SPECTATORS N" counter, or the death-recap
            # "COMBAT REPORT" card shown in the first few seconds before
            # that counter appears): the crosshair belongs to whoever
            # demon1 is following, not demon1, so this can't be scored as
            # demon1's pre-aim either way. Same "treat as no head found"
            # handling as the other state filters above.
            frames_since_seen += 1
            continue

        was_visible = frames_since_seen <= grace_samples
        frames_since_seen = 0

        if not was_visible:
            hx, hy, conf, head_x1, head_y1, head_x2, head_y2 = best_box
            dist_pct = best_dist / frame_w * 100

            smoke_mask = compute_smoke_mask(frame, frame_h, TOP_EXCLUSION_HEIGHT_FRAC, BOTTOM_EXCLUSION_HEIGHT_FRAC)
            frame_smoke_pct = smoke_coverage_pct(smoke_mask, 0, 0, int(frame_w), int(frame_h))
            lx1 = max(0, int(hx - SMOKE_LOCAL_RADIUS_PX))
            ly1 = max(0, int(hy - SMOKE_LOCAL_RADIUS_PX))
            lx2 = min(int(frame_w), int(hx + SMOKE_LOCAL_RADIUS_PX))
            ly2 = min(int(frame_h), int(hy + SMOKE_LOCAL_RADIUS_PX))
            local_smoke_pct = smoke_coverage_pct(smoke_mask, lx1, ly1, lx2, ly2)
            smoke_present = local_smoke_pct > SMOKE_PRESENT_THRESHOLD_PCT

            box_x1, box_y1, box_x2, box_y2 = best_outline_box
            gun_viewmodel_pred = is_gun_viewmodel_box(best_outline_box, frame_w, frame_h)

            engagements.append({
                "timestamp_s": round(timestamp, 2),
                "distance_px": round(best_dist, 1),
                "distance_pct_width": round(dist_pct, 2),
                "confidence": round(conf, 3),
                "smoke_present": smoke_present,
                "smoke_near_target_pct": round(local_smoke_pct, 2),
                "smoke_frame_coverage_pct": round(frame_smoke_pct, 2),
                # Prediction only, not a filter -- accuracy not yet trusted
                # (see is_gun_viewmodel_box), so nothing gets dropped based
                # on this. Recorded so it can be spot-checked against real
                # review labels before ever being turned back into a reject.
                "gun_viewmodel_pred": gun_viewmodel_pred,
                # The scored box (body-outline box, same one is_ally_outline/
                # has_ally_nameplate checked above) -- saved so downstream
                # tools (predict_teammate_prob.py, extract_ally_classifier_
                # dataset.py) can crop directly instead of re-running head+body
                # detection on a re-extracted frame, which misses boxes when
                # ffmpeg's -ss seek lands on a slightly different frame.
                "box_x1": round(box_x1, 1),
                "box_y1": round(box_y1, 1),
                "box_x2": round(box_x2, 1),
                "box_y2": round(box_y2, 1),
            })

            # Draw both models' boxes so a human reviewer can see exactly
            # why a detection was (or wasn't) trusted — body boxes in
            # green, the winning head box in blue.
            annotated = frame.copy()
            for bx1, by1, bx2, by2 in body_boxes_xyxy:
                cv2.rectangle(annotated, (int(bx1), int(by1)), (int(bx2), int(by2)), (0, 200, 0), 2)
            hx1, hy1 = int(head_x1), int(head_y1)
            hx2, hy2 = int(head_x2), int(head_y2)
            cv2.rectangle(annotated, (hx1, hy1), (hx2, hy2), (255, 100, 0), 2)
            cv2.putText(annotated, f"head {conf:.2f}", (hx1, hy1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 0), 2, cv2.LINE_AA)
            cv2.drawMarker(annotated, (int(center_x), int(center_y)),
                            (255, 255, 0), cv2.MARKER_CROSS, 30, 2)
            out_path = os.path.join(output_dir, f"t{timestamp:07.2f}s.jpg")
            cv2.imwrite(out_path, annotated)

    cap.release()

    # Save results
    with open(os.path.join(output_dir, "engagements.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_s", "distance_px", "distance_pct_width", "confidence",
                                                "smoke_present", "smoke_near_target_pct", "smoke_frame_coverage_pct",
                                                "gun_viewmodel_pred",
                                                "box_x1", "box_y1", "box_x2", "box_y2"])
        writer.writeheader()
        writer.writerows(engagements)

    print(f"Processed {sample_index} sampled frames ({frame_index} total frames in clip).")
    print(f"Found {len(engagements)} engagements (enemy reveal moments).")

    if engagements:
        distances = [e["distance_pct_width"] for e in engagements]
        avg = sum(distances) / len(distances)
        print(f"Average pre-aim distance: {avg:.2f}% of screen width")
        print(f"Best (smallest): {min(distances):.2f}%  Worst (largest): {max(distances):.2f}%")

        smoke_dists = [e["distance_pct_width"] for e in engagements if e["smoke_present"]]
        clear_dists = [e["distance_pct_width"] for e in engagements if not e["smoke_present"]]
        print(f"Near-smoke engagements: {len(smoke_dists)}"
              + (f" (avg {sum(smoke_dists)/len(smoke_dists):.2f}%)" if smoke_dists else ""))
        print(f"Clear-sightline engagements: {len(clear_dists)}"
              + (f" (avg {sum(clear_dists)/len(clear_dists):.2f}%)" if clear_dists else ""))

        plt.figure(figsize=(8, 5))
        plt.hist(distances, bins=20, color="#4C72B0", edgecolor="white")
        plt.xlabel("Pre-aim distance at reveal (% of screen width)")
        plt.ylabel("Number of engagements")
        plt.title(f"Crosshair Pre-Aim Discipline — {len(engagements)} engagements")
        plt.axvline(avg, color="red", linestyle="--", label=f"Average: {avg:.1f}%")
        plt.legend()
        plt.tight_layout()
        chart_path = os.path.join(output_dir, "preaim_distribution.png")
        plt.savefig(chart_path, dpi=150)
        print(f"Saved chart: {chart_path}")
        print(f"Saved per-engagement data: {os.path.join(output_dir, 'engagements.csv')}")
        print(f"Saved annotated frames: {output_dir}/")
        print(f"\nREVIEW REQUIRED before this data is used in any analysis:")
        print(f"    python review_engagements.py {output_dir}")
        print(f"    python filter_engagements.py {output_dir}")


if __name__ == "__main__":
    main()
