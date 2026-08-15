# Download the labeled Valorant enemy-detection dataset from Roboflow
# (public dataset by syz Bakray: 1,170 images, single "enemies" class).
# The API key lives in .env (gitignored) instead of hardcoded here, so it
# never ends up in the GitHub repo's history.

import os
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()
api_key = os.environ["ROBOFLOW_API_KEY"]

rf = Roboflow(api_key=api_key)
project = rf.workspace("syz-bakray").project("valorant-enemy-detection-m8r8n")
version = project.version(4)
dataset = version.download("yolov8", location="dataset")

print(f"\nDownloaded to: {dataset.location}")
