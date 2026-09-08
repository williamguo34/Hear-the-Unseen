/* Browser half of the local latency prototype. No external JavaScript assets. */
const $ = (id) => document.getElementById(id);
const el = {
  audioButton: $("audioButton"), calibrateButton: $("calibrateButton"), thresholdButton: $("thresholdButton"),
  threshold: $("threshold"), thresholdOut: $("thresholdOut"), prediction: $("prediction"), predictionOut: $("predictionOut"), invert: $("invert"),
  notice: $("notice"), tagStatus: $("tagStatus"), margin: $("margin"), yaw: $("yaw"), yawHint: $("yawHint"), fps: $("fps"), detect: $("detect"),
  audioLatency: $("audioLatency"), audioDetail: $("audioDetail"), eventFlash: $("eventFlash"),
  eventTotal: $("eventTotal"), eventDetect: $("eventDetect"), eventTransport: $("eventTransport"), eventAudio: $("eventAudio"),
  trialRows: $("trialRows"), downloadButton: $("downloadButton"), sourceCalibrateButton: $("sourceCalibrateButton"), saberButton: $("saberButton"), saberCalibrateButton: $("saberCalibrateButton"), saberThreshold: $("saberThreshold"), saberThresholdOut: $("saberThresholdOut"), hapticButton: $("hapticButton"),
  saberStatus: $("saberStatus"), saberPose: $("saberPose"), saberRelative: $("saberRelative"), imuStatus: $("imuStatus"), imuDetail: $("imuDetail"),
  imuOmega: $("imuOmega"), saberMotion: $("saberMotion"), saberLatency: $("saberLatency"), hapticTime: $("hapticTime"),
  saberWorldLabel: $("saberWorldLabel"), worldCanvas: $("worldCanvas"),
};

let ws;
let audioCtx, panner, master;
let clockOffsetMs = 0; // server clock = browser performance.now() + offset
let bestSyncRtt = Infinity;
let latestYaw = null, latestServerCaptureMs = null, previousYaw = null, previousCaptureMs = null;
let latestHeadPosition = null;
let thresholdEnabled = false, thresholdArmed = true, trialNumber = 0;
let saberTestArmed = false, saberThresholdArmed = true, saberCenterX = null, latestSaber = null;
const trials = [];
// One-time initial source offset in the displayed/head frame: right + front.
const SOURCE_OFFSET_FROM_HEAD_M = { right: 0.25, front: 0.35 };
let sourceCameraPosition = null;
let clickBuffer = null;
let visualFramePending = false;
let pendingImu, pendingSaber, pendingSerial, pendingPoseUi;
let pendingWorldRedraw = false;

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

function renderPoseUi({ tag, metrics, predicted, angularVelocity }) {
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
  el.yawHint.textContent = Number(el.prediction.value) ? `rendered ${predicted.toFixed(1)}° · ${angularVelocity.toFixed(0)}°/s` : `${angularVelocity.toFixed(0)}°/s`;
  updateWorld(tag, latestSaber);
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);
  ws.onopen = () => { say("Tracker connected. Face the camera, then set forward."); syncClock(); };
  ws.onclose = () => { say("Tracker disconnected; retrying…", true); window.setTimeout(connect, 1000); };
  ws.onerror = () => say("Could not reach the local tracker.", true);
  ws.onmessage = (event) => handle(JSON.parse(event.data));
}

function syncClock() {
  if (ws?.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "sync", t0: performance.now() }));
  window.setTimeout(syncClock, 2000);
}

