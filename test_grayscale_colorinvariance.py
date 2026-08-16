# Compare the color-trained head detector vs the grayscale-trained head
# detector on the same 3 real in-game frames, each recorded with a
# different Enemy Highlight Color (Yellow/Deuteranopia, Purple/Tritanopia,
# Red/Default - same bots, same range). Goal: check whether grayscale
# training reduces the spread in detection confidence across colors,
# compared to the color model's spread.

import cv2
from ultralytics import YOLO

FRAMES = {
    "Yellow": "clipB_t016.0s.jpg",
    "Purple": "clipB_t032.0s.jpg",
    "Red": "clipB_t064.0s.jpg",
}

COLOR_WEIGHTS = "runs/detect/runs/valorant_head_v1/weights/best.pt"
GRAY_WEIGHTS = "runs/detect/runs/valorant_head_gray_v1/weights/best.pt"


def best_conf(result):
    if len(result.boxes) == 0:
        return 0, 0.0
    confs = result.boxes.conf.tolist()
    return len(confs), max(confs)


def run_model(name, weights_path, convert_to_gray):
    model = YOLO(weights_path)
    print(f"\n--- {name} ---")
    for color, path in FRAMES.items():
        img = cv2.imread(path)
        if convert_to_gray:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        result = model.predict(img, conf=0.01, verbose=False)[0]
        count, conf = best_conf(result)
        print(f"{color:8s} detections={count:2d} best_conf={conf:.3f}")


def main():
    run_model("Color-trained model, color frames (baseline)", COLOR_WEIGHTS, convert_to_gray=False)
    run_model("Gray-trained model, grayscale frames", GRAY_WEIGHTS, convert_to_gray=True)


if __name__ == "__main__":
    main()
