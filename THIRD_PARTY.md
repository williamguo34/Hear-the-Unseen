# Third-party material

Code written for this repository is MIT. See [`LICENSE`](LICENSE). Each dependency below keeps its own license.

How each dependency is obtained. Game assets that were selected or mixed live in git; upstream binaries do not.

## Downloaded at runtime (not in git)

### MediaPipe Face Landmarker and Pose Landmarker lite

- Publisher: Google
- License: [Apache 2.0](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
- Fetch: `./run.zsh` (pinned `float16/1` URLs + SHA-256)
- Files: `assets/face_landmarker.task`, `assets/pose_landmarker_lite.task` (gitignored)

### Steam Audio Unity 4.8.1

- Publisher: Valve
- License: [Apache 2.0](https://github.com/ValveSoftware/steam-audio/blob/master/LICENSE)
- Source: https://github.com/ValveSoftware/steam-audio/releases/tag/v4.8.1
- Fetch: `HearTheUnseen-unity-game/fetch-steam-audio.zsh` (pinned `steamaudio_unity_4.8.1.zip` URL + SHA-256)
- Output: `HearTheUnseen-unity-game/Assets/Plugins/SteamAudio/` (gitignored)
- Assemblies already in that unpack: `SteamAudioUnity` (runtime) and `SteamAudioUnityEditor` (editor). `BinauralHead` references `SteamAudioUnity`. Do not add another asmdef beside those two.
- Product use: Direct Binaural only (no reflections, reverb, occlusion, or pathing)

## In git (project content, with attribution)

These started as CC0 packs but are trimmed, mixed, or subsetted. Re-downloading the upstream zips cannot reproduce the files in this repo.

See `HearTheUnseen-unity-game/Assets/HearTheUnseen/Art/ATTRIBUTION.txt`.

| Source | License | Used as |
| --- | --- | --- |
| [Kenney Particle Pack](https://kenney.nl/assets/particle-pack) | CC0 1.0 | selected VFX sprites |
| [Kenney Sci-Fi Sounds](https://kenney.nl/assets/sci-fi-sounds) | CC0 1.0 | layered gameplay audio |
| [Kenney Impact Sounds](https://kenney.nl/assets/impact-sounds) | CC0 1.0 | layered BLOCK transients and player HIT impacts |
| [Poly Haven metal_plate](https://polyhaven.com/a/metal_plate) | CC0 1.0 | PBR textures |
| [Poly Haven concrete_floor_worn_001](https://polyhaven.com/a/concrete_floor_worn_001) | CC0 1.0 | PBR textures |

## Package manager

Python packages: `python-backend/tracker/requirements.txt`, `python-backend/tracker/requirements-face.txt`, `python-backend/tracker/requirements-imu.txt`.

Unity built-in modules: `HearTheUnseen-unity-game/Packages/manifest.json` (resolved by Unity Hub).

## Not this repo

Player builds (`.app`, installers) belong on GitHub Releases when you ship one. Do not attach Steam Audio or MediaPipe binaries to Releases.
