using UnityEngine;

namespace HearTheUnseen
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
            IsValid = CameraSpace.Look(transform, forward, up);
        }
    }
}
