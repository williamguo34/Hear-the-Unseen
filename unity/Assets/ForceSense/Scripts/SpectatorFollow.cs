using UnityEngine;

namespace ForceSense
{
    public sealed class SpectatorFollow : MonoBehaviour
    {
        public TrackedHeadController Head;

        [SerializeField] Vector3 localOffset = new Vector3(0.15f, 0.62f, -2.05f);
        [SerializeField] Vector3 lookAhead = new Vector3(0f, -0.15f, 3.4f);
        [SerializeField] float positionSharpness = 8f;
        [SerializeField] float rotationSharpness = 8f;
        [SerializeField] float wallMargin = 0.7f;

        static readonly Vector3 Fallback = new Vector3(0.4f, 0.85f, 3.35f);

        void LateUpdate()
        {
            Vector3 targetPos;
            Vector3 look;
            Vector3 up;
            if (Head != null && Head.IsValid)
            {
                var head = Head.transform;
                targetPos = ClampInsideRoom(head.position + head.rotation * localOffset, wallMargin);
                look = head.position + head.rotation * lookAhead;
                up = head.up;
            }
            else
            {
                targetPos = Fallback;
                look = TrainingChamber.PadCenter + Vector3.up * 1.15f;
                up = Vector3.up;
            }

            if ((look - targetPos).sqrMagnitude < 1e-4f)
                look = targetPos + Vector3.forward;

            var targetRot = Quaternion.LookRotation(look - targetPos, up);
            var dt = Time.deltaTime;
            transform.position = Vector3.Lerp(transform.position, targetPos, 1f - Mathf.Exp(-positionSharpness * dt));
            transform.rotation = Quaternion.Slerp(transform.rotation, targetRot, 1f - Mathf.Exp(-rotationSharpness * dt));
        }

        static Vector3 ClampInsideRoom(Vector3 position, float margin)
        {
            position.x = Mathf.Clamp(position.x, -TrainingChamber.HalfWidth + margin, TrainingChamber.HalfWidth - margin);
            position.y = Mathf.Clamp(position.y, TrainingChamber.FloorY + 0.45f, TrainingChamber.FloorY + TrainingChamber.Height - 0.35f);
            position.z = Mathf.Clamp(position.z, TrainingChamber.ZNear + margin, TrainingChamber.ZFar - margin);
            return position;
        }
    }
}
