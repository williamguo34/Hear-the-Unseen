# ForceSense Unity

Unity 2022.3 project for the ForceSense game. Tracking stays in Python; this project is the world, Steam Audio binaural, collision, and rounds.

## Run

1. Fetch Steam Audio Unity **4.8.1** (once). Valve publishes this zip on GitHub Releases.

```zsh
chmod +x fetch-steam-audio.zsh
./fetch-steam-audio.zsh
```

This downloads a pinned SHA-256 of `steamaudio_unity_4.8.1.zip` and unpacks `SteamAudio.unitypackage` into `Assets/Plugins/SteamAudio/` (gitignored). Skip this step if that folder is already present.

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
- `Head` has the only `AudioListener` plus a `SteamAudioListener`. Incoming, saber, and feedback sources are `AudioSource` + `SteamAudioSource`.
- Layered mono clips live under `Assets/ForceSense/Resources/Audio/{Saber,Projectile,Block,Hit,Dodge}/`.
- Python sends `unity_pose` to UDP `8766`. Unity sends `calibrate_forward`, `calibrate_saber_reference`, `vibrate` to `8767`.

## Steam Audio

Steam Audio Unity `4.8.1` is fetched by `fetch-steam-audio.zsh`, not committed. Audio settings use **Steam Audio Spatializer** and **Steam Audio Ambisonic Decoder**. Third-party inventory: [`../THIRD_PARTY.md`](../THIRD_PARTY.md).

On Play:

- Spectator / Main Camera `AudioListener` is removed immediately; `Head` is the only listener
- `Head` gets `AudioListener` + `SteamAudioListener` (`applyReverb = false`)
- Steam Audio is told the listener is the Head transform (`NotifyAudioListenerChangedTo`) — Python head pose is the only listener truth
- saber hum + whoosh ride the saber transform; incoming rides the projectile; BLOCK / HIT / DODGE one-shots play at the real clash / body / pass-by point
- all gameplay clips are mono; Steam Audio Direct Binaural spatializes them (`spatialize = true`, bilinear HRTF interpolation, no baked stereo / reverb)
- reflections, occlusion, transmission, pathing, air absorption, and perspective correction stay off
- distance uses Unity Linear rolloff (`0.25–12 m`); Steam Audio distance attenuation is off so the two do not stack
- incoming gain, brightness, and modulation follow distance to the head, not just rolloff
- whoosh crossfades from IMU `angularSpeedRadS`
- BLOCK haptic fires with the attack transient, not after the tail

Do not enable Steam Audio perspective correction or listener-centric reverb. Head pose from Python is the only listener truth.
