/* Local tracker page: headphone listener, pose view, and calibration. */
const $ = (id) => document.getElementById(id);
const el = {
  audioButton: $("audioButton"), calibrateButton: $("calibrateButton"), invert: $("invert"),
  notice: $("notice"), tagStatus: $("tagStatus"), margin: $("margin"), yaw: $("yaw"), yawHint: $("yawHint"), fps: $("fps"), detect: $("detect"),
  audioLatency: $("audioLatency"), audioDetail: $("audioDetail"),
  sourceCalibrateButton: $("sourceCalibrateButton"), saberCalibrateButton: $("saberCalibrateButton"), hapticButton: $("hapticButton"),
  saberStatus: $("saberStatus"), saberPose: $("saberPose"), saberRelative: $("saberRelative"), imuStatus: $("imuStatus"), imuDetail: $("imuDetail"),
  mpuCard: $("mpuCard"), mpuStatus: $("mpuStatus"), mpuDetail: $("mpuDetail"),
  magCard: $("magCard"), magStatus: $("magStatus"), magDetail: $("magDetail"),
  magCalibrationCard: $("magCalibrationCard"), magCalibrationStatus: $("magCalibrationStatus"), magCalibrationDetail: $("magCalibrationDetail"),
  magAlignmentCard: $("magAlignmentCard"), magAlignmentStatus: $("magAlignmentStatus"), magAlignmentDetail: $("magAlignmentDetail"),
  motionCard: $("motionCard"), linearAcceleration: $("linearAcceleration"), gravityVector: $("gravityVector"),
  headingCard: $("headingCard"), magneticHeading: $("magneticHeading"), headingDetail: $("headingDetail"),
  magCalibrateButton: $("magCalibrateButton"),
  saberWorldLabel: $("saberWorldLabel"), worldCanvas: $("worldCanvas"),
};

let ws;
let audioCtx, panner, master;
let latestYaw = null, previousYaw = null, previousCaptureMs = null;
let latestHeadPosition = null;
let latestSaber = null;
// One-time initial source offset in the displayed/head frame: right + front.
const SOURCE_OFFSET_FROM_HEAD_M = { right: 0.25, front: 0.35 };
let sourceCameraPosition = null;
let visualFramePending = false;
let pendingImu, pendingSaber, pendingSerial, pendingPoseUi;
let pendingWorldRedraw = false;
let imuSourceLabel = "IMU";

function say(message, bad = false) { el.notice.textContent = message; el.notice.classList.toggle("bad", bad); }
function fmt(value, digits = 1) { return Number.isFinite(value) ? `${value.toFixed(digits)} ms` : "—"; }
function wrappedDelta(now, before) { return ((now - before + 540) % 360) - 180; }

function queueVisualUpdate(update) {
  if ("imu" in update) pendingImu = update.imu;
  if ("saber" in update) pendingSaber = update.saber;
  if ("serial" in update) pendingSerial = update.serial;
  if ("pose" in update) pendingPoseUi = update.pose;
  pendingWorldRedraw ||= Boolean(update.world);
  if (visualFramePending) return;
  visualFramePending = true;
  requestAnimationFrame(() => {
    visualFramePending = false;
    const imu = pendingImu, saber = pendingSaber, serial = pendingSerial, pose = pendingPoseUi;
    const redraw = pendingWorldRedraw;
    pendingImu = pendingSaber = pendingSerial = pendingPoseUi = undefined;
    pendingWorldRedraw = false;
    if (imu !== undefined) updateImu(imu);
    if (saber !== undefined) updateSaber(saber);
    if (serial !== undefined) updateSerial(serial);
    if (pose !== undefined) renderPoseUi(pose);
    else if (redraw) redrawWorld();
  });
}

