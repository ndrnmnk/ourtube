#!/bin/bash

mkdir -p videos;
mkdir -p thumbnails;
sudo apt update;
sudo apt install ffmpeg;
python3 -m venv venv;
venv/bin/pip install -r requirements.txt;
git clone https://github.com/ndrnmnk/deadRTSP;
git apply deadRTSP_video_adjustment.patch;
echo "Ourtube installed successfully! Execute <launch.py> to start it"