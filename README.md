# LightSaber head → audio + saber tracking prototype

The game itself is the Unity project in [`unity/`](unity/README.md). This folder is the tracking server that Unity consumes.

The Python + `web/` stack remains a feasibility test for tracking and world-lock:

```text
Mac camera → MediaPipe Face Landmarker → head pose → local WebSocket → Web Audio HRTF → headphones
Mac camera → Pose Landmarker wrist + iPhone IMU coast → saber handle
iPhone IMU quaternion / gyro → blade orientation
Python fused pose → UDP 8766 → Unity PHASEListener / game
```

## What is included

- `server.py` — webcam acquisition, Face + Pose Landmarker, iPhone OSC IMU, local WebSocket, and Unity UDP pose.
- `web/` — a no-build browser HRTF renderer, camera preview, 3D World, live diagnostics, prediction comparison, threshold trials, and CSV export.
- `run.zsh` — setup and run script; downloads pinned MediaPipe models.
- `unity/` — ForceSense game. Apple PHASE tarballs are built by `unity/fetch-apple-plugins.zsh`, not stored in git.
- `THIRD_PARTY.md` — where each third-party file comes from.
- `requirements-imu.txt` — optional serial dependency, installed only when `--serial` is used.
- `touchosc/LightSaber.tosc` — iPhone layout: streams gyro/accel over OSC and vibrates on `/vibrate`.
- `generate_touchosc.py` — rebuilds the TouchOSC layout from `touchosc/LightSaber.lua`.
- `arduino/LightSaberImu/LightSaberImu.ino` — optional legacy Uno firmware (MPU6050 + DRV2605L).

## First run

Use **wired headphones** for the first measurement. Then repeat with Bluetooth unchanged as a second condition.

```zsh
chmod +x run.zsh
./run.zsh
```

The first run creates `.venv`, installs the Python packages, and downloads the Face and Pose Landmarker models (`float16/1`, checksummed). Later runs reuse them. Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in Chrome or Safari. macOS may ask Terminal/Python for Camera access; allow it. If the browser asks to start audio, click **Start audio**.

To open the Unity game, first build Apple's plug-ins (once; needs Xcode), then open `unity/` in Unity Hub. See [`unity/README.md`](unity/README.md).

The server matches the Mac built-in camera by name each launch (FaceTime / Built-in / MacBook) and skips Continuity Camera, iPhone, and Desk View. Camera indices change when an iPhone appears, so it does not lock to `0`. Override with `./run.zsh --camera MacBook` or inspect the list with `./run.zsh --list-cameras`. Do **not** use the iPhone as Continuity Camera while it is the saber IMU.

## Test procedure

1. Face the camera and click **Set forward** (or press `C`). This establishes zero yaw.
2. Start the hum. Turn your head left/right. **Mirror display + audio** mirrors the webcam preview and HRTF. World is a room view from behind you looking at the Mac.
3. Try prediction at 0, 30, and 50 ms. The raw (`0 ms`) condition is the truthful tracking baseline; prediction is an optional subjective compensation experiment.
4. Enable **Threshold clicks**, return below the threshold, then turn right through it. Each crossing logs a trial and offers CSV export.
5. Repeat the same steps with Bluetooth headphones; preserve the configuration and label the CSV by headphone condition.

For the cleanest head-to-audio latency run, keep the camera preview but disable wrist Pose inference:

```zsh
./run.zsh --pose-fps 0 --preview-fps 2
```

## Saber tracking

```text
head:   MediaPipe Face Landmarker → yaw → Web Audio listener
handle: Pose Landmarker wrist, IMU-coasted between camera frames
blade:  iPhone Core Motion quaternion / gyro
```

Sit far enough that the Mac camera sees your shoulders and the holding hand. In ZIG SIM enable **GYRO**, **QUATERNION**, and **GRAVITY**. Lay the phone flat, top toward the Mac, then click **Set saber reference**. Lifting the top should raise the blade; the handle follows the wrist and keeps moving from IMU between slow camera frames.

Face tracking is preferable for bare faces and roughly ±60° turns. It is **not** a reliable final solution for a fully opaque blindfold. For the eventual blindfolded game, the robust no-line-of-sight option is a small IMU on the headband/headphones.

