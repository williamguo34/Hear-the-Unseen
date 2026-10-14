"""Arduino motion outputs and QMC5883P calibration/alignment.

Ellipsoid fitting follows the hard/soft-iron model described in NXP AN5019.
The +/-8 gauss firmware range is 3750 counts/gauss (Adafruit QMC5883P).
Fit residuals measure consistency, not absolute heading accuracy.
"""

import json
import math
from collections import deque
from pathlib import Path

import numpy as np


QMC_UT_PER_COUNT = 100.0 / 3750.0
FALLBACK_MOUNT_DEG = 8.0
MIN_MAG_SAMPLES = 240
CALIBRATION_ID = "qmc5883p-0x2c-8G-sensor-frame-motion-tip-alignment-v4"
MIN_ALIGNMENT_SAMPLES = 120
POSE_SAMPLES = 20
POSE_LABELS = ("-X", "+X", "-Y", "+Y", "-Z", "+Z")
POSE_ORDER = (2, 3, 5, 4, 1, 0)
POSE_HINTS = ("Hold the blade level; turn the MPU -X side upward.",
              "Hold the blade level; turn the MPU +X side upward.",
              "Point the blade tip straight up.", "Point the blade tip straight down.",
              "Hold the blade level; turn the MPU board face down.",
              "Hold the blade level; turn the MPU board face up.")
# Four tip-up headings (chip toward the screen, the user's right, the user's
# left, and back toward the screen): mag Y stayed near -1300 counts, so it is
# the blade axis, and mag X reversed between opposite headings, so it is the
# chip-face axis. mag +Y → MPU -Y (tip), mag +X → MPU +Z (chip face). The
# remaining axis completes a right-handed basis. One twist about that tip axis
# is still unknown.
QMC_TO_MPU_ZERO = np.array([[0., 0., 1.], [0., -1., 0.], [1., 0., 0.]])


def qmc_to_mpu_rotation(angle_deg):
    """Right-hand twist about MPU -Y, composed with the reference basis."""
    angle = math.radians(angle_deg)
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0., -s], [0., 1., 0.], [s, 0., c]]) @ QMC_TO_MPU_ZERO


