# Hear the Unseen

Unity 2022.3 project for Hear the Unseen. Tracking stays in Python; this project is the world, Steam Audio binaural, collision, and rounds.

## Run

1. Fetch Steam Audio Unity **4.8.1** (once). Valve publishes this zip on GitHub Releases.

```zsh
chmod +x fetch-steam-audio.zsh
./fetch-steam-audio.zsh
```

This downloads a pinned SHA-256 of `steamaudio_unity_4.8.1.zip` and unpacks `SteamAudio.unitypackage` into `Assets/Plugins/SteamAudio/` (gitignored). Skip this step if that folder is already present.

2. Start tracking from the repo root: `./run.zsh` on macOS, or `powershell -ExecutionPolicy Bypass -File .\run.ps1` on Windows.

```zsh
cd ..
./run.zsh
```

The server prints `Unity pose UDP 127.0.0.1:8766`.

3. Open this folder in **Unity Hub** with editor `2022.3.57f1` (China Hub: `2022.3.57f1c1`).
4. Wait for scripts to compile. Open `Assets/HearTheUnseen/Scenes/HearTheUnseen.unity` and press Play. The scene and prefabs are the world. Play does not build another one.
5. Face the camera, click **Set forward (C)**. Plug in the Arduino saber, then **Set saber reference (S)**.
6. **Start round (Space)**. Lasers spawn from discrete head-relative zones, freeze in world space, and fly at the spawn-time chest.

Wired headphones. Spectator camera looks across the training chamber toward the pad.

## Look

The scene is a dark metallic training chamber (origin still = Mac camera), an emissive energy blade, and a spectator HUD. Materials are Poly Haven CC0 metal/concrete; VFX sprites are Kenney Particle Pack CC0. See `Assets/HearTheUnseen/Art/ATTRIBUTION.txt`. This is Star-Wars-inspired, not licensed Star Wars IP.

## Layout

- Game scripts stay under `Assets/HearTheUnseen/Scripts/`: `App`, `Combat`, `Audio`, `Visual`, `Ui`. Pose receive and apply live in `Assets/PoseLink/`. The listener rig lives in `Assets/BinauralHead/`.
- `HearTheUnseen.unity` is the composed world. `TrainingChamber`, `Head`, `Saber`, `PlayerHurtbox`, and `Projectile` are prefabs. Gameplay references are on `Hear the Unseen` in the Inspector.
- Origin = Mac camera (Y-up after `(x, y, z) → (x, -y, z)`).
- `Head` has the only `AudioListener` plus a `SteamAudioListener`. The saber prefab carries the hum and whoosh loops (`Hum`, `Whoosh/SwingLow`, `SwingMid`, `SwingFast`). `ProjectileTemplate` carries `IncomingFar` and `IncomingNear`. Each is an `AudioSource` plus `SteamAudioSource` with its clip assigned. On Play, rolloff and Steam Audio flags are applied from `Assets/BinauralHead/Resources/SpatialMix.asset`. Block, hit, dodge, and launch one-shots are created at the moment they play.
- Assemblies point one way. `HearTheUnseen` references `PoseLink` and `BinauralHead`. `BinauralHead` references the plugin assembly `SteamAudioUnity`. PoseLink does not reference the game. `PoseSkeletonView` builds its own suit material.
- Layered mono clips live under `Assets/HearTheUnseen/Resources/Audio/{Saber,Projectile,Block,Hit,Dodge}/`.
- Python sends `unity_pose` to UDP `8766`. Unity sends `calibrate_forward`, `calibrate_saber_reference`, `vibrate`, and `set_saber_hand` (`hand`: `left` or `right`) to `8767`. The saber follows the right wrist unless that command or `--saber-hand` says otherwise.

## Steam Audio

Steam Audio Unity `4.8.1` is fetched by `fetch-steam-audio.zsh`, not committed. Audio settings use **Steam Audio Spatializer** and **Steam Audio Ambisonic Decoder**. Third-party inventory: [`../THIRD_PARTY.md`](../THIRD_PARTY.md).

On Play:

- Spectator / Main Camera `AudioListener` is removed if one is still present; `Head` is the only listener
- `Head` already has `AudioListener` + `SteamAudioListener` (`applyReverb = false`)
- Steam Audio is told the listener is the Head transform (`NotifyAudioListenerChangedTo`) — Python head pose is the only listener truth
- saber hum + whoosh are the sources on the saber prefab; incoming is the pair on the projectile prefab; BLOCK / HIT / DODGE one-shots play at the real clash / body / pass-by point
- all gameplay clips are mono; Steam Audio Direct Binaural spatializes them (`spatialize = true`, bilinear HRTF interpolation, no baked stereo / reverb)
- reflections, occlusion, transmission, pathing, air absorption, and perspective correction stay off
- those source flags, the listener reverb switch, and the Unity rolloff live on `Assets/BinauralHead/Resources/SpatialMix.asset`
- distance uses Unity Linear rolloff (`0.25–12 m`); Steam Audio distance attenuation is off so the two do not stack
- incoming gain, brightness, and modulation follow distance to the head, not just rolloff
- whoosh crossfades from IMU `angularSpeedRadS`
- BLOCK haptic fires with the attack transient, not after the tail

Do not enable Steam Audio perspective correction or listener-centric reverb. Head pose from Python is the only listener truth.