function handle(message) {
  if (message.type === "server_info") {
    if (message.cameraError) say(message.cameraError, true);
    el.invert.checked = Boolean(message.mirrorCamera);
    updateListener(latestYaw ?? 0, latestHeadPosition);
    redrawWorld();
    return;
  }
  if (message.type === "sync_ack") {
    const t3 = performance.now();
    const rtt = t3 - message.t0;
    // use the least-contended (smallest RTT) exchange, as in simple NTP
    if (rtt <= bestSyncRtt) {
      bestSyncRtt = rtt;
      clockOffsetMs = ((message.serverReceivedMs + message.serverSentMs) / 2) - ((message.t0 + t3) / 2);
    }
    return;
  }
  if (message.type === "notice" || message.type === "error") { say(message.message, !message.ok && message.type !== "notice"); return; }
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
  let predicted = latestYaw ?? 0;
  let angularVelocity = 0;
  if (tag) {
    latestHeadPosition = tag.positionM ?? null;
    const yaw = tag.yawDeg;
    latestYaw = yaw; latestServerCaptureMs = timestamps.capturedMs;
    if (previousYaw !== null && previousCaptureMs !== null) {
      const dt = (timestamps.capturedMs - previousCaptureMs) / 1000;
      if (dt > 0.003 && dt < 0.25) angularVelocity = wrappedDelta(yaw, previousYaw) / dt;
    }
    previousYaw = yaw; previousCaptureMs = timestamps.capturedMs;
    predicted = yaw + angularVelocity * (Number(el.prediction.value) / 1000);
    if (!sourceCameraPosition) setSourceFromHead(latestHeadPosition, yaw);
    updateListener(predicted, latestHeadPosition);
    if (thresholdEnabled && audioCtx) {
      const threshold = Number(el.threshold.value);
      if (yaw < threshold - 5) thresholdArmed = true;
      if (thresholdArmed && yaw >= threshold) {
        thresholdArmed = false;
        triggerTrial(yaw, metrics, timestamps);
      }
    }
  }
  if (saber) {
    handleCameraSaber(saber, metrics, timestamps);
    latestSaber = saber;
  }
  const visual = {
    serial,
    pose: { tag, metrics, predicted, angularVelocity },
    world: true,
  };
  if (saber) visual.saber = saber;
  queueVisualUpdate(visual);
}

