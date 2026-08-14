# Helper: pull several frames spread across a clip (or a sub-range of it)
# so we can eyeball them and pick one that actually shows an enemy.

import cv2
import sys

CLIP_PATH = r"C:\Users\alexh\Videos\NVIDIA\Valorant\Valorant 2026.07.16 - 22.42.31.02.DVR.mp4"
START_SEC = float(sys.argv[1]) if len(sys.argv) > 1 else 60
END_SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 100
STEP_SEC = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

cap = cv2.VideoCapture(CLIP_PATH)
print(f"Clip: {CLIP_PATH}")
print(f"Sampling {START_SEC}s to {END_SEC}s every {STEP_SEC}s")

t = START_SEC
while t <= END_SEC:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    success, frame = cap.read()
    if success:
        filename = f"dense_t{t:05.1f}s.jpg"
        cv2.imwrite(filename, frame)
        print(f"  saved {filename}")
    t += STEP_SEC

cap.release()