function renderPoseUi({ tag, metrics, angularVelocity }) {
  el.fps.textContent = metrics.fps ? `${metrics.fps.toFixed(1)} Hz` : "warming up";
  const skipped = metrics.droppedCaptureFrames ? ` · skipped ${metrics.droppedCaptureFrames}` : "";
  el.detect.textContent = `detect ${fmt(metrics.detectMs)}${skipped}`;
  if (!tag) {
    updateWorld(null, latestSaber);
    el.tagStatus.textContent = "not visible"; el.tagStatus.className = "warn"; el.margin.textContent = "show your face";
    return;
  }
  el.tagStatus.textContent = "Face visible"; el.tagStatus.className = "good";
  el.margin.textContent = `${tag.quality} landmarks`;
  el.yaw.textContent = `${tag.yawDeg.toFixed(1)}°`;
  el.yawHint.textContent = `${angularVelocity.toFixed(0)}°/s`;
  updateWorld(tag, latestSaber);
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);
  ws.onopen = () => { say("Tracker connected. Face the camera, then set forward."); };
  ws.onclose = () => { say("Tracker disconnected; retrying…", true); window.setTimeout(connect, 1000); };
  ws.onerror = () => say("Could not reach the local tracker.", true);
  ws.onmessage = (event) => handle(JSON.parse(event.data));
}

function handle(message) {
  if (message.type === "server_info") {
    if (message.cameraError) say(message.cameraError, true);
    el.invert.checked = Boolean(message.mirrorCamera);
    updateListener(latestYaw ?? 0, latestHeadPosition);
    redrawWorld();
    return;
  }
  if (message.type === "notice" || message.type === "error") { say(message.message, message.ok === false || message.type === "error"); return; }
  if (message.type === "mag_calibration") { updateMagCalibration(message.calibration); return; }
  if (message.type === "sensor_status") {
    queueVisualUpdate({ serial: message.serial });
    return;
  }
  if (message.type === "imu") {
    const visual = { imu: message.imu, world: Boolean(message.saber) };
    if (message.saber) {
      latestSaber = message.saber;
      visual.saber = message.saber;
    }
    queueVisualUpdate(visual);
    return;
  }
  if (message.type === "block") { handleSwing(message); return; }
  if (message.type !== "pose") return;

  const { tag, metrics, timestamps, saber, serial } = message;
  let angularVelocity = 0;
  if (tag) {
    latestHeadPosition = tag.positionM ?? null;
    const yaw = tag.yawDeg;
    latestYaw = yaw;
    if (previousYaw !== null && previousCaptureMs !== null) {
      const dt = (timestamps.capturedMs - previousCaptureMs) / 1000;
      if (dt > 0.003 && dt < 0.25) angularVelocity = wrappedDelta(yaw, previousYaw) / dt;
    }
    previousYaw = yaw; previousCaptureMs = timestamps.capturedMs;
    if (!sourceCameraPosition) setSourceFromHead(latestHeadPosition, yaw);
    updateListener(yaw, latestHeadPosition);
  }
  if (saber) latestSaber = saber;
  const visual = {
    serial,
    pose: { tag, metrics, angularVelocity },
    world: true,
  };
  if (saber) visual.saber = saber;
  queueVisualUpdate(visual);
}

function updateSaber(saber) {
  if (!saber) {
    el.saberStatus.textContent = "not visible"; el.saberStatus.className = "warn"; el.saberPose.textContent = "connect Arduino or ZIG SIM, then set saber reference";
    el.saberRelative.textContent = "relative to head —";
    el.saberWorldLabel.textContent = "waiting for IMU";
    return;
  }
  latestSaber = saber;
  const p = saber.positionM, o = saber.orientation;
  const fromImu = saber.source === "imu" || saber.id === "iphone";
  const fromPose = saber.positionSource === "pose" || saber.positionSource === "pose+imu";
  const coasting = saber.positionSource === "imu";
  const wristLabel = saber.wrist ? `${saber.wrist} wrist` : "wrist";
  el.saberStatus.textContent = fromImu
    ? (fromPose ? `${imuSourceLabel} + ${wristLabel}` : (coasting ? `${imuSourceLabel} coast · ${wristLabel}` : imuSourceLabel))
    : (saber.source === "pose" ? wristLabel : "tracked");
  el.saberStatus.className = "good";
  const origin = fromPose ? `${wristLabel} ` : (coasting ? "IMU coast " : (fromImu ? "handle stand-in " : ""));
  el.saberPose.textContent = `${origin}${p.x >= 0 ? "+" : ""}${p.x.toFixed(2)}, ${p.y >= 0 ? "+" : ""}${p.y.toFixed(2)}, ${p.z >= 0 ? "+" : ""}${p.z.toFixed(2)} m · yaw ${o.yawDeg.toFixed(0)}°`;
  if (saber.relativeToHeadM) {
    const r = saber.relativeToHeadM;
    el.saberRelative.textContent = `head frame: x ${r.x >= 0 ? "+" : ""}${r.x.toFixed(2)} · y ${r.y >= 0 ? "+" : ""}${r.y.toFixed(2)} · z ${r.z >= 0 ? "+" : ""}${r.z.toFixed(2)} m`;
  } else {
    el.saberRelative.textContent = "relative to head unavailable";
  }
}

