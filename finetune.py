# Fine-tune the pretrained YOLOv8n (trained on COCO photos) further on the
# Valorant-specific "enemies" dataset, using the local GPU. This is transfer
# learning: we don't start from scratch, we nudge yolov8n.pt's existing
# weights toward Valorant's specific look.

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="dataset/data.yaml",
        epochs=50,
        imgsz=640,
        batch=16,
        device=0,          # GPU 0 (the RTX 4070)
        project="runs",
        name="valorant_enemy_v1",
    )


# Windows starts DataLoader worker processes by re-importing this file, so
# the training call must be guarded like this or it crashes on startup.
if __name__ == "__main__":
    main()
