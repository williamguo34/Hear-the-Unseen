using UnityEngine;

namespace ForceSense
{
    public sealed class ProjectileSpawner : MonoBehaviour
    {
        public static readonly float[] Azimuths = { -60f, -30f, 0f, 30f, 60f };
        public static readonly float[] Elevations = { -30f, 0f, 30f };

        [SerializeField] float spawnDistanceM = 6f;
        [SerializeField] float chestDownUnity = 0.30f;
        [SerializeField] float flightSeconds = 2.4f;

        public float FlightSeconds => flightSeconds;

        public Projectile Spawn(Transform head, Transform world, LaserSoundDriver sound, GameObject template)
        {
            var azimuth = Azimuths[Random.Range(0, Azimuths.Length)];
            var elevation = Elevations[Random.Range(0, Elevations.Length)];
            var local = SphericalOffset(spawnDistanceM, azimuth, elevation);
            var origin = head.TransformPoint(local);
            var target = head.position + Vector3.down * chestDownUnity;

            GameObject body;
            if (template != null)
            {
                body = Instantiate(template);
                body.SetActive(true);
            }
            else
            {
                body = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                body.transform.localScale = Vector3.one * 0.08f;
            }
            body.name = "Projectile";
            body.transform.SetParent(world, false);
            body.transform.position = origin;
            var collider = body.GetComponent<Collider>();
            if (collider != null) collider.enabled = false;

            var projectile = body.GetComponent<Projectile>() ?? body.AddComponent<Projectile>();
            projectile.Launch(origin, target, flightSeconds, sound, head);
            return projectile;
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
