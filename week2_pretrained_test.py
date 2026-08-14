# WEEK 2: Object detection, step 1 — run an EXISTING pretrained model
# (no training yet) on one frame from a real clip, just to see the
# pipeline work end-to-end: video -> frame -> model -> boxes.
#
# This model (yolov8n.pt) was trained on COCO, a general dataset of everyday
# objects — it knows "person", "car", "dog", etc. It does NOT know "Jett" or
# "Sova". It should still draw a box around any visible enemy/teammate body,
# labeled "person", because a Valorant agent model is still shaped like a
# person. That's the sanity check: if this works, the pipeline (extract
# frame -> feed to model -> get boxes back) is solid, and Week 3 becomes
# "swap in a Valorant-trained model" rather than "build this from scratch."

import cv2
from ultralytics import YOLO

CLIP_PATH = r"C:\Users\alexh\Videos\NVIDIA\Valorant\Valorant 2026.07.17 - 18.28.55.03.DVR.mp4"
SECOND_TO_GRAB = 10  # skip the first 10 seconds (loading/menu screens)

# --- Step 1: pull one frame out of the video with OpenCV ---
cap = cv2.VideoCapture(CLIP_PATH)
cap.set(cv2.CAP_PROP_POS_MSEC, SECOND_TO_GRAB * 1000)
success, frame = cap.read()
cap.release()

if not success:
    raise RuntimeError("Couldn't read a frame from the clip — check the path/time.")

cv2.imwrite("sample_frame.jpg", frame)
print("Saved sample_frame.jpg — open it to see the raw frame we grabbed.")

# --- Step 2: load the pretrained model (auto-downloads yolov8n.pt once) ---
model = YOLO("yolov8n.pt")

# --- Step 3: run detection on that one frame ---
results = model(frame)

# --- Step 4: print what it found, and save an annotated copy ---
result = results[0]
print(f"\nDetections in this frame: {len(result.boxes)}")
for box in result.boxes:
    class_id = int(box.cls[0])
    class_name = model.names[class_id]
    confidence = float(box.conf[0])
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    print(f"  {class_name}  conf={confidence:.2f}  box=({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})")

result.save(filename="sample_frame_annotated.jpg")
print("\nSaved sample_frame_annotated.jpg — open it to see the boxes drawn on.")
