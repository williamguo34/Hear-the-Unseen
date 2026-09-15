using UnityEngine;

namespace ForceSense
{
    public sealed class PlayerHurtbox : MonoBehaviour
    {
        [SerializeField] float radius = 0.22f;
        [SerializeField] float chestDownUnity = 0.30f;

        public Vector3 Center { get; private set; }
        public float Radius => radius;

        public void Follow(Transform head)
        {
            Center = head.position + Vector3.down * chestDownUnity;
            transform.position = Center;
            transform.localScale = Vector3.one * radius * 2f;
        }

        public bool Contains(Vector3 point)
        {
            return Vector3.Distance(point, Center) <= radius;
        }
    }
}
