using UnityEngine;

namespace HearTheUnseen
{
    public sealed class PlayerHurtbox : MonoBehaviour
    {
        [SerializeField] float radius = 0.22f;
        [SerializeField] float chestDownM = 0.30f;

        Vector3 _center;

        public void Follow(Transform head)
        {
            _center = head.position + Vector3.down * chestDownM;
            transform.position = _center;
            transform.localScale = Vector3.one * radius * 2f;
        }

        public bool Contains(Vector3 point)
        {
            return Vector3.Distance(point, _center) <= radius;
        }
    }
}
