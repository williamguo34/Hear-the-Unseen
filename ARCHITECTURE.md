# Hear the Unseen

Three cuts of the same system. Hardware is grouped by physical role. Software is the programs in this repo plus the libraries they depend on. Features are grouped by the data they produce.

A Mac or a Windows PC is the host. The camera, the saber electronics, and the headphones all hang off it. An iPhone replaces the saber’s inertial sensing. It is a separate path from the host camera.

## Hardware

| Role | Device | Job | Where |
|---|---|---|---|
| Host | Mac or Windows PC | Runs tracking, Unity, and the diagnostic page. This side of the serial link and the LAN. | `run.zsh`, `run.ps1` |
| Camera | Built-in camera | The only image source for the head and the upper body. Mac FaceTime, or the Windows integrated camera. Asks for 640×480 at 60 fps, and skips Continuity Camera. | `python-backend/mac_camera/` |
| Saber controller | Arduino Uno | I2C master. Serial at 230400 baud. Runs `BLOCK` and `STILL`. | `firmware/saber-board/HearTheUnseen` |
| Six-axis inertial | MPU6500-compatible module | Gyro and accelerometer at 200 Hz, address `0x68`. Firmware identifies it with `WHO_AM_I`. | `IMU,…` frames |
| Magnetometer | QMC5883P, optional | Raw 3-axis at 10 Hz, address `0x2C`. Six-axis streaming continues when it is absent. | `MAG,…` frames |
| Vibration | V919 on D9 | Full-strength pulse for 150 ms on a block. | Receives `BLOCK` |
| Direction button | Switch, D2 to ground | Locks saber direction immediately and pulses the motor. The two-second still window is a different action. | Sends `CALIBRATE` |
| Alternate inertial | iPhone | Replaces the Arduino sensing path. ZIG SIM or TouchOSC, UDP port 8000. | `--iphone` |
| Listening | Wired headphones | Output for both the diagnostic page and the game. | Web Audio / Steam Audio |

The six-axis part is the MPU6500-compatible module in the firmware (same register family as boards often labeled MPU6050). The repo names it MPU6500.

## Software

### Programs in this repo

| Program | Path | Job |
|---|---|---|
| Firmware | `firmware/saber-board/HearTheUnseen` | Sampling, serial frames, vibration, two-second gyro bias |
| Tracker | `python-backend/tracker/` | Wires the camera, vision, IMU, coasting, and pose UDP. `./run.zsh` or `run.ps1` starts `python -m tracker.server`. |
| Diagnostic page | `web/tracker-page/` | Preview, calibration controls, left/right check in the browser, room view |
| Game | `HearTheUnseen-unity-game/Assets/HearTheUnseen` | Training chamber, rounds, collision, game spatial audio |

`run.zsh` (macOS) and `run.ps1` (Windows) are the tracker entry points. Each creates the virtualenv, fetches the Face and Pose models, and starts `python -m tracker.server`.

### Libraries, engine, art, phone apps

Phone apps are installed on the iPhone. Steam Audio is fetched by `HearTheUnseen-unity-game/fetch-steam-audio.zsh` and is kept out of git.

| Job | Dependency | Used for |
|---|---|---|
| Face | MediaPipe Face Landmarker | Head position and orientation |
| Upper body | MediaPipe Pose Landmarker Lite | Wrist, skeleton, short head stand-in when the face is lost |
| Capture and preview | OpenCV | Opens the built-in camera and serves MJPEG |
| Pose math | NumPy | Rotations, complementary filter, magnetometer fit |
| Serial | pyserial | Arduino |
| Phone packets | python-osc | iPhone OSC |
| Local page | aiohttp | Page, WebSocket, and preview on port 8765 |
| Diagnostic spatial audio | Browser Web Audio, HRTF `PannerNode` | Synthetic hum. The listener follows the head. |
| Game spatial audio | Steam Audio Unity 4.8.1 | Head is the only listener. Direct binaural, no reverb. |
| Engine | Unity 2022.3 | HearTheUnseen scene and scripts |
| Surfaces | Poly Haven, CC0 | Metal and concrete |
| Particles | Kenney Particle Pack, CC0 | Hits and blade flashes |
| Phone inertial | ZIG SIM | Gyro, quaternion, and gravity. No vibration return path. |
| Phone inertial and vibration | TouchOSC | The same pose, plus `/vibrate` on port 9000 |

`phone/generate_touchosc.py` rebuilds the TouchOSC layout.

## Features

