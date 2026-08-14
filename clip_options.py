# Grab one frame from near the end (last 10s) of several candidate clips,
# so we can pick which clip to use just by looking at these previews.

import cv2
import os

CLIPS_DIR = r"C:\Users\alexh\Videos\NVIDIA\Valorant"
CANDIDATES = [
    "Valorant 2026.07.16 - 22.42.31.02.DVR.mp4",
    "Valorant 2026.07.17 - 17.24.05.03.DVR.mp4",
    "Valorant 2025.11.08 - 20.50.52.09.DVR.mp4",
    "Valorant 2025.10.29 - 20.45.10.03.DVR.mp4",
    "Valorant 2026.02.08 - 16.11.27.04.DVR.mp4",
    "Valorant 2026.01.24 - 19.54.27.05.DVR.mp4",
]

for i, name in enumerate(CANDIDATES, start=1):
    path = os.path.join(CLIPS_DIR, name)
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total_frames / fps if fps else 0
    t = max(duration - 5, 0)  # 5s before the end, inside the last 10s
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    success, frame = cap.read()
    if success:
        filename = f"option_{i}.jpg"
        cv2.imwrite(filename, frame)
        print(f"option_{i}.jpg  <-  {name}  (duration {duration:.1f}s, grabbed at {t:.1f}s)")
    else:
        print(f"FAILED to read {name}")
    cap.release()
