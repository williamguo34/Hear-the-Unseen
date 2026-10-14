using UnityEngine;

namespace HearTheUnseen
{
    public sealed class ProjectileSpawner : MonoBehaviour
    {
        public static readonly float[] Azimuths = { -45f, 0f, 45f };
        public static readonly float[] Elevations = { 0f, 30f };

        [SerializeField] float spawnDistanceM = 6f;
        [SerializeField] float chestDownM = 0.30f;
        [SerializeField] float flightSeconds = 2.4f;

        public Projectile Spawn(Transform head, Transform world, LaserSoundDriver sound, GameObject template, TrackedSaberController saber)
        {
            var chest = head.position + Vector3.down * chestDownM;
            if (!TryGuardOrigin(head, saber, chest, out var origin))
            {
                var local = SphericalOffset(
                    spawnDistanceM,
                    Azimuths[Random.Range(0, Azimuths.Length)],
                    Elevations[Random.Range(0, Elevations.Length)]);
                origin = head.TransformPoint(local);
            }

            if (template == null) return null;

            var shot = Instantiate(template);
            shot.SetActive(true);
            shot.name = "Projectile";
            shot.transform.SetParent(world, false);
            shot.transform.position = origin;
            var collider = shot.GetComponent<Collider>();
            if (collider != null) collider.enabled = false;

            var projectile = shot.GetComponent<Projectile>() ?? shot.AddComponent<Projectile>();
            projectile.Launch(origin, chest, flightSeconds, sound, head);
            return projectile;
        }

        bool TryGuardOrigin(Transform head, TrackedSaberController saber, Vector3 chest, out Vector3 origin)
        {
            origin = chest;
            if (saber == null || !saber.TrackedHandle) return false;

            var order = new int[Azimuths.Length * Elevations.Length];
            for (var i = 0; i < order.Length; i++) order[i] = i;
            for (var i = order.Length - 1; i > 0; i--)
            {
                var swap = Random.Range(0, i + 1);
                var tmp = order[i];
                order[i] = order[swap];
                order[swap] = tmp;
            }

            var fromChest = saber.Handle - chest;
            var fallback = head.TransformPoint(SphericalOffset(spawnDistanceM, Azimuths[0], Elevations[0]));

            for (var n = 0; n < order.Length; n++)
            {
                var index = order[n];
                var local = SphericalOffset(
                    spawnDistanceM,
                    Azimuths[index / Elevations.Length],
                    Elevations[index % Elevations.Length]);
                var candidate = head.TransformPoint(local);
                fallback = candidate;
                if (Vector3.Dot(candidate - chest, fromChest) <= 0f) continue;
                origin = candidate;
                return true;
            }

            origin = fallback;
            return true;
        }

        static Vector3 SphericalOffset(float distance, float azimuthDeg, float elevationDeg)
        {
            var az = azimuthDeg * Mathf.Deg2Rad;
            var el = elevationDeg * Mathf.Deg2Rad;
            var horizontal = Mathf.Cos(el);
            return new Vector3(horizontal * Mathf.Sin(az), Mathf.Sin(el), horizontal * Mathf.Cos(az)) * distance;
        }

    }
}
