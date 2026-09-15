using UnityEngine;

namespace ForceSense
{
    public static class ProjectileVisual
    {
        public static GameObject CreateTemplate()
        {
            var root = new GameObject("ProjectileTemplate");
            root.SetActive(false);

            var core = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            core.name = "Core";
            core.transform.SetParent(root.transform, false);
            core.transform.localScale = Vector3.one * 0.07f;
            Object.Destroy(core.GetComponent<Collider>());
            core.GetComponent<MeshRenderer>().sharedMaterial = VisualTheme.Glow(VisualTheme.Bolt, 3.4f);

            var halo = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            halo.name = "Halo";
            halo.transform.SetParent(root.transform, false);
            halo.transform.localScale = Vector3.one * 0.16f;
            Object.Destroy(halo.GetComponent<Collider>());
            var haloMat = VisualTheme.Additive(new Color(1f, 0.45f, 0.15f, 0.35f), VisualTheme.Tex("Art/Vfx/circle_05"));
            halo.GetComponent<MeshRenderer>().sharedMaterial = haloMat;

            var trail = root.AddComponent<TrailRenderer>();
            trail.time = 0.38f;
            trail.widthMultiplier = 0.07f;
            trail.minVertexDistance = 0.02f;
            trail.numCapVertices = 4;
            trail.material = VisualTheme.Additive(new Color(1f, 0.5f, 0.18f, 1f), VisualTheme.Tex("Art/Vfx/flare_01"));
            trail.startColor = new Color(1f, 0.7f, 0.3f, 1f);
            trail.endColor = new Color(1f, 0.2f, 0.05f, 0f);

            var light = root.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = VisualTheme.Bolt;
            light.intensity = 1.6f;
            light.range = 2.2f;

            root.AddComponent<Projectile>();
            return root;
        }
    }
}
