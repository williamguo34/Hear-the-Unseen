#!/bin/zsh
# Face + Pose Landmarker + iPhone IMU saber.
set -euo pipefail

cd "${0:A:h}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
mkdir -p "$MPLCONFIGDIR"
if ! python -c 'import aiohttp, cv2, numpy, mediapipe, pythonosc' 2>/dev/null; then
  python -m pip install -r requirements-face.txt
fi
if [[ "$*" == *"--serial"* ]] && ! python -c 'import serial' 2>/dev/null; then
  python -m pip install -r requirements-imu.txt
fi
if [[ ! -f touchosc/LightSaber.tosc ]]; then
  python generate_touchosc.py
fi
if [[ ! -f assets/face_landmarker.task ]]; then
  model_url='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task'
  print "Downloading the official MediaPipe face-landmarker model (once only)…"
  curl --fail --location --retry 3 --output assets/face_landmarker.task.tmp "$model_url"
  mv assets/face_landmarker.task.tmp assets/face_landmarker.task
fi
if [[ ! -f assets/pose_landmarker_lite.task ]]; then
  model_url='https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task'
  print "Downloading the official MediaPipe pose-landmarker lite model (once only)…"
  curl --fail --location --retry 3 --output assets/pose_landmarker_lite.task.tmp "$model_url"
  mv assets/pose_landmarker_lite.task.tmp assets/pose_landmarker_lite.task
fi
exec python server.py "$@"
