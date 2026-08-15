# Download the labeled Valorant head-detection dataset from Roboflow
# (public dataset by Valorant Detection: 2,836 images, single "head" class).
# Same API key as the earlier enemy-body dataset, read from .env.

import os
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()
api_key = os.environ["ROBOFLOW_API_KEY"]

rf = Roboflow(api_key=api_key)
project = rf.workspace("valorant-detection").project("head-detector-tqndi")
version = project.version(1)
dataset = version.download("yolov8", location="dataset_head")

print(f"\nDownloaded to: {dataset.location}")