Each row is a piece of data, from where it is produced to where it is consumed. The upper body is one pose stream with two uses: the wrist locks the handle, and the other joints are drawn for display.

| Module | Output | Produced by | Consumed by |
|---|---|---|---|
| Head pose | Camera-space position, forward, up | Face Landmarker. Set forward stores the zero. | Diagnostic listener, Unity `Head`, projectile aim |
| Upper-body points | Shoulders, elbows, wrists, hips | Pose Landmarker | Wrist locks the handle. `PoseSkeletonView` draws the rest. |
| Handle position | Position in metres, with a source tag | Wrist is the absolute lock. Acceleration coasts across dropped frames. | Unity saber, block test |
| Blade orientation | Blade axis, up, angular speed | Six-axis fusion, optional magnetic heading. Set saber reference stores the zero. | Blade direction, swing loudness |
| Alignment | Forward zero, saber reference, magnetometer fit, gyro bias | Page, Unity HUD, saber button, `.cache` calibration file | Zeros for the four rows above |
| Haptics | One short pulse | Unity sends `vibrate` on a block | Arduino `BLOCK`, or TouchOSC `/vibrate` |
| Diagnostic listening | Synthetic hum in the headphones | Page Web Audio | Left/right check. Separate from the game mix. |
| Game spatial audio | Saber, incoming, block, hit, dodge | Steam Audio. The head is the only listener. | Wired headphones |
| Training round | Projectiles, and block / hit / dodge | `GameDirector`, spawner, collision judge | HUD, one-shot audio, haptics |
| Pose bus | `unity_pose` and four return commands | UDP 8766 out, 8767 in. The page uses a separate WebSocket. | The contract between Python and Unity |

The training chamber (dark room, spectator camera) belongs with the training round. Its origin is the Mac camera. Camera space is Y-down; Unity flips that to Y-up with `(x, -y, z)`.

### Pose bus commands

Python sends `unity_pose` to `127.0.0.1:8766`. The packet carries head, saber, calibration, skeleton, and metrics.

Unity sends these to port `8767`:

- `calibrate_forward`
- `calibrate_saber_reference`
- `vibrate`
- `set_saber_hand` (`left` or `right`)

Alignment is four different actions:

- **Set forward** — face the camera and hold still for two seconds. Stores head yaw zero.
- **Set saber reference** — point the blade at the camera and hold still for two seconds. Stores blade direction.
- **Saber button** — locks blade direction immediately.
- **Sensor fit** — one magnetometer calibration saved under `.cache/`, plus the firmware `STILL` average of two seconds of gyro bias.

## Reusable packages

Each package has a stable input and output, so someone else can take one without the game. Hear the Unseen is the product that wires them together. Its Unity assets stay in `HearTheUnseen-unity-game/Assets/HearTheUnseen/`.

The packages below are separate folders. `python-backend/tracker/server.py` is the process that calls them. Saber policy (blade axis, forward zero, saber reference, handle reach) stays in that process.

```text
firmware/saber-board/          Arduino sketch
phone/touchosc/                layout generator and layout
python-backend/mac_camera/             built-in camera picker
python-backend/vision_pose/            Face and Pose Landmarker
python-backend/imu_attitude/           AHRS and magnetometer fit
python-backend/imu_transport/          serial frames and iPhone OSC
python-backend/inertial_coast/         camera lock plus acceleration coast
python-backend/pose_protocol/          JSON schema and UDP hub
python-backend/tracker/                process that wires the python packages
web/tracker-page/              diagnostic page
HearTheUnseen-unity-game/Assets/PoseLink/         receive pose and drive transforms
HearTheUnseen-unity-game/Assets/BinauralHead/     listener on a tracked head
HearTheUnseen-unity-game/Assets/HearTheUnseen/       the game
```

### Packages

