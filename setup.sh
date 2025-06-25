#!/bin/bash

mkdir -p videos;
mkdir -p thumbnails;
python3 -m venv venv;
venv/bin/pip install -r requirements.txt;
git clone https://github.com/ndrnmnk/deadRTSP;
git -C deadRTSP apply -p1 deadRTSP_video_adjustment.patch;
echo "Ourtube installed successfully! Execute <launch.py> to start it"