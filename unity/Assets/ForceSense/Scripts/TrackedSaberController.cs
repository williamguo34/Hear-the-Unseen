using UnityEngine;

namespace ForceSense
{
    public sealed class TrackedSaberController : MonoBehaviour
    {
        public const float BladeLengthM = 0.8f;

        [SerializeField] Transform bladeVisual;
        public bool PoseValid { get; private set; }
        public bool CollisionReady { get; private set; }
        public float AngularSpeedRadS { get; private set; }
        public Vector3 Handle => transform.position;
        public Vector3 BladeAxis { get; private set; } = Vector3.forward;
        public Vector3 Tip => Handle + BladeAxis * BladeLengthM;

        public void Apply(SaberPose saber, CalibrationState calibration)
        {
            if (saber == null || !saber.valid || !saber.handlePositionCamM.HasLength)
            {
                PoseValid = false;
                CollisionReady = false;
                AngularSpeedRadS = 0f;
                return;
            }
            transform.position = CameraSpace.Vec(saber.handlePositionCamM);
            BladeAxis = saber.bladeAxisCam.HasLength
                ? CameraSpace.Vec(saber.bladeAxisCam).normalized
                : Vector3.forward;
            var up = saber.bladeUpCam.HasLength ? CameraSpace.Vec(saber.bladeUpCam).normalized : Vector3.up;
            if (Mathf.Abs(Vector3.Dot(BladeAxis, up)) > 0.98f)
                up = Vector3.up;
            if (BladeAxis.sqrMagnitude > 1e-6f)
                transform.rotation = Quaternion.LookRotation(BladeAxis, up);
            if (bladeVisual != null)
                bladeVisual.localScale = new Vector3(0.03f, 0.03f, BladeLengthM);

            var source = saber.positionSource ?? "";
            PoseValid = true;
            AngularSpeedRadS = saber.angularSpeedRadS;
            CollisionReady = calibration != null
                && calibration.saberReferenceSet
                && source != "stand-in";
        }

        public float DistanceToSegment(Vector3 point)
        {
            var a = Handle;
            var b = Tip;
            var ab = b - a;
            var t = ab.sqrMagnitude < 1e-8f ? 0f : Mathf.Clamp01(Vector3.Dot(point - a, ab) / ab.sqrMagnitude);
            return Vector3.Distance(point, a + ab * t);
        }

        public Vector3 ClosestPoint(Vector3 point)
        {
            var a = Handle;
            var b = Tip;
            var ab = b - a;
            var t = ab.sqrMagnitude < 1e-8f ? 0f : Mathf.Clamp01(Vector3.Dot(point - a, ab) / ab.sqrMagnitude);
            return a + ab * t;
        }
    }
}
