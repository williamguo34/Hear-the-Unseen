using UnityEngine;

namespace HearTheUnseen
{
    public sealed class TrackedSaberController : MonoBehaviour
    {
        public const float BladeLengthM = 0.8f;

        public bool PoseValid { get; private set; }
        public bool TrackedHandle { get; private set; }
        public bool CollisionReady { get; private set; }
        public float AngularSpeedRadS { get; private set; }
        public Vector3 Handle => transform.position;
        public Vector3 BladeAxis { get; private set; } = Vector3.forward;
        public Vector3 Tip => Handle + BladeAxis * BladeLengthM;

        public void Apply(SaberPose saber)
        {
            if (saber == null || !saber.valid || !saber.handlePositionCamM.HasLength)
            {
                PoseValid = false;
                TrackedHandle = false;
                CollisionReady = false;
                AngularSpeedRadS = 0f;
                return;
            }
            transform.position = CameraSpace.Vec(saber.handlePositionCamM);
            BladeAxis = saber.bladeAxisCam.HasLength
                ? CameraSpace.Vec(saber.bladeAxisCam).normalized
                : Vector3.forward;
            var up = saber.bladeUpCam.HasLength ? CameraSpace.Vec(saber.bladeUpCam).normalized : Vector3.up;
            CameraSpace.Look(transform, BladeAxis, up);

            var source = saber.positionSource ?? "";
            PoseValid = true;
            AngularSpeedRadS = saber.angularSpeedRadS;
            TrackedHandle = source != "stand-in";
            CollisionReady = TrackedHandle;
        }

        public float DistanceToSegment(Vector3 point)
        {
            return Vector3.Distance(point, ClosestPoint(point));
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
