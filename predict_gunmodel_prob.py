"""
Pre-flag pass for review_engagements.py: runs the trained gunmodel_classifier
(gunmodel_classifier_head.pt, see train_gunmodel_classifier.py) over every raw
engagement frame in a folder and writes a <folder>_gunmodel_predictions.csv of
gun-viewmodel-probability scores. Does NOT touch engagements.csv or drop
anything -- review_engagements.py reads this file (if present) to sort
likely-bad frames first / show the score, but every frame still gets
manually reviewed. Pure pre-sort convenience, not a filter (same role as
predict_teammate_prob.py, separate model/category).

Usage:
    python predict_gunmodel_prob.py engagements_<slug> [<folder> ...]
"""

import csv
import re
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
from ultralytics import YOLO

from analyze_crosshair_placement import HEAD_MODEL_PATH, BODY_MODEL_PATH
from calibrate_ally_filter import find_scored_box, load_boxes_from_engagements_csv
from extract_ally_classifier_dataset import padded_crop
from extract_hard_negatives_from_review import extract_frame, find_video_for_slug

REPO_ROOT = Path(__file__).resolve().parent
WEIGHTS_PATH = REPO_ROOT / "gunmodel_classifier_head.pt"
TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")

TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def build_model(device):
    # weights=None: load_state_dict below fully replaces every parameter with
    # the trained head_pt, so the ImageNet download is pure waste here and
    # would break the offline / portable build.
    backbone = models.resnet18(weights=None)
    for p in backbone.parameters():
        p.requires_grad = False
    in_features = backbone.fc.in_features
    backbone.fc = nn.Sequential(
        nn.Linear(in_features, 64),
        nn.ReLU(),
        nn.Dropout(0.4),
        nn.Linear(64, 2),
    )
    backbone.load_state_dict(torch.load(WEIGHTS_PATH, map_location=device))
    backbone.to(device)
    backbone.eval()
    return backbone


def predict_prob(model, device, crop_bgr):
    import cv2
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    x = TRANSFORM(img).unsqueeze(0).to(device)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)
    return probs[0, 1].item()  # index 1 = "gunmodel"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python predict_gunmodel_prob.py <engagements_folder> [<folder> ...]")

    if not WEIGHTS_PATH.exists():
        raise SystemExit(f"No trained weights at {WEIGHTS_PATH} -- run train_gunmodel_classifier.py first")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(device)
    head_model = YOLO(HEAD_MODEL_PATH)
    body_model = YOLO(BODY_MODEL_PATH)

    for folder_arg in sys.argv[1:]:
        folder = Path(folder_arg)
        slug = folder.name.removeprefix("engagements_")
        out_path = folder.parent / f"{folder.name}_gunmodel_predictions.csv"
        video = find_video_for_slug(slug)
        if video is None:
            print(f"SKIP {folder}: no matching source video in Downloads")
            continue

        frames = sorted(folder.glob("t*.jpg"))
        print(f"{folder.name}: {len(frames)} frames ({video.name})")

        saved_boxes = load_boxes_from_engagements_csv(folder)
        from_csv = 0

        rows = []
        no_box = 0
        for path in frames:
            m = TIMESTAMP_RE.match(path.name)
            if not m:
                continue
            ts = float(m.group(1))
            frame = extract_frame(video, ts)
            if frame is None:
                continue
            frame_h, frame_w = frame.shape[:2]
            box = saved_boxes.get(path.name)
            if box is not None:
                from_csv += 1
            else:
                box = find_scored_box(frame, head_model, body_model, frame_w, frame_h)
            if box is None:
                no_box += 1
                continue
            crop = padded_crop(frame, box)
            if crop.size == 0:
                no_box += 1
                continue
            prob = predict_prob(model, device, crop)
            rows.append((path.name, prob))

        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["filename", "gunmodel_prob"])
            writer.writerows(rows)

        print(f"  -> {out_path} ({len(rows)} scored, {no_box} skipped/no-box, "
              f"{from_csv} from saved box coords)")


if __name__ == "__main__":
    main()