| Package | Takes | Returns | Lives in |
|---|---|---|---|
| `saber-board` | `BLOCK`, `STILL` | `IMU` and `MAG` lines, `CALIBRATE` | `firmware/saber-board/HearTheUnseen/` |
| `touchosc` | `/vibrate` | gyro, quaternion, gravity, `/ping` | `phone/touchosc/`, `phone/generate_touchosc.py` |
| `mac-camera` | a name substring, or nothing | OpenCV index of the built-in camera | `python-backend/mac_camera/` |
| `vision-pose` | one camera frame | head pose, wrist, upper-body points, face-loss cue | `python-backend/vision_pose/` |
| `imu-attitude` | gyro, accel, optional mag | rotation, heading, saved fit | `python-backend/imu_attitude/` |
| `imu-transport` | serial port, or UDP 8000 | the same sample dict either source | `python-backend/imu_transport/` |
| `inertial-coast` | camera point plus linear acceleration | coasted position in metres | `python-backend/inertial_coast/` |
| `pose-protocol` | the pose dict | UDP `unity_pose`; parses the four commands | `python-backend/pose_protocol/` |
| `tracker-page` | WebSocket pose and telemetry | preview, calibration buttons, browser hum | `web/tracker-page/` |
| `PoseLink` | UDP 8766 | head, saber, and skeleton transforms; sends 8767 | `HearTheUnseen-unity-game/Assets/PoseLink/` |
| `BinauralHead` | a head transform | Steam Audio listener and point sources | `HearTheUnseen-unity-game/Assets/BinauralHead/` |

`vision-pose` is one package with two models. Face and pose share the camera, the field of view, and the depth used to unproject landmarks. Opening the camera twice would fight over the Mac built-in.

`imu-transport` speaks two wires and one sample shape. Arduino text frames and iPhone OSC should stay behind that shape so attitude code never imports serial or OSC.

### What each package is for

**saber-board.** A Uno that streams a six-axis sample at 200 Hz and an optional magnetometer at 10 Hz, and pulses a motor. The button message is `CALIBRATE`. Another project can ignore that word.

**touchosc.** A phone layout that sends the same inertial sample and can buzz. ZIG SIM needs no layout; it is documented as an OSC source inside `imu-transport`.

**mac-camera.** Picks the built-in camera and skips Continuity Camera, iPhone, and Desk View. Any Mac webcam tool can use it. It does not run landmarkers.

**vision-pose.** MediaPipe on frames someone else captured. Head output is position, forward, and up in camera metres, plus a spoken cue when the face leaves the frame (`turn_left`, `turn_right`, `turn_back`, `step_closer`). Body output is the wrist and the upper-body joints. The wrist is the handle lock. The other joints are for drawing.

**imu-attitude.** Complementary filter: gyro integrates, gravity holds tilt, magnetometer corrects yaw only. The fit file is hard-iron, soft-iron, and the mount twist. No serial port and no camera.

**imu-transport.** `SerialImuReader` and `OscImuReader`. Both call one ingest function with gyro, accelerometer, and optional gravity or quaternion.

**inertial-coast.** A camera point is the absolute position. Acceleration fills the gaps and short occlusions, then the next camera sample pulls it back. Written for the saber handle. The same loop fits any object that has a vision fix and an IMU.

**pose-protocol.** The contract other people should implement, rather than import the tracker.

- Camera space, Y-down, metres.
- `unity_pose` on UDP 8766: head, saber, calibration, skeleton, metrics.
- Commands on UDP 8767: `calibrate_forward`, `calibrate_saber_reference`, `vibrate`, `set_saber_hand`.
- Unity applies `(x, -y, z)` and does not convert quaternions across that flip.

**PoseLink.** Unity side of that contract. Drop it into a scene that is not HearTheUnseen.

- `PoseContract.cs`
- `CameraSpace.cs`
- `TrackingReceiver.cs`
- `PoseApplicator.cs`
- `TrackedHeadController.cs`
- `TrackedSaberController.cs`
- `PoseSkeletonView.cs`

**BinauralHead.** Listener on a tracked head, sources that follow other transforms. Steam Audio direct binaural, Unity linear rolloff, reflections off. Fetch stays `HearTheUnseen-unity-game/fetch-steam-audio.zsh`.

- `SpatialAudio.cs`
- `SpatialMixSettings.cs`
- `HeadListenerAnchor.cs`
- `Resources/SpatialMix.asset`

Saber hum, incoming whine, and block/hit/dodge clips stay in HearTheUnseen. They are game content played through this rig.

**tracker-page.** Local monitor: MJPEG with overlays, calibration buttons, sensor cards, room view, browser HRTF hum. It is a client of the tracker WebSocket. The page hum is the left/right check. Game audio does not go through it.

**tracker.** The only Python process. It opens the camera, runs `vision-pose`, reads `imu-transport`, runs `imu-attitude` and `inertial-coast`, and publishes `pose-protocol` plus the page socket. `./run.zsh` starts `python -m tracker.server`.

### Stays in HearTheUnseen

These are the game. They are reusable only as the whole training round, not as libraries.