def fit_accelerometer(points):
    """Fit per-axis bias and gain to stationary 1-g poses, preserving MPU axes."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < MIN_ALIGNMENT_SAMPLES:
        raise ValueError("Need more still samples in all six orientations.")
    training = np.arange(len(points)) % 5 != 0

    def solve(rows):
        origin = rows.mean(axis=0)
        scale = float(np.std(rows))
        if scale < .1:
            raise ValueError("Accelerometer needs more tilted orientations.")
        unit = (rows-origin)/scale
        design = np.column_stack((unit**2, unit))
        coefficients, _, rank, singular = np.linalg.lstsq(design, np.ones(len(rows)), rcond=None)
        diagonal, linear = coefficients[:3], coefficients[3:]
        if rank < 6 or singular[0]/singular[-1] > 1e4 or np.min(diagonal) <= 0:
            raise ValueError("Accelerometer directions are incomplete. Follow the highlighted pose.")
        center = -.5*linear/diagonal
        denominator = 1+np.sum(diagonal*center**2)
        offset = origin+center*scale
        gain = np.sqrt(diagonal/denominator)/scale
        if np.max(np.abs(offset)) > .35 or np.min(gain) < .65 or np.max(gain) > 1.55:
            raise ValueError("Accelerometer bias/gain is outside the supported range. Check the sensor and hold still.")
        return offset, gain

    offset, gain = solve(points[training])
    residual = np.linalg.norm((points[~training]-offset)*gain, axis=1)-1
    rms, p95 = float(np.sqrt(np.mean(residual**2))), float(np.quantile(np.abs(residual), .95))
    if rms > .025 or p95 > .05:
        raise ValueError("Still-pose fit failed. Pause longer in each orientation; do not shake the saber.")
    offset, gain = solve(points)
    return {"accelOffset": offset.tolist(), "accelScale": gain.tolist(),
            "accelFitRmsPercent": rms*100, "accelFitP95Percent": p95*100}


def fit_mount_alignment(corrected_fields, acceleration):
    """Estimate the shared-axis twist from constant magnetic/gravity dot product.

    Input pairs must be near-static and contemporaneous. The local inclination
    is unknown and fitted as the common dot product; yaw is never required.
    This is a constrained alignment fit, not a full accelerometer calibration.
    """
    field = np.asarray(corrected_fields, dtype=float)
    up = np.asarray(acceleration, dtype=float)
    if len(field) < MIN_ALIGNMENT_SAMPLES:
        raise ValueError("Not enough slow, near-static samples for alignment. Rotate slowly and pause in different orientations.")
    if (field.ndim != 2 or field.shape[1] != 3 or up.shape != field.shape
            or not np.all(np.isfinite(field)) or not np.all(np.isfinite(up))):
        raise ValueError("Invalid alignment samples.")
    norms = np.linalg.norm(field, axis=1)
    up_norms = np.linalg.norm(up, axis=1)
    if np.any(norms < 1e-9) or np.any(up_norms < 1e-9):
        raise ValueError("Invalid alignment vectors.")
    field = field / norms[:, None] @ QMC_TO_MPU_ZERO.T
    up = up / up_norms[:, None]
    spread = np.linalg.eigvalsh(np.cov(up.T))
    sectors = 2 * np.argmax(np.abs(up), axis=1) + (up[np.arange(len(up)), np.argmax(np.abs(up), axis=1)] > 0)
    if spread[-1] < .05 or spread[0] / spread[-1] < .04 or np.min(np.bincount(sectors, minlength=6)) < 5:
        raise ValueError("Alignment needs six gravity directions. Tilt the saber up/down, sideways and end over end.")
    # dot(R_tip(theta) @ field, up) = a*cos(theta)+b*sin(theta)+d.
    a = up[:, 0]*field[:, 0] + up[:, 2]*field[:, 2]
    b = -up[:, 0]*field[:, 2] + up[:, 2]*field[:, 0]
    d = up[:, 1]*field[:, 1]
    training = np.arange(len(up)) % 5 != 0

    def solve(mask):
        terms = np.column_stack((a[mask], b[mask], d[mask]))
        terms -= terms.mean(axis=0)
        covariance = terms.T @ terms / len(terms)
        grid = np.linspace(-math.pi, math.pi, 1440, endpoint=False)
        vectors = np.column_stack((np.cos(grid), np.sin(grid), np.ones(len(grid))))
        costs = np.einsum('ni,ij,nj->n', vectors, covariance, vectors)
        index = int(np.argmin(costs))
        angle = float(grid[index])
        # Refine the grid minimum with Newton steps, bounded to its own basin.
        for _ in range(8):
            v = np.array([math.cos(angle), math.sin(angle), 1.])
            dv = np.array([-math.sin(angle), math.cos(angle), 0.])
            ddv = np.array([-math.cos(angle), -math.sin(angle), 0.])
            first = 2*dv @ covariance @ v
            second = 2*(ddv @ covariance @ v + dv @ covariance @ dv)
            if second <= 1e-10:
                break
            step = float(np.clip(first / second, -.01, .01))
            angle -= step
            if abs(step) < 1e-10:
                break
        best = max(0., float(np.array([math.cos(angle), math.sin(angle), 1.]) @ covariance @ np.array([math.cos(angle), math.sin(angle), 1.])))
        distant = np.abs((grid-angle+math.pi) % (2*math.pi)-math.pi) > math.radians(30)
        if math.sqrt(max(0., float(np.min(costs[distant])))) < math.sqrt(best) + .02:
            raise ValueError("Mount angle is ambiguous. Add more tilted orientations and keep the field undisturbed.")
        return angle

    angle = solve(training)
    dots = a*math.cos(angle)+b*math.sin(angle)+d
    residual = dots[~training]-np.mean(dots[training])
    rms, p95 = float(np.sqrt(np.mean(residual**2))), float(np.quantile(np.abs(residual), .95))
    if rms > .035 or p95 > .07:
        raise ValueError("Alignment fit failed. Move slowly, pause in each direction and avoid magnetic interference.")
    full_angle = solve(np.ones(len(up), dtype=bool))
    if abs((full_angle-angle+math.pi) % (2*math.pi)-math.pi) > math.radians(3):
        raise ValueError("Alignment is inconsistent. Collect more slow rotations.")
    return {"mountAngleDeg": (math.degrees(full_angle)+180) % 360-180,
            "alignmentRmsPercent": rms*100, "alignmentP95Percent": p95*100,
            "alignmentSamples": len(up)}


def _fit_ellipsoid(points):
    origin = points.mean(axis=0)
    scale = float(np.sqrt(np.mean((points - origin) ** 2)))
    if scale < 1:
        raise ValueError("Not enough magnetic variation. Slowly rotate the saber around all three axes.")
    x, y, z = ((points - origin) / scale).T
    design = np.column_stack((x*x, y*y, z*z, 2*x*y, 2*x*z, 2*y*z, x, y, z))
    coefficients, _, rank, singular = np.linalg.lstsq(design, np.ones(len(x)), rcond=None)
    if rank < 9 or singular[0] / singular[-1] > 1e4:
        raise ValueError("Not enough orientations. Add end-over-end and sideways rotations.")
    a, b, c, d, e, f, g, h, i = coefficients
    shape = np.array([[a, d, e], [d, b, f], [e, f, c]])
    center = -0.5 * np.linalg.solve(shape, [g, h, i])
    denominator = 1.0 + center @ shape @ center
    if abs(denominator) < 1e-9:
        raise ValueError("Cannot fit the magnetic field. Move away from interference and collect again.")
    eigenvalues, vectors = np.linalg.eigh(shape / denominator)
    if np.min(eigenvalues) <= 0 or np.max(eigenvalues) / np.min(eigenvalues) > 64:
        raise ValueError("Invalid magnetic fit. Move away from metal and magnets and collect again.")
    root = vectors @ np.diag(np.sqrt(eigenvalues)) @ vectors.T
    factor = np.linalg.det(root) ** (1.0 / 3.0)
    return origin + center * scale, root / factor, scale / factor


def fit_magnetometer(points):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise ValueError("Invalid magnetic samples.")
    if len(points) < MIN_MAG_SAMPLES:
        raise ValueError(f"Need at least {MIN_MAG_SAMPLES} magnetic samples; collected {len(points)}.")
    spread = np.linalg.eigvalsh(np.cov(points.T))
    if spread[-1] < 1 or spread[0] / spread[-1] < 0.06:
        raise ValueError("Samples are stationary or nearly planar. Rotate around all three axes.")
    # Deterministic holdout: every fifth reading is excluded from the first fit.
    training = np.arange(len(points)) % 5 != 0
    offset, matrix, radius = _fit_ellipsoid(points[training])
    directions = (points - offset) @ matrix.T / radius
    axes = np.argmax(np.abs(directions), axis=1)
    sectors = 2 * axes + (directions[np.arange(len(points)), axes] > 0)
    if np.min(np.bincount(sectors, minlength=6)) < 10:
        raise ValueError("Not enough coverage. Rotate through all six directions.")
    residual = np.linalg.norm(directions[~training], axis=1) - 1
    rms = float(np.sqrt(np.mean(residual**2)))
    p95 = float(np.quantile(np.abs(residual), 0.95))
    if rms > 0.08 or p95 > 0.15:
        raise ValueError("Magnetic interference is too strong. Move away from magnets, metal and motors and collect again.")
    offset, matrix, radius = _fit_ellipsoid(points)
    return {"id": CALIBRATION_ID, "offset": offset.tolist(), "matrix": matrix.tolist(),
            "radiusCounts": float(radius), "samples": len(points), "fitRmsPercent": rms * 100,
            "fitP95Percent": p95 * 100}


class MagnetometerCalibration:
    def __init__(self, path=None, fixed_mount_angle=None):
        self.path = Path(path) if path is not None else None
        if fixed_mount_angle is not None and not math.isfinite(fixed_mount_angle):
            raise ValueError("Mount twist must be finite.")
        # None uses a saved one-time fit, or FALLBACK_MOUNT_DEG until that fit exists.
        # An explicit angle forces that twist and does not run the guided fit.
        self.forced_mount_angle = fixed_mount_angle
        self.fixed_mount_angle = fixed_mount_angle
        self.fitted = False
        self.model = None
        self.collecting = False
        self.samples = []
        self.pose_pairs = [deque(maxlen=40) for _ in POSE_LABELS]
        self.accel_history = deque(maxlen=5)
        self.auto_save = False
        self.last_attempt_count = 0
        self.current_up = None
        self.current_speed = None
        self.settled = False
        self.completed = False
        self.failure_stage = None
        self.refine_target = None
        self.refine_count = 0
        self.gyro_history = deque(maxlen=20)
        self.gyro_bias = None
        self.previous_gyro_bias = None
        self.last_timestamp = None
        self.error = None
        if self.path is not None and self.path.exists():
            try:
                model = json.loads(self.path.read_text())
                offset = np.asarray(model["offset"], dtype=float)
                matrix = np.asarray(model["matrix"], dtype=float)
                if (model.get("id") != CALIBRATION_ID or offset.shape != (3,) or matrix.shape != (3, 3)
                        or not np.all(np.isfinite(offset)) or not np.all(np.isfinite(matrix))
                        or not np.allclose(matrix, matrix.T) or np.min(np.linalg.eigvalsh(matrix)) <= 0
                        or np.linalg.cond(matrix) > 8 or not np.isclose(np.linalg.det(matrix), 1, atol=0.01)
                        or not math.isfinite(model["radiusCounts"]) or not 1 < model["radiusCounts"] < 32768
                        or not 0 <= model["fitRmsPercent"] <= 8 or not 0 <= model["fitP95Percent"] <= 15
                        or model["samples"] < MIN_MAG_SAMPLES):
                    raise ValueError("invalid model")
                fitted = self._fitted_model(model)
                if fixed_mount_angle is None and fitted:
                    self.model = model
                    self.fitted = True
                    self.fixed_mount_angle = None
                else:
                    # Reuse acceleration coefficients only when independently valid.
                    try:
                        bias = np.asarray(model["accelOffset"], dtype=float)
                        gain = np.asarray(model["accelScale"], dtype=float)
                        valid_accel = (bias.shape == gain.shape == (3,) and np.all(np.isfinite(bias))
                            and np.all(np.isfinite(gain)) and np.max(np.abs(bias)) <= .35
                            and np.min(gain) >= .65 and np.max(gain) <= 1.55
                            and 0 <= model["accelFitRmsPercent"] <= 2.5 and 0 <= model["accelFitP95Percent"] <= 5)
                    except (KeyError, TypeError, ValueError):
                        valid_accel = False
                    if not valid_accel:
                        model.pop("accelOffset", None)
                        model.pop("accelScale", None)
                    self.model = model
                    self.fitted = False
            except (ValueError, KeyError, TypeError, OSError, np.linalg.LinAlgError):
                self.error = ("Saved field correction unavailable; using raw magnetic readings."
                    if fixed_mount_angle is not None else
                    "Saved calibration is incompatible or invalid. Recalibrate once; the result is kept.")
        self._load_still_calibration()

    @staticmethod
    def _fitted_model(model):
        """A one-time factory result has a checked mount angle and accelerometer fit."""
        try:
            if (model.get("id") != CALIBRATION_ID
                    or not math.isfinite(model["mountAngleDeg"]) or not -180 <= model["mountAngleDeg"] <= 180
                    or not 0 <= model["alignmentRmsPercent"] <= 3.5
                    or not 0 <= model["alignmentP95Percent"] <= 7
                    or model["alignmentSamples"] < MIN_ALIGNMENT_SAMPLES):
                return False
            offset = np.asarray(model["accelOffset"], dtype=float)
            gain = np.asarray(model["accelScale"], dtype=float)
            return (offset.shape == gain.shape == (3,) and np.all(np.isfinite(offset))
                    and np.all(np.isfinite(gain)) and np.max(np.abs(offset)) <= .35
                    and np.min(gain) >= .65 and np.max(gain) <= 1.55
                    and 0 <= model["accelFitRmsPercent"] <= 2.5 and 0 <= model["accelFitP95Percent"] <= 5)
        except (KeyError, TypeError, ValueError):
            return False

    def active_mount_angle(self):
        if self.fitted and self.model and "mountAngleDeg" in self.model:
            return float(self.model["mountAngleDeg"])
        if self.forced_mount_angle is not None:
            return float(self.forced_mount_angle)
        if self.fixed_mount_angle is not None:
            return float(self.fixed_mount_angle)
        return FALLBACK_MOUNT_DEG

    def _load_still_calibration(self):
        """Restore the one-time stationary default. It survives reconnect and boot."""
        self.saved_gyro_bias = None
        self.still_accel_offset = None
        self.still_accel_scale = None
        if self.path is None or not self.path.exists():
            return
        try:
            still = json.loads(self.path.read_text()).get("stillCalibration")
            if not isinstance(still, dict):
                return
            gyro = np.asarray(still["gyroBiasRadS"], dtype=float)
            offset = np.asarray(still.get("accelOffset", [0, 0, 0]), dtype=float)
            scale = np.asarray(still.get("accelScale", [1, 1, 1]), dtype=float)
            if (gyro.shape != (3,) or offset.shape != (3,) or scale.shape != (3,)
                    or not np.all(np.isfinite(gyro)) or not np.all(np.isfinite(offset)) or not np.all(np.isfinite(scale))
                    or np.max(np.abs(gyro)) > math.radians(40) or np.max(np.abs(offset)) > .5
                    or np.min(scale) < .65 or np.max(scale) > 1.55):
                return
            self.saved_gyro_bias = gyro
            self.gyro_bias = gyro.copy()
            self.still_accel_offset = offset
            self.still_accel_scale = scale
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return

    def observe_gyro_zero(self, accel, gyro, field):
        """Zero the gyro during a stationary two-second magnetic window."""
        if self.gyro_bias is not None:
            return
        magnitude = float(np.linalg.norm(accel))
        field_norm = float(np.linalg.norm(field))
        if (.55 <= magnitude <= 1.55 and np.linalg.norm(gyro) < math.radians(35)
                and field_norm > 0 and np.all(np.isfinite(gyro)) and np.all(np.isfinite(field))):
            self.gyro_history.append((accel.copy(), gyro.copy(), field/field_norm))
        else:
            self.gyro_history.clear()
        while len(self.gyro_history) > 1:
            a, g, m = (np.array([row[i] for row in self.gyro_history]) for i in range(3))
            if (np.max(np.std(a,axis=0)) < .012 and np.max(np.std(g,axis=0)) < math.radians(.3)
                    and np.max(np.std(m,axis=0)) < .015):
                break
            self.gyro_history.popleft()
        if len(self.gyro_history) == 20:
            self.gyro_bias = np.mean([row[1] for row in self.gyro_history], axis=0)

    def start(self, auto_save=False):
        if self.forced_mount_angle is not None:
            raise ValueError("A fixed mounting angle was requested. Omit --mag-mount-angle to calibrate once.")
        self.collecting = True
        self.samples = []
        self.pose_pairs = [deque(maxlen=40) for _ in POSE_LABELS]
        self.accel_history.clear()
        self.auto_save = auto_save
        self.previous_gyro_bias = None if self.gyro_bias is None else self.gyro_bias.copy()
        self.gyro_bias = None if auto_save else np.zeros(3)
        self.gyro_history.clear()
        self.last_attempt_count = 0
        self.completed = False
        self.settled = False
        self.failure_stage = None
        self.refine_target = None
        self.refine_count = 0
        self.last_timestamp = None
        self.error = None

    def add(self, field, timestamp, acceleration=None, rotation_rate=None):
        if not self.collecting:
            if timestamp != self.last_timestamp and acceleration is not None and rotation_rate is not None:
                self.last_timestamp = timestamp
                accel, gyro, field = (np.asarray(vector, dtype=float) for vector in (acceleration, rotation_rate, field))
                if accel.shape == gyro.shape == field.shape == (3,):
                    self.observe_gyro_zero(accel, gyro, field)
            return False
        if timestamp == self.last_timestamp:
            return False
        self.last_timestamp = timestamp
        field = np.asarray(field, dtype=float)
        if field.shape == (3,) and np.all(np.isfinite(field)) and np.max(np.abs(field)) < 32760:
            if len(self.samples) >= 6000:
                self.samples.pop(0)
                self.last_attempt_count = max(0, self.last_attempt_count-1)
            if len(self.samples) < 6000:
                self.samples.append(field.copy())
                if acceleration is not None and rotation_rate is not None:
                    accel = np.asarray(acceleration, dtype=float)
                    gyro = np.asarray(rotation_rate, dtype=float)
                    if accel.shape == gyro.shape == (3,) and np.all(np.isfinite(accel)) and np.all(np.isfinite(gyro)):
                        magnitude = float(np.linalg.norm(accel))
                        self.observe_gyro_zero(accel, gyro, field)
                        corrected_gyro = gyro if self.gyro_bias is None else gyro-self.gyro_bias
                        self.current_speed = float(np.linalg.norm(corrected_gyro)*180/math.pi)
                        self.current_up = (accel/max(magnitude, 1e-9)).tolist()
                        self.accel_history.append(accel.copy())
                        self.settled = bool(self.gyro_bias is not None and len(self.accel_history) == 5 and self.current_speed <= 12
                            and .55 <= magnitude <= 1.55
                            and np.max(np.std(self.accel_history, axis=0)) < .018)
                        if self.settled:
                            axis = int(np.argmax(np.abs(accel)))
                            if abs(accel[axis])/magnitude >= .85:
                                sector = 2*axis+int(accel[axis] > 0)
                                paired = accel.copy()
                                self.pose_pairs[sector].append((field.copy(), paired))
                                if sector == self.refine_target:
                                    self.refine_count += 1
                                    if self.refine_count >= POSE_SAMPLES:
                                        self.refine_target = (sector+1) % 6
                                        self.refine_count = 0
                counts = [len(pairs) for pairs in self.pose_pairs]
                if (self.auto_save and min(counts) >= POSE_SAMPLES and len(self.samples) >= MIN_MAG_SAMPLES
                        and len(self.samples)-self.last_attempt_count >= 30):
                    self.last_attempt_count = len(self.samples)
                    try:
                        self.finish()
                        return True
                    except ValueError:
                        pass  # Keep collecting and tell the guide what is missing.
        return False

    def finish(self):
        if not self.collecting:
            raise ValueError("Start magnetic calibration first.")
        try:
            self.failure_stage = "magnetic"
            candidate = fit_magnetometer(self.samples)
            pairs = [pair for sector in self.pose_pairs for pair in sector]
            if any(len(sector) < POSE_SAMPLES for sector in self.pose_pairs):
                raise ValueError("Need more still samples in the highlighted orientations.")
            fields = np.asarray([pair[0] for pair in pairs])
            acceleration = np.asarray([pair[1] for pair in pairs])
            self.failure_stage = "acceleration"
            accel_model = fit_accelerometer(acceleration)
            calibrated_accel = (acceleration-accel_model["accelOffset"])*accel_model["accelScale"]
            candidate.update(accel_model)
            corrected = (fields - candidate["offset"]) @ np.asarray(candidate["matrix"]).T
            self.failure_stage = "alignment"
            candidate.update(fit_mount_alignment(corrected, calibrated_accel))
            self.failure_stage = "save"
            self._write_model(candidate)
            self.model = candidate
            self.fitted = True
            self.fixed_mount_angle = None
            self.collecting = False
            self.completed = True
            if self.saved_gyro_bias is not None:
                self.gyro_bias = self.saved_gyro_bias.copy()
                self.previous_gyro_bias = self.gyro_bias.copy()
            else:
                self.previous_gyro_bias = None if self.gyro_bias is None else self.gyro_bias.copy()
            self.error = None
            self.failure_stage = None
        except (ValueError, OSError, np.linalg.LinAlgError) as error:
            self.error = str(error)
            if self.failure_stage in ("acceleration", "alignment") and self.refine_target is None:
                self.refine_target = POSE_ORDER[0]
                self.refine_count = 0
            raise ValueError(self.error) from error

    def cancel(self):
        self.collecting = False
        self.settled = False
        self.samples = []
        self.pose_pairs = [deque(maxlen=40) for _ in POSE_LABELS]
        self.accel_history.clear()
        self.completed = False
        self.failure_stage = None
        self.refine_target = None
        self.gyro_bias = self.previous_gyro_bias
        self.error = None

    def _write_model(self, candidate):
        """Save the one-time fit without dropping the separate still-gyro record."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(candidate)
        if self.path.exists():
            try:
                previous = json.loads(self.path.read_text())
                if isinstance(previous.get("stillCalibration"), dict):
                    data["stillCalibration"] = previous["stillCalibration"]
            except (OSError, json.JSONDecodeError):
                pass
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
        temporary.replace(self.path)

    def apply(self, field):
        field = np.asarray(field, dtype=float)
        if self.model is None:
            return field
        return np.asarray(self.model["matrix"]) @ (field - self.model["offset"])

    def status(self):
        model = self.model or {}
        common = {"gyroReady": self.gyro_bias is not None, "stillSaved": self.saved_gyro_bias is not None,
                  "error": self.error, "fitRmsPercent": model.get("fitRmsPercent")}
        if self.collecting:
            return {**common, "state": "collecting", "calibrated": False, "fitted": False,
                    "fieldCalibrated": self.model is not None, "calibrationRequired": True,
                    "samples": len(self.samples), "minimumSamples": MIN_MAG_SAMPLES,
                    "mountAngleDeg": None, "mountSource": "collecting", "mountApproximate": True,
                    "guide": self.guide()}
        if self.fitted:
            return {**common, "state": "calibrated", "calibrated": True, "fitted": True,
                    "fieldCalibrated": True, "calibrationRequired": False,
                    "samples": model.get("samples", 0), "minimumSamples": MIN_MAG_SAMPLES,
                    "fitP95Percent": model.get("fitP95Percent"),
                    "mountAngleDeg": model.get("mountAngleDeg"), "mountSource": "saved", "mountApproximate": False,
                    "alignmentRmsPercent": model.get("alignmentRmsPercent"),
                    "alignmentSamples": model.get("alignmentSamples", 0),
                    "accelFitRmsPercent": model.get("accelFitRmsPercent"), "guide": self.guide()}
        return {**common, "state": "fixed" if self.forced_mount_angle is not None else "approximate",
                "calibrated": False, "fitted": False, "fieldCalibrated": self.model is not None,
                "calibrationRequired": self.forced_mount_angle is None,
                "mountAngleDeg": self.active_mount_angle(),
                "mountSource": "fixed" if self.forced_mount_angle is not None else "fallback",
                "mountApproximate": True, "guide": {"stage": "idle"}}

    def guide(self):
        counts = [len(pairs) for pairs in self.pose_pairs]
        target = next((i for i in POSE_ORDER if counts[i] < POSE_SAMPLES), None)
        refining = target is None and self.failure_stage in ("acceleration", "alignment")
        if refining:
            target = self.refine_target
        up = None if target is None else [float((target//2 == i)*(1 if target%2 else -1)) for i in range(3)]
        stage = "pose" if target is not None else "rotate"
        if not self.collecting:
            stage = "saved" if self.completed else "idle"
        elif self.gyro_bias is None:
            stage = "still"
            target = None
            up = None
        hint = POSE_HINTS[target] if target is not None else "Slowly roll, tilt and turn end over end to fill magnetic coverage."
        if refining:
            hint = "Turn a quarter turn, then repeat: " + hint
        if self.failure_stage == "save" and self.collecting:
            stage = "save_error"
            hint = "Data checks passed, but the file could not be saved. Check the error below."
        if self.current_speed is not None and self.current_speed > 12 and stage == "pose":
            hint += " Slow down, then hold still."
        if stage == "still":
            hint = "Keep the saber completely still. Gyro zero is measured automatically."
        return {"stage": stage, "target": target, "targetUp": up, "targetLabel": POSE_LABELS[target] if target is not None else None,
                "counts": counts, "labels": list(POSE_LABELS), "required": POSE_SAMPLES,
                "currentUp": self.current_up, "settled": self.settled,
                "hint": hint, "autoSave": self.auto_save,
                "message": self.error, "samples": len(self.samples), "refining": refining,
                "refineCount": self.refine_count, "failureStage": self.failure_stage,
                "stillCount": min(len(self.gyro_history),19) if self.gyro_bias is None else 20,
                "gyroReady": self.gyro_bias is not None}

    def apply_acceleration(self, acceleration):
        model = self.model or {}
        if "accelOffset" in model and "accelScale" in model:
            offset, scale = model["accelOffset"], model["accelScale"]
        else:
            offset = [0, 0, 0] if self.still_accel_offset is None else self.still_accel_offset
            scale = [1, 1, 1] if self.still_accel_scale is None else self.still_accel_scale
        return (np.asarray(acceleration, dtype=float)-offset)*scale

    def apply_rotation_rate(self, rate):
        return np.asarray(rate,dtype=float)-(self.gyro_bias if self.gyro_bias is not None else 0)

    def reset_runtime_gyro(self):
        # Arduino boot clears the firmware bias, so the saved stationary default applies again.
        # A bias learned only during this session does not.
        self.gyro_history.clear()
        self.last_timestamp = None
        if self.saved_gyro_bias is not None:
            self.gyro_bias = self.saved_gyro_bias.copy()
            self.previous_gyro_bias = self.gyro_bias.copy()
        else:
            self.gyro_bias = self.previous_gyro_bias = None

    def suspend_saved_gyro(self):
        """A screen still calibration stores its own firmware bias. Do not subtract the Mac bias as well."""
        self.gyro_history.clear()
        self.last_timestamp = None
        self.gyro_bias = np.zeros(3)
        self.previous_gyro_bias = self.gyro_bias.copy()

    def mount_rotation(self):
        return qmc_to_mpu_rotation(self.active_mount_angle())


def motion_vectors(rotation, acceleration_g):
    """Gravity is Apple-style downward; raw MPU acceleration is specific force.

    An at-rest MPU reads +up, so user acceleration = raw + downward gravity.
    Both output vectors are in MPU device axes and units of g.
    """
    gravity = rotation.T @ np.array([0.0, 0.0, -1.0])
    return gravity, np.asarray(acceleration_g, dtype=float) + gravity


def magnetic_heading(rotation, field, declination=None):
    """Tilt-compensated MPU +X heading clockwise from magnetic north.

    Keep the game's arbitrary yaw reference. A vertical +X axis has no heading.
    East-positive declination gives true north only when supplied by the user.
    """
    field = np.asarray(field, dtype=float)
    if field.shape != (3,) or not np.all(np.isfinite(field)) or np.linalg.norm(field) < 1e-9:
        return None, None
    world_field = rotation @ field
    forward = rotation[:, 0]
    horizontal = float(np.linalg.norm(world_field[:2]))
    if horizontal < 0.1 * float(np.linalg.norm(world_field)) or np.linalg.norm(forward[:2]) < 0.1:
        return None, None
    north_angle = math.atan2(world_field[1], world_field[0])
    forward_angle = math.atan2(forward[1], forward[0])
    heading = math.degrees(north_angle - forward_angle) % 360
    if heading == 360.0:  # Floating remainder can round a tiny negative angle up.
        heading = 0.0
    true = None if declination is None else (heading + declination) % 360
    return heading, true
