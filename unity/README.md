# ForceSense Unity

Unity 2022.3 project for the ForceSense game. Tracking stays in Python; this project is the world, PHASE-ready audio, collision, and rounds.

## Run

1. Build Apple.Core + Apple.PHASE from upstream (once). Apple does not publish these tarballs as Release assets.

```zsh
chmod +x fetch-apple-plugins.zsh
./fetch-apple-plugins.zsh
```

This clones a pinned commit of [apple/unityplugins](https://github.com/apple/unityplugins), runs `build.py`, and writes `Packages/com.apple.unityplugin.*.tgz`. Those files and `Assets/Apple Plug-In Support/` stay gitignored. Skip this step if the two tarballs are already in `Packages/`.

2. Start tracking (same as before):

```zsh
cd ..
./run.zsh
```

The server prints `Unity pose UDP 127.0.0.1:8766`.

3. Open this folder in **Unity Hub** with editor `2022.3.57f1` (China Hub: `2022.3.57f1c1`).
4. Wait for scripts to compile. Play the empty scene — `ForceSenseBootstrap` builds the world at runtime.
5. Optional: menu **ForceSense → Build Scene** to save `Assets/ForceSense/Scenes/ForceSense.unity`.
6. Face the Mac, click **Set forward (C)**. For blocking, start ZIG SIM / TouchOSC, then **Set saber reference (S)**.
7. **Start round (Space)**. Lasers spawn from discrete head-relative zones, freeze in world space, and fly at the spawn-time chest.

Wired headphones. Spectator camera looks across the training chamber toward the pad.

## Look

Runtime build is a dark metallic training chamber (origin still = Mac camera), a hovering training orb, an emissive energy blade, and a spectator HUD. Materials are Poly Haven CC0 metal/concrete; VFX sprites are Kenney Particle Pack CC0. See `Assets/ForceSense/Art/ATTRIBUTION.txt`. This is Star-Wars-inspired, not licensed Star Wars IP.

## Layout

- Origin = Mac camera (Y-up after `(x, y, z) → (x, -y, z)`).
- `Head` has the only `AudioListener`. `PHASEListener` / `PHASESource` are added automatically if `Apple.PHASE` is imported.
- Layered mono clips live under `Assets/ForceSense/Resources/Audio/{Saber,Projectile,Block,Hit,Dodge}/`.
- Python sends `unity_pose` to UDP `8766`. Unity sends `calibrate_forward`, `calibrate_saber_reference`, `vibrate` to `8767`.

## PHASE

Apple.Core `3.2.0` and Apple.PHASE `1.2.7` are local tarballs referenced from `Packages/manifest.json` (`file:com.apple.unityplugin.*.tgz`). They are built by `fetch-apple-plugins.zsh`, not committed. Audio settings use **PHASE Spatializer**. Third-party inventory: [`../THIRD_PARTY.md`](../THIRD_PARTY.md).

On Play:

- `Head` gets the only `AudioListener` and a `PHASEListener`
- automatic head tracking is off
- global reverb preset is `None`
- saber hum + whoosh ride the saber transform; incoming rides the projectile; BLOCK / HIT / DODGE one-shots play at the real clash / body / pass-by point
- all gameplay clips are mono; PHASE spatializes them (`spatialize = true`, no baked stereo / reverb)
- incoming gain, brightness, and modulation follow distance to the head, not just PHASE rolloff
- whoosh crossfades from IMU `angularSpeedRadS`
- BLOCK haptic fires with the attack transient, not after the tail

Do not turn on PHASE automatic head tracking. Head pose from Python is the only listener truth.