const BLADE_LENGTH_M = 0.8;
// Look from the room toward the Mac, the same way you face the computer.
const worldView = { yaw: Math.PI, pitch: 0.28, radius: 2.05, look: { x: 0, y: 0.12, z: 0.55 } };
let worldDrag = null;

function vSub(a, b) { return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z }; }
function vAdd(a, b) { return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z }; }
function vScale(a, s) { return { x: a.x * s, y: a.y * s, z: a.z * s }; }
function vDot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
function vCross(a, b) { return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x }; }
function vLen(a) { return Math.hypot(a.x, a.y, a.z); }
function vNorm(a) { const n = vLen(a) || 1; return vScale(a, 1 / n); }

function cameraToYUp(p) {
  return { x: p.x, y: -p.y, z: p.z };
}

function worldEye() {
  const cy = Math.cos(worldView.pitch), sy = Math.sin(worldView.pitch);
  const cz = Math.cos(worldView.yaw), sz = Math.sin(worldView.yaw);
  const r = worldView.radius;
  return {
    x: worldView.look.x + r * cy * sz,
    y: worldView.look.y + r * sy,
    z: worldView.look.z - r * cy * cz,
  };
}

function projectWorld(p, w, h) {
  const eye = worldEye();
  const forward = vNorm(vSub(worldView.look, eye));
  const right = vNorm(vCross({ x: 0, y: 1, z: 0 }, forward));
  const up = vCross(forward, right);
  const rel = vSub(p, eye);
  const cam = { x: vDot(rel, right), y: vDot(rel, up), z: vDot(rel, forward) };
  if (cam.z < 0.08) return null;
  const f = 1.05 * h;
  return { x: w / 2 + (cam.x / cam.z) * f, y: h / 2 - (cam.y / cam.z) * f, z: cam.z };
}