The HRTF path uses the same camera frame. On the first valid head pose (or when you click **Set source from head**), it places the virtual source 25 cm to the displayed right and 35 cm ahead of the head, then saves that result in the Mac camera frame. With the default selfie mirror the browser reflects both source/head x and yaw so World and audio stay aligned. Face translation is a monocular estimate, useful for feasibility testing, not centimetre-accurate acoustics.

### Replace the Uno with an iPhone (recommended)

iPhone already has fused Core Motion (gyro + accel, typically 100 Hz) and a Taptic Engine.

**Use free ZIG SIM first.** TouchOSC is paid and only needed later if you want the Mac to trigger Taptic.

1. Install **ZIG SIM** (free, by 1-10). Do **not** buy ZIG SIM PRO yet; gyro is in the free app.
2. Put the Mac and iPhone on the **same Wi-Fi**. The Mac built-in camera is selected automatically.
3. In ZIG SIM settings:
   - DATA DESTINATION: Other App
   - PROTOCOL: UDP
   - IP ADDRESS: the Mac LAN IP printed when `./run.zsh` starts (not `127.0.0.1`)
   - PORT NUMBER: `8000`
   - MESSAGE FORMAT: **OSC** (not JSON)
   - Enable **GYRO**, **QUATERNION**, **GRAVITY**, and ACCEL if listed
   - Message rate: 60 fps if the free app offers it
4. Allow **Local Network** if iOS asks. Keep ZIG SIM in the foreground, then tap Start.
5. Start the Mac side:

```zsh
./run.zsh
```

The terminal prints the Host IP. In the browser, **iPhone IMU** should move from `waiting` to a live °/s reading. ZIG SIM cannot receive `/vibrate`, so there is no Taptic click yet.

If IMU stays on `waiting`, check Wi-Fi, the Host IP, port 8000, OSC (not JSON), that GYRO is enabled, and macOS Firewall for Python/UDP 8000.

Optional later: **TouchOSC** (paid) if you want Mac → Taptic. Open `touchosc/LightSaber.tosc`, Host = Mac IP, Send 8000, Receive 9000, then **Test iPhone haptic**.

### Optional: keep the Uno path

The wired MPU6050 firmware is still in `arduino/LightSaberImu/LightSaberImu.ino` if you need a USB fallback.

```zsh
./run.zsh --serial /dev/cu.usbmodem3101
```

Use `--serial auto` only when the Uno is the sole USB serial device.

## What the number means

The camera panel is a **12 Hz diagnostic preview**. It draws face and pose overlays on the already-captured camera frame. It opens no extra camera and is excluded from the audio pipeline. JPEG work is latest-only, so a slow preview cannot build an encoding queue. To cut debug encoding, run `./run.zsh --preview-fps 2`.

Camera capture continuously replaces a single latest-frame slot. Face tracking consumes only that newest frame and discards intermediate frames when inference falls behind. Pose wrist inference defaults to 12 Hz, runs independently, and never waits in the Face path; `--pose-fps 0` disables it.

The web page reports an **observable software-path estimate**:

```text
latest captured OpenCV frame → Face detect → local WebSocket → browser scheduling → baseLatency + outputLatency
```

Handle motion between camera frames is IMU-coasted and sent on the IMU WebSocket path (~125 Hz), not the camera path.

This estimate **does not** include webcam sensor/ISP age or acoustic earbud delay.

## Interpreting results

| Physical motion-to-sound result | Interpretation for this prototype |
| --- | --- |
| under 30 ms | excellent |
| 30–45 ms | very good |
| 45–60 ms | acceptable for the course game |
| 60–80 ms | usable, consider a small prediction setting |
| over 80 ms | investigate camera buffering or output device before adding Unity |

`baseLatency` and `outputLatency` are browser/device estimates. A displayed `0.0 ms` can mean the browser does not expose the value.

## Deliberate scope limits

- Yaw uses an approximate webcam field of view; it is adequate for responsiveness tests, not metrology.
- Face tracking is intended for roughly ±60° yaw.
- The default HTTP UI listens on `127.0.0.1`. iPhone IMU uses LAN UDP (default port 8000). Camera frames do not leave the Mac.
- The hum and click are generated procedurally in the browser; no copyrighted game audio is included.
