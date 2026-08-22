"""
Low-LR fine-tune of the stable v1 head detector on the augmented
dataset_head_gray/ (now includes the real hard-negative frames from
extract_hard_negatives_from_review.py), instead of a full retrain from
scratch.

Why: the v1-2 attempt (full retrain from scratch with 35 hard negatives)
catastrophically overgeneralized "reject head" and lost recall (0/9 on the
validation set vs v1's 7/9). Starting from v1's already-good weights with a
small learning rate and few epochs should nudge the model to reject the new
false-positive patterns without unlearning what it already knows.
"""

from ultralytics import YOLO

BASE_WEIGHTS = "runs/detect/runs/valorant_head_gray_v1/weights/best.pt"


def main():
    model = YOLO(BASE_WEIGHTS)

    model.train(
        data="dataset_head_gray/data.yaml",
        epochs=15,
        imgsz=640,
        batch=16,
        device=0,
        lr0=0.0001,
        project="runs",
        name="valorant_head_gray_v1-3",
    )


if __name__ == "__main__":
    main()