function updateSaber(saber) {
  if (!saber) {
    el.saberStatus.textContent = "not visible"; el.saberStatus.className = "warn"; el.saberPose.textContent = "start ZIG SIM, then set saber reference";
    el.saberRelative.textContent = "relative to head —";
    el.saberWorldLabel.textContent = "waiting for iPhone IMU";
    return;
  }
  latestSaber = saber;
  const p = saber.positionM, o = saber.orientation;
  const fromImu = saber.source === "imu" || saber.id === "iphone";
  const fromPose = saber.positionSource === "pose" || saber.positionSource === "pose+imu";
  const coasting = saber.positionSource === "imu";
  const wristLabel = saber.wrist ? `${saber.wrist} wrist` : "wrist";
  el.saberStatus.textContent = fromImu
    ? (fromPose ? `iPhone IMU + ${wristLabel}` : (coasting ? `iPhone IMU coast · ${wristLabel}` : "iPhone IMU"))
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
  const displacementCm = saberCenterX === null ? null : (p.x - saberCenterX) * 100;
  el.saberMotion.textContent = displacementCm === null ? "set center" : `${displacementCm >= 0 ? "+" : ""}${displacementCm.toFixed(1)} cm`;
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
    const orientBit = fromImu ? "iPhone IMU · " : "";
    el.saberWorldLabel.textContent = `${orientBit}${handleBit} · ${saber.bladeReferenceSet ? "reference set" : "set reference"}`;
  } else {
    el.saberWorldLabel.textContent = "waiting for iPhone IMU";
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

function handleCameraSaber(saber, metrics, timestamps) {
  if (!saberTestArmed || !audioCtx || saberCenterX === null) return;
  const displacementCm = (saber.positionM.x - saberCenterX) * 100;
  const thresholdCm = Number(el.saberThreshold.value);
  if (displacementCm < thresholdCm - 2) saberThresholdArmed = true;
  if (!saberThresholdArmed || displacementCm < thresholdCm) return;
  saberThresholdArmed = false;
  updateAudioTelemetry();
  const receivedServerMs = performance.now() + clockOffsetMs;
  const schedulerMs = 0;
  const baseMs = Number(audioCtx.baseLatency || 0) * 1000;
  const outputMs = Number(audioCtx.outputLatency || 0) * 1000;
  const observableMs = Math.max(0, receivedServerMs - timestamps.capturedMs) + schedulerMs + baseMs + outputMs;
  playClick(audioCtx.currentTime);
  el.saberLatency.textContent = fmt(observableMs);
  el.eventFlash.textContent = "SABER CAMERA CLICK"; el.eventFlash.classList.remove("show"); void el.eventFlash.offsetWidth; el.eventFlash.classList.add("show");
  say(`Saber camera click: frame → audio estimate ${observableMs.toFixed(1)} ms (detect ${metrics.detectMs.toFixed(1)} ms). Physical camera-frame age remains excluded.`);
}

function updateSerial(serial) {
  if (!serial) return;
    if (serial.connected) {
    if (el.imuStatus.textContent !== "swinging") {
      el.imuStatus.textContent = serial.app === "zigsim" ? "ZIG SIM" : (serial.source === "iphone" ? "iphone" : "connected");
      el.imuStatus.className = "good";
    }
    if (serial.device && !el.imuDetail.textContent.includes("°/s")) el.imuDetail.textContent = serial.device;
    if (serial.app === "zigsim" && serial.haptic === false) el.hapticTime.textContent = "ZIG SIM cannot vibrate";
  } else if (serial.error) {
    el.imuStatus.textContent = "unavailable"; el.imuStatus.className = "warn"; el.imuDetail.textContent = serial.error;
  } else if (serial.device) {
    el.imuStatus.textContent = "waiting"; el.imuStatus.className = "warn"; el.imuDetail.textContent = serial.device;
  }
}

function updateImu(imu) {
  if (!imu) return;
  el.imuOmega.textContent = `${imu.omegaDegS.toFixed(0)}°/s`;
  el.imuStatus.textContent = imu.poseSource === "quaternion" ? "quaternion" : "attitude";
  el.imuStatus.className = "good";
  el.imuDetail.textContent = `ω ${imu.omegaDegS.toFixed(0)}°/s · ${imu.poseSource === "quaternion" ? "Core Motion quat" : "gyro + gravity"}`;
}

function handleSwing(event) {
  updateImu(event.imu);
  const isBlock = event.type === "block";
  if (event.hapticCommandSentMs != null) el.hapticTime.textContent = event.manual ? "test /vibrate sent" : "command sent";
  else if (isBlock) el.hapticTime.textContent = "no iPhone yet";
  if (event.manual) {
    say(event.hapticCommandSentMs != null ? "Sent /vibrate to TouchOSC. You should feel a short Taptic click." : "No Taptic path yet. Use free ZIG SIM for gyro; TouchOSC is only needed if you want the phone to vibrate.", event.hapticCommandSentMs == null);
    return;
  }
  if (!audioCtx) return;
  updateAudioTelemetry();
  const schedulerMs = 0;
  const baseMs = Number(audioCtx.baseLatency || 0) * 1000;
  const outputMs = Number(audioCtx.outputLatency || 0) * 1000;
  const receivedServerMs = performance.now() + clockOffsetMs;
  const imuToBrowserMs = event.imu ? Math.max(0, receivedServerMs - event.imu.receivedMs) : null;
  playClick(audioCtx.currentTime);
  el.eventFlash.textContent = "SABER BLOCK"; el.eventFlash.classList.remove("show"); void el.eventFlash.offsetWidth; el.eventFlash.classList.add("show");
  say(`iPhone block: gyro threshold → local browser ${imuToBrowserMs != null ? imuToBrowserMs.toFixed(1) : "—"} ms; reported audio ${(schedulerMs + baseMs + outputMs).toFixed(1)} ms.`);
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
    clickBuffer = audioCtx.createBuffer(1, Math.ceil(audioCtx.sampleRate * 0.024), audioCtx.sampleRate);
    const click = clickBuffer.getChannelData(0);
    for (let i = 0; i < click.length; i++) click[i] = (Math.random() * 2 - 1) * Math.exp(-i / (click.length * 0.16));
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

function playClick(when) {
  if (!clickBuffer) return;
  const source = audioCtx.createBufferSource(), gain = audioCtx.createGain();
  source.buffer = clickBuffer; gain.gain.setValueAtTime(0.75, when); source.connect(gain).connect(panner); source.start(when);
}

function triggerTrial(yaw, metrics, timestamps) {
  updateAudioTelemetry();
  const receivedServerMs = performance.now() + clockOffsetMs;
  const transportMs = Math.max(0, receivedServerMs - timestamps.sentMs);
  const detectMs = timestamps.detectedMs - timestamps.capturedMs;
  const schedulerMs = 0;
  const baseMs = Number(audioCtx.baseLatency || 0) * 1000;
  const outputMs = Number(audioCtx.outputLatency || 0) * 1000;
  const audioMs = schedulerMs + baseMs + outputMs;
  const observableMs = Math.max(0, receivedServerMs - timestamps.capturedMs) + audioMs;
  playClick(audioCtx.currentTime);
  el.eventFlash.classList.remove("show"); void el.eventFlash.offsetWidth; el.eventFlash.classList.add("show");
  const trial = { number: ++trialNumber, yaw, detectMs, transportMs, audioMs, observableMs, capturedMs: timestamps.capturedMs, sentMs: timestamps.sentMs, receivedServerMs, baseMs, outputMs, fps: metrics.fps };
  trials.unshift(trial); renderTrials();
  el.eventTotal.textContent = fmt(observableMs); el.eventDetect.textContent = fmt(detectMs); el.eventTransport.textContent = fmt(transportMs); el.eventAudio.textContent = fmt(audioMs);
  say(`Click ${trial.number}: observable software estimate ${observableMs.toFixed(1)} ms. Physical camera frame age is excluded.`);
}

function renderTrials() {
  el.downloadButton.disabled = trials.length === 0;
  el.trialRows.innerHTML = trials.map((t) => `<tr><td>${t.number}</td><td>${t.yaw.toFixed(1)}°</td><td>${fmt(t.detectMs)}</td><td>${fmt(t.transportMs)}</td><td>${fmt(t.audioMs)}</td><td><strong>${fmt(t.observableMs)}</strong></td></tr>`).join("");
}

function downloadCsv() {
  const header = "trial,yaw_deg,frame_to_detect_ms,transport_estimate_ms,audio_scheduler_base_output_ms,observable_frame_to_output_estimate_ms,base_latency_ms,output_latency_ms,fps,captured_server_ms,sent_server_ms,received_server_estimate_ms";
  const lines = trials.slice().reverse().map((t) => [t.number, t.yaw, t.detectMs, t.transportMs, t.audioMs, t.observableMs, t.baseMs, t.outputMs, t.fps, t.capturedMs, t.sentMs, t.receivedServerMs].join(","));
  const url = URL.createObjectURL(new Blob([[header, ...lines].join("\n")], { type: "text/csv" }));
  const a = document.createElement("a"); a.href = url; a.download = `head-audio-trials-${new Date().toISOString().replaceAll(":", "-")}.csv`; a.click(); URL.revokeObjectURL(url);
}

el.audioButton.addEventListener("click", startAudio);
el.calibrateButton.addEventListener("click", () => ws?.send(JSON.stringify({ type: "calibrate" })));
el.thresholdButton.addEventListener("click", () => { thresholdEnabled = !thresholdEnabled; thresholdArmed = true; el.thresholdButton.textContent = `Threshold clicks: ${thresholdEnabled ? "on" : "off"}`; say(thresholdEnabled ? "Threshold clicks enabled. Return below the threshold, then turn right past it." : "Threshold clicks disabled."); });
el.threshold.addEventListener("input", () => el.thresholdOut.textContent = `${el.threshold.value}°`);
el.prediction.addEventListener("input", () => el.predictionOut.textContent = `${el.prediction.value} ms`);
el.downloadButton.addEventListener("click", downloadCsv);
el.sourceCalibrateButton.addEventListener("click", () => {
  if (!setSourceFromHead(latestHeadPosition, latestYaw ?? 0)) { say("Show your face to the camera before setting the source.", true); return; }
  redrawWorld();
  updateAudioSource();
  say("Source reset to the head's displayed right-front, then fixed in the Mac camera frame.");
});
el.saberCalibrateButton.addEventListener("click", () => {
  saberCenterX = latestSaber ? latestSaber.positionM.x : 0;
  saberThresholdArmed = true;
  el.saberMotion.textContent = "0.0 cm";
  ws?.send(JSON.stringify({ type: "calibrate_saber_reference" }));
  say("Saber reference requested from the iPhone IMU. Point the phone as the blade toward the camera.");
});
el.saberButton.addEventListener("click", () => {
  saberTestArmed = !saberTestArmed;
  el.saberButton.textContent = `Saber travel test: ${saberTestArmed ? "armed" : "off"}`;
  el.saberButton.classList.toggle("active", saberTestArmed);
  if (saberTestArmed) say(saberCenterX === null ? "Set saber reference first, then move the wrist through the travel threshold." : "Saber travel test armed. Return below the threshold, then move right through it.");
});
el.saberThreshold.addEventListener("input", () => { el.saberThresholdOut.textContent = `${el.saberThreshold.value} cm`; saberThresholdArmed = true; });
el.hapticButton.addEventListener("click", () => ws?.send(JSON.stringify({ type: "block" })));
el.invert.addEventListener("change", () => {
  ws?.send(JSON.stringify({ type: "mirror_camera", mirrored: el.invert.checked }));
  updateListener(latestYaw ?? 0, latestHeadPosition);
});
document.addEventListener("keydown", (event) => { if (event.key.toLowerCase() === "c" && !event.metaKey && !event.ctrlKey) el.calibrateButton.click(); });
window.setInterval(updateAudioTelemetry, 1000);
bindWorldOrbit();
redrawWorld();
connect();
