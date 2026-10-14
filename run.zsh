#!/bin/zsh
# Face + Pose Landmarker + Arduino IMU saber.
set -euo pipefail

cd "${0:A:h}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
if ! python -c 'import aiohttp, cv2, numpy, mediapipe, pythonosc' 2>/dev/null; then
  python -m pip install -r python-backend/tracker/requirements-face.txt
fi
if [[ "$*" != *"--iphone"* ]] && ! python -c 'import serial' 2>/dev/null; then
  python -m pip install -r python-backend/tracker/requirements-imu.txt
fi
if [[ ! -f phone/touchosc/HearTheUnseen.tosc ]]; then
  python phone/generate_touchosc.py
fi
# Official MediaPipe bundles, versioned path `float16/1` (not `latest`).
fetch_model() {
  local dest="$1" url="$2" sha="$3"
  local tmp="${dest}.tmp"
  if [[ -f "$dest" ]]; then
    if [[ "$(shasum -a 256 "$dest" | awk '{print $1}')" == "$sha" ]]; then
      return
    fi
    print "Checksum mismatch for $dest; re-downloading…"
    rm -f "$dest"
  fi
  print "Downloading $dest…"
  curl --fail --location --retry 3 --output "$tmp" "$url"
  if [[ "$(shasum -a 256 "$tmp" | awk '{print $1}')" != "$sha" ]]; then
    print "error: checksum failed for $dest" >&2
    rm -f "$tmp"
    exit 1
  fi
  mv "$tmp" "$dest"
}

fetch_model \
  assets/face_landmarker.task \
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task' \
  '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'

fetch_model \
  assets/pose_landmarker_lite.task \
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task' \
  '59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a'

export PYTHONPATH="${0:A:h}/python-backend${PYTHONPATH:+:$PYTHONPATH}"
exec python -m tracker.server "$@"
