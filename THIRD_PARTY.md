# Third-party material

How each dependency is obtained. Game assets that were selected or mixed live in git; upstream binaries do not.

## Downloaded at runtime (not in git)

### MediaPipe Face Landmarker and Pose Landmarker lite

- Publisher: Google
- License: [Apache 2.0](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
- Fetch: `./run.zsh` (pinned `float16/1` URLs + SHA-256)
- Files: `assets/face_landmarker.task`, `assets/pose_landmarker_lite.task` (gitignored)

### Apple.Core 3.2.0 and Apple.PHASE 1.2.7

- Publisher: Apple
- Source: https://github.com/apple/unityplugins (Apache 2.0)
- Nested: xNode (MIT), UnityPickers (MIT)
- Fetch: `unity/fetch-apple-plugins.zsh` builds tarballs from pinned commit `17f601bf68fc9867ee4c4f0f14870ca55f28c798`
- Apple does not attach these `.tgz` files to GitHub Releases; the official install is clone + `build.py`
- Output: `unity/Packages/com.apple.unityplugin.*.tgz` (gitignored)
- Unity then copies native Play Mode libraries into `Assets/Apple Plug-In Support/` (also gitignored)

## In git (project content, with attribution)

These started as CC0 packs but are trimmed, mixed, or subsetted. Re-downloading the upstream zips cannot reproduce the files in this repo.

See `unity/Assets/ForceSense/Art/ATTRIBUTION.txt`.

| Source | License | Used as |
| --- | --- | --- |
| [Kenney Particle Pack](https://kenney.nl/assets/particle-pack) | CC0 1.0 | selected VFX sprites |
| [Kenney Sci-Fi Sounds](https://kenney.nl/assets/sci-fi-sounds) | CC0 1.0 | layered gameplay audio |
| [Kenney Impact Sounds](https://kenney.nl/assets/impact-sounds) | CC0 1.0 | layered BLOCK / HIT transients |
| [Poly Haven metal_plate](https://polyhaven.com/a/metal_plate) | CC0 1.0 | PBR textures |
| [Poly Haven concrete_floor_worn_001](https://polyhaven.com/a/concrete_floor_worn_001) | CC0 1.0 | PBR textures |

## Package manager

Python packages: `requirements.txt`, `requirements-face.txt`, `requirements-imu.txt`.

Unity built-in modules: `unity/Packages/manifest.json` (resolved by Unity Hub).

## Not this repo

Player builds (`.app`, installers) belong on GitHub Releases when you ship one. Do not attach Apple or MediaPipe binaries to Releases.
