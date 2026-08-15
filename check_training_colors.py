# Sample labeled "enemies" boxes from the training set and check what
# fresnel/outline color actually shows up in them, to test the hypothesis
# that the dataset is dominated by the default red highlight color.

import glob
import os
import random

import cv2
import numpy as np

IMAGES_DIR = "dataset/train/images"
LABELS_DIR = "dataset/train/labels"
PAD = 15          # extra pixels around the labeled box, to catch the outline
SAMPLE_SIZE = 20
CROP_SIZE = 160    # each tile in the contact sheet, resized to this

random.seed(0)
label_files = glob.glob(os.path.join(LABELS_DIR, "*.txt"))
sample = random.sample(label_files, SAMPLE_SIZE)

tiles = []
red_hue_fractions = []

for label_path in sample:
    stem = os.path.splitext(os.path.basename(label_path))[0]
    img_path = os.path.join(IMAGES_DIR, stem + ".jpg")
    img = cv2.imread(img_path)
    if img is None:
        continue
    h, w = img.shape[:2]

    with open(label_path) as f:
        line = f.readline().strip()
    if not line:
        continue
    _, xc, yc, bw, bh = map(float, line.split())
    x1 = int((xc - bw / 2) * w) - PAD
    y1 = int((yc - bh / 2) * h) - PAD
    x2 = int((xc + bw / 2) * w) + PAD
    y2 = int((yc + bh / 2) * h) + PAD
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w), min(y2, h)

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        continue

    # Quantify: fraction of pixels that fall in a "reddish" hue range
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0]
    sat = hsv[..., 1]
    val = hsv[..., 2]
    # red wraps around hue 0/180 in OpenCV's 0-179 scale; require some
    # saturation/brightness so we're not counting grey/dark background
    reddish = (((hue < 10) | (hue > 170)) & (sat > 80) & (val > 80))
    red_fraction = reddish.mean()
    red_hue_fractions.append(red_fraction)

    tile = cv2.resize(crop, (CROP_SIZE, CROP_SIZE))
    cv2.putText(tile, f"{red_fraction:.2f}", (4, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
    tiles.append(tile)

# Assemble into a grid contact sheet
cols = 5
rows = (len(tiles) + cols - 1) // cols
grid = np.zeros((rows * CROP_SIZE, cols * CROP_SIZE, 3), dtype=np.uint8)
for i, tile in enumerate(tiles):
    r, c = divmod(i, cols)
    grid[r * CROP_SIZE:(r + 1) * CROP_SIZE, c * CROP_SIZE:(c + 1) * CROP_SIZE] = tile

cv2.imwrite("training_color_check.jpg", grid)

print(f"Sampled {len(tiles)} labeled enemy crops.")
print(f"Mean red-hue-pixel fraction per crop: {np.mean(red_hue_fractions):.3f}")
print(f"Crops with >5% reddish pixels: {sum(f > 0.05 for f in red_hue_fractions)}/{len(red_hue_fractions)}")
print("Saved contact sheet: training_color_check.jpg (number in each tile = reddish-pixel fraction)")
