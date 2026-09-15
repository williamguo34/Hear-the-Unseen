using UnityEngine;

namespace ForceSense
{
    public sealed class DebugWorldDraw : MonoBehaviour
    {
        public TrackedHeadController Head;
        public TrackedSaberController Saber;
        public PlayerHurtbox Hurtbox;

        void OnDrawGizmos()
        {
            Gizmos.color = Color.cyan;
            Gizmos.DrawWireSphere(Vector3.zero, 0.04f);
            Gizmos.color = Color.red;
            Gizmos.DrawLine(Vector3.zero, Vector3.right * 0.35f);
            Gizmos.color = Color.green;
            Gizmos.DrawLine(Vector3.zero, Vector3.up * 0.35f);
            Gizmos.color = Color.blue;
            Gizmos.DrawLine(Vector3.zero, Vector3.forward * 0.45f);

            if (Head != null)
            {
                Gizmos.color = Color.white;
                Gizmos.DrawSphere(Head.transform.position, 0.05f);
                Gizmos.color = Color.yellow;
                Gizmos.DrawLine(Head.transform.position, Head.transform.position + Head.transform.forward * 0.25f);
            }
            if (Saber != null)
            {
                Gizmos.color = new Color(0.3f, 0.9f, 1f);
                Gizmos.DrawLine(Saber.Handle, Saber.Tip);
                Gizmos.DrawSphere(Saber.Handle, 0.025f);
            }
            if (Hurtbox != null)
            {
                Gizmos.color = new Color(1f, 0.4f, 0.3f, 0.25f);
                Gizmos.DrawSphere(Hurtbox.Center, Hurtbox.Radius);
            }
        }
    }
}
