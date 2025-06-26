#!/bin/bash

mkdir -p videos;
mkdir -p thumbnails;
python3 -m venv venv;
venv/bin/pip install -r requirements.txt;
git clone https://github.com/ndrnmnk/deadRTSP;
mv deadRTSP_video_adjustment.patch deadRTSP/;
cd deadRTSP;
git apply deadRTSP_video_adjustment.patch;
cd ..;
echo "Ourtube installed successfully!"
echo "Run 'source venv/bin/activate && python launch.py' to start it"