- Combat: `GameDirector`, `Projectile`, `ProjectileSpawner`, `CollisionJudge`, `PlayerHurtbox`
- Place and look: `TrainingChamber`, `VisualTheme`, `CombatVfx`, `SpectatorFollow`
- HUD: `CalibrationHud`, `SciFiHud`
- Game clips and drivers: `AudioBank`, `SaberSoundDriver`, `LaserSoundDriver`, `FeedbackPlayer`, and `Resources/Audio/`, including the face-loss cues under `Resources/Audio/Cue/`. `SciFiHud` plays those cues.
- Composition: `HearTheUnseenSession`, the scene, prefabs, and materials. The scene is the world. Play does not build another one.

`CalibrationHud` calls PoseLink (`CalibrateForward`, `CalibrateSaber`, vibrate, saber hand). The sci-fi widgets stay in the game.

`PoseSkeletonView` builds its own grey suit material. It does not call `VisualTheme`.

## Boundaries

These are the rules the current split follows. A package stays extractable while its public surface is data in and data out, and it does not import the tracker or the game.

Three rules:

- Transport, attitude, vision, and coasting never call each other. The tracker calls them.
- Saber policy stays in the tracker: blade axis (`GY-91` is -Y, iPhone is +Y), forward zero, saber reference, handle reach limit, and the stand-in handle beside the head. Those are this product. The libraries do not know what a saber is.
- Unity dependencies point one way. HearTheUnseen may call PoseLink and BinauralHead. Those two never reference `GameDirector`, the HUD, or game clips.

### Python seams

The readers, attitude, vision, coasting, and the UDP hub are already separate modules. `Tracker` calls them. Names below are the boundary, not a required spelling.

`ImuSample` is the only type that leaves the wire. Both readers construct it and stop.

- `t_ms`, gyro in rad/s, accel in g
- optional raw magnetometer, optional quaternion, optional gravity
- `source`: `arduino` or `osc`

`SerialImuReader` and `OscImuReader` take hooks (`on_sample`, and for the Arduino also the button, the still window, and link status). They do not receive a `Tracker`. `ingest_imu` stays on the tracker and is the sample callback.

`Attitude` takes an `ImuSample` and returns a rotation. `MagnetometerCalibration` stays the fit object it already is: points in, corrected field and mount rotation out. Neither opens a socket.

`VisionPose.detect(frame)` takes one RGB frame plus its time and focal length. It returns a head estimate and a body estimate, or nothing. The head estimate is position, forward, up, quality, and the cue name. The body estimate is the chosen wrist and the upper-body joints. No IMU and no UDP inside this call.

`HandleInertial` takes a camera-frame acceleration and a camera point. `predict` runs on every IMU sample. `correct` runs when a wrist arrives. It returns a position. It does not build a saber.

`pose_protocol` is two pure functions: `build_unity_pose(...) -> dict` and `parse_command(dict) -> command`. `UnityPoseHub` only sends and receives those dicts. The page WebSocket is a second channel owned by the tracker. The diagnostic page speaks that channel. It does not speak `unity_pose`, and the Unity package does not speak the page channel.

The tracker loop is the only place that still knows the whole system:

```text
frame = camera.read()
head, body = vision.detect(frame)
coast.correct(body.wrist)

on each ImuSample:
    rotation = attitude.update(sample)
    coast.predict(accel_in_camera)
    saber = blade_axis(rotation) at coast.position()
    hub.send(build_unity_pose(head, saber, body))
    page.send(telemetry)
```

`blade_axis`, the two-second still, and `vibrate` routing stay in that loop.

### Unity seams

Each script keeps its `.meta`, so the scene still points at the same components. PoseLink, BinauralHead, and the game share the namespace `HearTheUnseen`.

Assembly definitions:

- `PoseLink` references nothing in HearTheUnseen.
- `BinauralHead` references `SteamAudioUnity`, the assembly shipped in the plugin (`Assets/Plugins/SteamAudio/SteamAudioUnity.asmdef`). The editor half is `SteamAudioUnityEditor`. Do not add a second asmdef in those folders.
- `HearTheUnseen` references PoseLink and BinauralHead. `HearTheUnseen.Editor` references those two plus `SteamAudioUnity`.

`TrackedSaberController` and `TrackedHeadController` stay in PoseLink. `CollisionJudge`, `SaberSoundDriver`, and `GameDirector` stay in HearTheUnseen and call them. `SaberSoundDriver` calls `SpatialAudio.ConfigurePointSource`. The clips and the hum logic stay in the game.

Separate git repositories would be a later copy of these folders. They are not required for the seams above.
