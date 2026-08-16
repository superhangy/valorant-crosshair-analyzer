# Build a grayscale copy of dataset_head/ so the head detector can be
# retrained without any color information at all - forces it to learn
# shape/contrast cues instead of outline hue, which should make it robust
# to whatever Enemy Highlight Color the player has set.
#
# Images are converted to grayscale then written back out as 3-channel
# (R=G=B) JPEGs, since YOLO expects 3-channel input - this way the model
# architecture doesn't change, only the pixel content. Label files (the
# .txt bounding box files) don't depend on color at all, so they're just
# copied over unchanged.

import shutil
from pathlib import Path

import cv2

SRC = Path("dataset_head")
DST = Path("dataset_head_gray")
SPLITS = ["train", "valid", "test"]


def convert_split(split: str) -> None:
    src_images = SRC / split / "images"
    src_labels = SRC / split / "labels"
    dst_images = DST / split / "images"
    dst_labels = DST / split / "labels"
    dst_images.mkdir(parents=True, exist_ok=True)
    dst_labels.mkdir(parents=True, exist_ok=True)

    image_paths = list(src_images.glob("*.jpg"))
    for i, img_path in enumerate(image_paths):
        color = cv2.imread(str(img_path))
        gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
        gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        cv2.imwrite(str(dst_images / img_path.name), gray_3ch)

        label_path = src_labels / (img_path.stem + ".txt")
        if label_path.exists():
            shutil.copy(label_path, dst_labels / label_path.name)

        if (i + 1) % 200 == 0:
            print(f"{split}: {i + 1}/{len(image_paths)}")

    print(f"{split}: done, {len(image_paths)} images")


def main():
    for split in SPLITS:
        convert_split(split)

    data_yaml = DST / "data.yaml"
    data_yaml.write_text(
        "names:\n"
        "- head\n"
        "nc: 1\n"
        "test: ../test/images\n"
        "train: ../train/images\n"
        "val: ../valid/images\n"
    )
    print(f"wrote {data_yaml}")


if __name__ == "__main__":
    main()
