using UnityEngine;

namespace HearTheUnseen
{
    public enum RoundResult
    {
        None,
        Block,
        Hit,
        Dodge
    }

    public sealed class CollisionJudge : MonoBehaviour
    {
        [SerializeField] float blockRadius = 0.10f;

        public RoundResult Evaluate(Projectile projectile, TrackedSaberController saber, PlayerHurtbox hurtbox)
        {
            if (projectile == null || !projectile.Flying) return RoundResult.None;
            var point = projectile.transform.position;
            if (saber != null && saber.CollisionReady && saber.DistanceToSegment(point) <= blockRadius)
                return RoundResult.Block;
            if (hurtbox != null && hurtbox.Contains(point))
                return RoundResult.Hit;
            if (projectile.ReachedTarget)
                return RoundResult.Hit;
            return RoundResult.None;
        }
    }
}
