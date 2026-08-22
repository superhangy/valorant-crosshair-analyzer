# Extract confirmed false-positive frames from demon1_chamber_clean.mp4
# (see false_positives_demon1_chamber.txt) and add them to dataset_head_gray/
# as background images (empty label = no head box), so the head detector
# learns NOT to fire on teammates, gun/viewmodel, and scoreboard-portrait
# regions. Grayscale-converted to match the rest of dataset_head_gray/
# (see make_grayscale_dataset.py) - keeps the model color-invariant.

import subprocess
from pathlib import Path

import cv2

FFMPEG = r"C:\Users\alexh\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"
VIDEO = r"C:\Users\alexh\Videos\NVIDIA\Desktop\demon1_chamber_clean.mp4"

DST_IMAGES = Path("dataset_head_gray/train/images")
DST_LABELS = Path("dataset_head_gray/train/labels")
TMP = Path("hardneg_tmp.jpg")

# categorized per false_positives_demon1_chamber.txt - only categories where
# the box is on something that isn't a head at all, or shouldn't be trained
# as one (per user request: teammates, guns, maps/scoreboard-UI)
TEAMMATE_AS_TARGET = [
    8.03, 88.13, 136.10, 137.37, 140.17, 451.07, 497.14, 551.01, 553.61,
    555.67, 557.44, 559.34, 561.04, 727.38, 728.11, 873.88, 877.25, 879.28,
    880.11, 881.25, 883.51, 938.58, 1023.25, 1024.78, 1029.15, 1350.12,
    1351.19, 1352.89, 1425.19,
]
GUN_VIEWMODEL_AS_HEAD = [752.48, 664.21, 789.54]
SCOREBOARD_PORTRAIT_AS_HEAD = [181.54, 705.38, 904.81]

ALL_TIMESTAMPS = (
    [("teammate", t) for t in TEAMMATE_AS_TARGET]
    + [("gun", t) for t in GUN_VIEWMODEL_AS_HEAD]
    + [("scoreboard", t) for t in SCOREBOARD_PORTRAIT_AS_HEAD]
)


def extract_frame(timestamp: float) -> "cv2.Mat | None":
    TMP.unlink(missing_ok=True)
    subprocess.run(
        [
            FFMPEG, "-y", "-ss", str(timestamp), "-i", VIDEO,
            "-frames:v", "1", "-q:v", "2", str(TMP),
        ],
        check=True, capture_output=True,
    )
    if not TMP.exists():
        return None
    return cv2.imread(str(TMP))


def main():
    DST_IMAGES.mkdir(parents=True, exist_ok=True)
    DST_LABELS.mkdir(parents=True, exist_ok=True)

    written = 0
    for category, ts in ALL_TIMESTAMPS:
        frame = extract_frame(ts)
        if frame is None:
            print(f"SKIP {category} t{ts:.2f}s - ffmpeg produced no frame")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        name = f"hardneg_demon1_{category}_t{ts:07.2f}s"
        cv2.imwrite(str(DST_IMAGES / f"{name}.jpg"), gray_3ch)
        (DST_LABELS / f"{name}.txt").write_text("")  # empty = background, no head
        written += 1
        print(f"wrote {name}.jpg (background, no box)")

    TMP.unlink(missing_ok=True)
    print(f"\n{written}/{len(ALL_TIMESTAMPS)} hard-negative frames added to {DST_IMAGES}")


if __name__ == "__main__":
    main()