function resizeWorldCanvas() {
  const canvas = el.worldCanvas;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(320, Math.floor(rect.width * dpr));
  const h = Math.max(220, Math.floor(rect.height * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
}

function strokePath(ctx, pts, color, width) {
  const drawn = pts.filter(Boolean);
  if (drawn.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(drawn[0].x, drawn[0].y);
  for (let i = 1; i < drawn.length; i++) ctx.lineTo(drawn[i].x, drawn[i].y);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

function fillDot(ctx, p, r, color) {
  if (!p) return;
  ctx.beginPath();
  ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
}

function labelAt(ctx, p, text, color) {
  if (!p) return;
  ctx.fillStyle = color;
  ctx.font = "600 11px ui-rounded, system-ui, sans-serif";
  ctx.fillText(text, p.x + 8, p.y - 8);
}

function redrawWorld() {
  updateWorld(latestHeadPosition ? { positionM: latestHeadPosition } : null, latestSaber);
}

function updateWorld(head, saber) {
  const canvas = el.worldCanvas;
  if (!canvas) return;
  resizeWorldCanvas();
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const px = (n) => n * dpr;
  const toW = cameraToYUp;
  const proj = (p) => projectWorld(toW(p), w, h);
  ctx.clearRect(0, 0, w, h);
  const grout = ctx.createLinearGradient(0, 0, 0, h);
  grout.addColorStop(0, "#12385a");
  grout.addColorStop(1, "#07121e");
  ctx.fillStyle = grout;
  ctx.fillRect(0, 0, w, h);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  const floorY = 0.45;
  for (let x = -1.2; x <= 1.2 + 1e-6; x += 0.2) {
    strokePath(ctx, [proj({ x, y: floorY, z: 0 }), proj({ x, y: floorY, z: 2.0 })], "rgba(90,140,180,0.18)", px(1));
  }
  for (let z = 0; z <= 2.0 + 1e-6; z += 0.2) {
    strokePath(ctx, [proj({ x: -1.2, y: floorY, z }), proj({ x: 1.2, y: floorY, z })], "rgba(90,140,180,0.18)", px(1));
  }

  strokePath(ctx, [proj({ x: 0, y: 0, z: 0 }), proj({ x: 0.35, y: 0, z: 0 })], "#ff6b6b", px(2));
  strokePath(ctx, [proj({ x: 0, y: 0, z: 0 }), proj({ x: 0, y: -0.35, z: 0 })], "#7dff9a", px(2));
  strokePath(ctx, [proj({ x: 0, y: 0, z: 0 }), proj({ x: 0, y: 0, z: 0.45 })], "#62c6ff", px(2));
  labelAt(ctx, proj({ x: 0.35, y: 0, z: 0 }), "x", "#ff8a8a");
  labelAt(ctx, proj({ x: 0, y: -0.35, z: 0 }), "up", "#9dffb4");
  labelAt(ctx, proj({ x: 0, y: 0, z: 0.45 }), "+z room", "#9de4ff");

  const cam = proj({ x: 0, y: 0, z: 0 });
  fillDot(ctx, cam, px(6), "#9de4ff");
  labelAt(ctx, cam, "Mac camera", "#b9d6e8");
  strokePath(ctx, [
    proj({ x: -0.08, y: -0.05, z: 0.02 }),
    proj({ x: 0.08, y: -0.05, z: 0.02 }),
    proj({ x: 0.14, y: 0.08, z: 0.18 }),
    proj({ x: -0.14, y: 0.08, z: 0.18 }),
    proj({ x: -0.08, y: -0.05, z: 0.02 }),
  ], "rgba(121,217,255,0.7)", px(1.5));

  const sprites = [];
  const source = sourceCameraPosition ?? { x: 0, y: 0, z: 0.05 };
  const sourceP = proj(source);
  if (sourceP) {
    sprites.push({
      z: sourceP.z,
      draw() {
        fillDot(ctx, sourceP, px(7), "#ffee79");
        labelAt(ctx, sourceP, "source", "#ffe27a");
      },
    });
  }

  if (head?.positionM) {
    const hp = proj(head.positionM);
    const yaw = (latestYaw ?? 0) * Math.PI / 180;
    const face = {
      x: head.positionM.x + Math.sin(yaw) * 0.18,
      y: head.positionM.y,
      z: head.positionM.z - Math.cos(yaw) * 0.18,
    };
    const faceP = proj(face);
    if (hp) {
      sprites.push({
        z: hp.z,
        draw() {
          fillDot(ctx, hp, px(10), "#e6f4ff");
          strokePath(ctx, [hp, faceP], "#99f75f", px(3));
          labelAt(ctx, hp, "head", "#d5e7f7");
        },
      });
    }
  }

  if (saber?.positionM && saber.bladeAxis) {
    const handle = saber.positionM;
    const axis = vNorm(saber.bladeAxis);
    const tip = vAdd(handle, vScale(axis, BLADE_LENGTH_M));
    const handleP = proj(handle);
    const tipP = proj(tip);
    const shadowHandle = proj({ x: handle.x, y: floorY, z: handle.z });
    const shadowTip = proj({ x: tip.x, y: floorY, z: tip.z });
    const depth = ((handleP?.z ?? 1) + (tipP?.z ?? 1)) / 2;
    sprites.push({
      z: depth,
      draw() {
        strokePath(ctx, [shadowHandle, shadowTip], "rgba(20,40,60,0.55)", px(10));
        strokePath(ctx, [handleP, tipP], "rgba(24,191,255,0.28)", px(18));
        strokePath(ctx, [handleP, tipP], "rgba(88,229,255,0.85)", px(8));
        strokePath(ctx, [handleP, tipP], "#f5ffff", px(2.4));
        fillDot(ctx, handleP, px(5), "#d9efff");
        labelAt(ctx, handleP, "saber", "#c5f6ff");
      },
    });
    const fromImu = saber.source === "imu" || saber.id === "iphone";
    const fromPose = saber.positionSource === "pose" || saber.positionSource === "pose+imu";
    const coasting = saber.positionSource === "imu";
    const handleBit = fromPose ? "wrist + IMU" : (coasting ? "IMU coast" : (fromImu ? "3D blade" : "saber tracked"));
    const orientBit = fromImu ? `${imuSourceLabel} · ` : "";
    el.saberWorldLabel.textContent = `${orientBit}${handleBit} · ${saber.bladeReferenceSet ? "reference set" : "set reference"}`;
  } else {
    el.saberWorldLabel.textContent = "waiting for IMU";
  }

  sprites.sort((a, b) => b.z - a.z);
  for (const sprite of sprites) sprite.draw();
}

function bindWorldOrbit() {
  const canvas = el.worldCanvas;
  if (!canvas) return;
  canvas.addEventListener("pointerdown", (event) => {
    worldDrag = { x: event.clientX, y: event.clientY, yaw: worldView.yaw, pitch: worldView.pitch };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!worldDrag) return;
    worldView.yaw = worldDrag.yaw + (event.clientX - worldDrag.x) * 0.006;
    worldView.pitch = Math.max(0.08, Math.min(1.15, worldDrag.pitch + (worldDrag.y - event.clientY) * 0.006));
    redrawWorld();
  });
  canvas.addEventListener("pointerup", () => { worldDrag = null; });
  canvas.addEventListener("pointercancel", () => { worldDrag = null; });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    worldView.radius = Math.max(0.85, Math.min(4.6, worldView.radius + event.deltaY * 0.002));
    redrawWorld();
  }, { passive: false });
  window.addEventListener("resize", redrawWorld);
}

function updateSensorCards(serial) {
  const sensors = serial?.sensors;
  el.mpuCard.hidden = el.magCard.hidden = !sensors;
  el.magCalibrationCard.hidden = el.magAlignmentCard.hidden = el.motionCard.hidden = el.headingCard.hidden = !sensors;
  updateMagCalibration(serial?.magCalibration);
  if (!sensors?.mpu.connected) {
    el.linearAcceleration.textContent = el.magneticHeading.textContent = "—";
    el.gravityVector.textContent = "Waiting for fresh data";
    el.headingDetail.textContent = "Waiting for sensor recovery";
  }
  if (!sensors?.mag.connected) {
    el.magneticHeading.textContent = "—";
    el.headingDetail.textContent = "Waiting for valid magnetic field";
  }
  if (!sensors) return;
  const mpu = sensors.mpu, mag = sensors.mag;
  const render = (status, detail, sensor, isMag) => {
    status.className = sensor.connected ? "good" : "warn";
    if (sensor.connected) {
      status.textContent = "Connected";
      detail.textContent = `Live data · ${sensor.ageMs ?? 0} ms ago`;
      if (isMag && !serial.magUsed) detail.textContent += " · Not used for fusion";
    } else if (sensor.state === "unavailable") {
      status.textContent = "Unavailable";
      detail.textContent = "USB serial disconnected · Reconnecting";
    } else if (sensor.state === "paused") {
      status.textContent = "Paused";
      detail.textContent = "MPU recovering · Magnetometer state unconfirmed";
    } else if (sensor.state === "waiting") {
      status.textContent = "Waiting for data";
      detail.textContent = isMag ? "Waiting for magnetic data · Six-axis fusion" : "Waiting for MPU data · Reconnecting";
    } else {
      status.textContent = sensor.state === "stale" ? "Data stale" : "Offline";
      detail.textContent = isMag ? "Disconnected · Retrying · Six-axis fusion continues" : "MPU offline · Reconnecting · Check wiring";
    }
  };
  render(el.mpuStatus, el.mpuDetail, mpu, false);
  render(el.magStatus, el.magDetail, mag, true);
}

const POSE_ZH = [
  "剑身放平，MPU 的 -X 面朝上，停住",
  "剑身放平，MPU 的 +X 面朝上，停住",
  "剑尖竖直朝上，停住",
  "剑尖竖直朝下，停住",
  "剑身放平，MPU 芯片面朝下，停住",
  "剑身放平，MPU 芯片面朝上，停住",
];

function calibrationHint(calibration) {
  const guide = calibration?.guide || {};
  if (guide.stage === "still") return "先完全静止，正在记陀螺零点";
  if (guide.stage === "pose" && Number.isInteger(guide.target)) {
    const pose = POSE_ZH[guide.target] || guide.hint;
    const counts = Array.isArray(guide.counts) ? guide.counts.map((count, index) => `${guide.labels?.[index] || index} ${count}/${guide.required}`).join(" · ") : "";
    return [pose, counts, guide.message].filter(Boolean).join(" · ");
  }
  if (guide.stage === "rotate") {
    const reason = guide.message
      ? "这一轮没有保存：磁场强度不稳定，继续在原地翻滚不会把前面受干扰的数据清掉。"
      : "六个面的计数已经满了，还要补全各个磁场方向。";
    return `${reason} 离开电脑、喇叭和手机后再慢慢翻滚。`;
  }
  if (guide.stage === "save_error") return guide.hint || "检查通过，但文件没有保存";
  if (guide.stage === "saved" || calibration?.fitted) {
    const angle = calibration?.mountAngleDeg;
    return `已保存，以后开机直接用${Number.isFinite(angle) ? ` · 安装角 ${angle.toFixed(1)}°` : ""}`;
  }
  return calibration?.error || "线束按最终位置固定后做一次。结果会保存，之后不用每次重做";
}

function updateMagCalibration(calibration) {
  const collecting = calibration?.state === "collecting";
  const saved = Boolean(calibration?.fitted || calibration?.state === "calibrated");
  el.magCalibrateButton.dataset.collecting = collecting ? "1" : "0";
  el.magCalibrateButton.textContent = collecting ? "Cancel sensor calibration" : (saved ? "Recalibrate sensors" : "Calibrate sensors once");
  el.magCalibrationStatus.textContent = collecting ? "Calibrating" : (saved ? "Saved" : "Not calibrated");
  el.magCalibrationStatus.className = saved && !collecting ? "good" : "warn";
  el.magCalibrationDetail.textContent = calibrationHint(calibration);
  const angle = calibration?.mountAngleDeg;
  el.magAlignmentStatus.textContent = Number.isFinite(angle) ? `${calibration?.mountApproximate ? "Approx. " : ""}${angle.toFixed(1)}°` : "Measuring";
  el.magAlignmentStatus.className = calibration?.mountApproximate ? "warn" : "good";
  el.magAlignmentDetail.textContent = saved
    ? "Saved mounting twist · Magnetic heading uses this calibration"
    : "Fallback twist until the one-time calibration is saved";
  if (!saved && calibration?.error && calibration?.state !== "collecting") el.magAlignmentDetail.textContent += ` · ${calibration.error}`;
}

function updateSerial(serial) {
  if (!serial) return;
  updateSensorCards(serial);
  if (serial.connected) {
    if (el.imuStatus.textContent !== "swinging") {
      el.imuStatus.textContent = serial.app === "zigsim" ? "ZIG SIM" : (serial.source === "iphone" ? "iphone" : (serial.magUsed ? "Nine-axis fusion" : "Six-axis fusion"));
      el.imuStatus.className = "good";
    }
    if (serial.device && !el.imuDetail.textContent.includes("°/s")) el.imuDetail.textContent = serial.device;
  } else if (serial.reconnecting) {
    el.imuStatus.textContent = serial.portConnected ? "MPU offline / reconnecting" : "USB reconnecting";
    el.imuStatus.className = "warn";
    el.imuDetail.textContent = serial.error || "Waiting for fresh IMU data…";
  } else if (serial.error) {
    el.imuStatus.textContent = "unavailable"; el.imuStatus.className = "warn"; el.imuDetail.textContent = serial.error;
  } else if (serial.device) {
    el.imuStatus.textContent = "waiting"; el.imuStatus.className = "warn"; el.imuDetail.textContent = serial.device;
  }
}

function updateImu(imu) {
  if (!imu) return;
  imuSourceLabel = imu.arduino ? "Arduino IMU" : "iPhone IMU";
  el.imuStatus.textContent = imu.arduino ? (imu.magUsed ? "Nine-axis fusion" : "Six-axis fusion") : (imu.poseSource === "quaternion" ? "quaternion" : "attitude");
  el.imuStatus.className = "good";
  const fusion = imu.poseSource === "quaternion" ? "Core Motion quat" : (imu.magUsed ? "gyro + gravity + mag" : "gyro + gravity");
  el.imuDetail.textContent = `ω ${imu.omegaDegS.toFixed(0)}°/s · ${fusion}`;
  if (imu.arduino) {
    updateMagCalibration(imu.magCalibration);
    const vector = (v) => [v.x, v.y, v.z].map(value => value.toFixed(3)).join(", ");
    if (imu.userAcceleration && imu.gravity) {
      el.linearAcceleration.textContent = vector(imu.userAcceleration);
      el.gravityVector.textContent = `Gravity (${vector(imu.gravity)}) · MPU frame · g`;
    }
    const heading = imu.magneticHeadingDeg;
    el.magneticHeading.textContent = Number.isFinite(heading) ? `${heading.toFixed(1)}°` : "—";
    el.headingDetail.textContent = Number.isFinite(heading)
      ? (imu.headingCalibrated ? "Magnetic calibration applied" : "Fixed mount · Approximate heading") + (Number.isFinite(imu.trueHeadingDeg) ? ` · True north ${imu.trueHeadingDeg.toFixed(1)}°` : " · True north needs local declination")
      : !Number.isFinite(imu.magCalibration?.mountAngleDeg)
        ? "Mounting alignment not calibrated · Magnetic fusion disabled"
        : "Field not used for fusion, or MPU +X is nearly vertical";
    if (imu.saturated) el.imuDetail.textContent += " · Sensor range exceeded";
  }
}

function handleSwing(event) {
  if (!event.manual) return;
  say(event.hapticCommandSentMs != null ? "Vibration command sent. You should feel a short pulse." : "No vibration device connected. Use the Arduino board, or TouchOSC on iPhone.", event.hapticCommandSentMs == null);
}

function setParam(param, value) { if (param) param.value = value; }
function displayYaw(yawDeg) { return el.invert.checked ? -yawDeg : yawDeg; }
function setSourceFromHead(headPosition, yawDeg = latestYaw ?? 0) {
  if (!headPosition) return false;
  const radians = displayYaw(yawDeg) * Math.PI / 180;
  const displayDx = SOURCE_OFFSET_FROM_HEAD_M.right * Math.cos(radians) + SOURCE_OFFSET_FROM_HEAD_M.front * Math.sin(radians);
  const displayDz = SOURCE_OFFSET_FROM_HEAD_M.right * Math.sin(radians) - SOURCE_OFFSET_FROM_HEAD_M.front * Math.cos(radians);
  sourceCameraPosition = {
    x: headPosition.x + (el.invert.checked ? -displayDx : displayDx),
    y: headPosition.y,
    z: Math.max(0.05, headPosition.z + displayDz),
  };
  return true;
}
function cameraToAudio(position) {
  // Camera: +x right, +y down, +z forward. Web Audio: +x right, +y up,
  // listener-forward -z. Mirror reflects x to match the selfie preview.
  return { x: el.invert.checked ? -position.x : position.x, y: -position.y, z: position.z };
}
function updateAudioSource() {
  if (!audioCtx || !panner || !sourceCameraPosition) return;
  const source = cameraToAudio(sourceCameraPosition);
  setParam(panner.positionX, source.x); setParam(panner.positionY, source.y); setParam(panner.positionZ, source.z);
}
function updateListener(yawDeg, headPosition) {
  if (!audioCtx || !audioCtx.listener) return;
  const displayedYawDeg = displayYaw(yawDeg);
  const radians = displayedYawDeg * Math.PI / 180;
  const listener = audioCtx.listener;
  setParam(listener.forwardX, Math.sin(radians)); setParam(listener.forwardY, 0); setParam(listener.forwardZ, -Math.cos(radians));
  if (headPosition) {
    const position = cameraToAudio(headPosition);
    setParam(listener.positionX, position.x); setParam(listener.positionY, position.y); setParam(listener.positionZ, position.z);
  }
  updateAudioSource();
}

async function startAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 0 });
    master = audioCtx.createGain(); master.gain.value = 0.34; master.connect(audioCtx.destination);
    panner = audioCtx.createPanner(); panner.panningModel = "HRTF"; panner.distanceModel = "inverse"; panner.refDistance = 1;
    panner.maxDistance = 20; panner.rolloffFactor = 0.45; panner.connect(master);
    // A deliberately original, quiet synthetic hum avoids bundling copyrighted media.
    const osc = audioCtx.createOscillator(), wobble = audioCtx.createOscillator(), wobbleGain = audioCtx.createGain(), humGain = audioCtx.createGain();
    osc.type = "sawtooth"; osc.frequency.value = 93; wobble.frequency.value = 0.65; wobbleGain.gain.value = 11; humGain.gain.value = 0.055;
    wobble.connect(wobbleGain).connect(osc.frequency); osc.connect(humGain).connect(panner); osc.start(); wobble.start();
  }
  await audioCtx.resume();
  el.audioButton.textContent = "Audio running"; el.audioButton.classList.add("active");
  if (!sourceCameraPosition) setSourceFromHead(latestHeadPosition);
  updateAudioTelemetry(); updateListener(latestYaw ?? 0, latestHeadPosition);
  say("Audio is running. The source was initialized right-front of the head, then frozen in the Mac camera frame; face position and yaw now drive the listener.");
}

