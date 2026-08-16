# Fine-tune YOLOv8n on the grayscale copy of the head dataset (see
# make_grayscale_dataset.py). Same setup as finetune_head.py, just pointed
# at dataset_head_gray/ so the model never sees outline color during
# training - the goal is a detector that keys off head shape/contrast
# only, robust to Enemy Highlight Color setting.

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="dataset_head_gray/data.yaml",
        epochs=50,
        imgsz=640,
        batch=16,
        device=0,
        project="runs",
        name="valorant_head_gray_v1",
    )


if __name__ == "__main__":
    main()
