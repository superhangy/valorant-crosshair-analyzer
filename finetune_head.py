# Fine-tune YOLOv8n to detect enemy HEADS specifically (not whole bodies),
# since crosshair-placement analysis needs distance-to-head, not
# distance-to-a-generic-body-box.

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="dataset_head/data.yaml",
        epochs=50,
        imgsz=640,
        batch=16,
        device=0,          # GPU 0 (the RTX 4070)
        project="runs",
        name="valorant_head_v1",
    )


if __name__ == "__main__":
    main()
