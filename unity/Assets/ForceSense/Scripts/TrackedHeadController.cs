using UnityEngine;

namespace ForceSense
{
    public sealed class TrackedHeadController : MonoBehaviour
    {
        public bool IsValid { get; private set; }

        public void Apply(HeadPose head)
        {
            if (head == null || !head.valid || !head.positionCamM.HasLength || !head.forwardCam.HasLength)
            {
                IsValid = false;
                return;
            }
            transform.position = CameraSpace.Vec(head.positionCamM);
            var forward = CameraSpace.Vec(head.forwardCam).normalized;
            var up = head.upCam.HasLength ? CameraSpace.Vec(head.upCam).normalized : Vector3.up;
            if (forward.sqrMagnitude < 1e-6f)
            {
                IsValid = false;
                return;
            }
            if (Mathf.Abs(Vector3.Dot(forward, up)) > 0.98f)
                up = Vector3.up;
            transform.rotation = Quaternion.LookRotation(forward, up);
            IsValid = true;
        }
    }
}