function updateAudioTelemetry() {
  if (!audioCtx) return;
  const base = Number(audioCtx.baseLatency || 0) * 1000;
  const output = Number(audioCtx.outputLatency || 0) * 1000;
  const total = base + output;
  el.audioLatency.textContent = `${total.toFixed(1)} ms`;
  el.audioLatency.className = total <= 25 ? "good" : "warn";
  el.audioDetail.textContent = `base ${base.toFixed(1)} · output ${output.toFixed(1)} ms`;
}

el.audioButton.addEventListener("click", startAudio);
el.calibrateButton.addEventListener("click", () => {
  ws?.send(JSON.stringify({ type: "calibrate" }));
  say("Keep still for two seconds. Forward is set after that.");
});
el.sourceCalibrateButton.addEventListener("click", () => {
  if (!setSourceFromHead(latestHeadPosition, latestYaw ?? 0)) { say("Show your face to the camera before setting the source.", true); return; }
  redrawWorld();
  updateAudioSource();
  say("Source reset to the head's displayed right-front, then fixed in the Mac camera frame.");
});
el.saberCalibrateButton.addEventListener("click", () => {
  ws?.send(JSON.stringify({ type: "calibrate_saber_reference" }));
  say("Keep the saber still for two seconds. The blade reference is set after that.");
});
el.hapticButton.addEventListener("click", () => ws?.send(JSON.stringify({ type: "block" })));
el.magCalibrateButton.addEventListener("click", () => {
  const action = el.magCalibrateButton.dataset.collecting === "1" ? "cancel" : "start";
  ws?.send(JSON.stringify({ type: "mag_calibration", action }));
  say(action === "start"
    ? "Hold still, then pause on each face and tumble slowly. The calibration is saved once and reused."
    : "Sensor calibration cancelled. The previous saved result stays in use.");
});
el.invert.addEventListener("change", () => {
  ws?.send(JSON.stringify({ type: "mirror_camera", mirrored: el.invert.checked }));
  updateListener(latestYaw ?? 0, latestHeadPosition);
});
document.addEventListener("keydown", (event) => { if (event.key.toLowerCase() === "c" && !event.metaKey && !event.ctrlKey) el.calibrateButton.click(); });
window.setInterval(updateAudioTelemetry, 1000);
bindWorldOrbit();
redrawWorld();
connect();
