using UnityEngine;

namespace ForceSense
{
    public static class SaberVisual
    {
        const float HandleLength = 0.20f;

        public static void Build(GameObject saber)
        {
            Part(saber.transform, PrimitiveType.Cylinder, "Handle",
                new Vector3(0f, 0f, -HandleLength * 0.35f),
                Quaternion.Euler(90f, 0f, 0f),
                new Vector3(0.028f, HandleLength * 0.5f, 0.028f),
                VisualTheme.Handle());

            for (var i = 0; i < 4; i++)
            {
                Part(saber.transform, PrimitiveType.Cylinder, "Grip",
                    new Vector3(0f, 0f, -0.02f - i * 0.028f),
                    Quaternion.Euler(90f, 0f, 0f),
                    new Vector3(0.031f, 0.007f, 0.031f),
                    VisualTheme.Grip());
            }

            Part(saber.transform, PrimitiveType.Cylinder, "Emitter",
                new Vector3(0f, 0f, 0.03f),
                Quaternion.Euler(90f, 0f, 0f),
                new Vector3(0.036f, 0.012f, 0.036f),
                VisualTheme.Trim());

            Part(saber.transform, PrimitiveType.Cylinder, "Pommel",
                new Vector3(0f, 0f, -HandleLength * 0.72f),
                Quaternion.Euler(90f, 0f, 0f),
                new Vector3(0.032f, 0.012f, 0.032f),
                VisualTheme.Trim());

            Part(saber.transform, PrimitiveType.Cube, "Button",
                new Vector3(0.016f, 0f, -0.04f),
                Quaternion.identity,
                new Vector3(0.008f, 0.01f, 0.016f),
                VisualTheme.Glow(VisualTheme.Sensor, 1.8f));

            var length = TrackedSaberController.BladeLengthM;
            Part(saber.transform, PrimitiveType.Cylinder, "BladeGlow",
                new Vector3(0f, 0f, length * 0.5f + 0.02f),
                Quaternion.Euler(90f, 0f, 0f),
                new Vector3(0.028f, length * 0.5f, 0.028f),
                VisualTheme.Glow(VisualTheme.Blade, 1.6f));
            Part(saber.transform, PrimitiveType.Cylinder, "BladeCore",
                new Vector3(0f, 0f, length * 0.5f + 0.02f),
                Quaternion.Euler(90f, 0f, 0f),
                new Vector3(0.012f, length * 0.5f, 0.012f),
                VisualTheme.Glow(Color.white, 2.8f));

            var light = new GameObject("BladeLight");
            light.transform.SetParent(saber.transform, false);
            light.transform.localPosition = new Vector3(0f, 0f, length * 0.45f);
            var point = light.AddComponent<Light>();
            point.type = LightType.Point;
            point.color = VisualTheme.Blade;
            point.intensity = 1.15f;
            point.range = 1.6f;
        }

        public static void DressHead(GameObject head)
        {
            var renderer = head.GetComponent<MeshRenderer>();
            if (renderer != null)
                renderer.sharedMaterial = VisualTheme.Lit(VisualTheme.Helmet, 0.7f, 0.35f, VisualTheme.Tex("Art/Textures/metal_plate_diff"));

            Part(head.transform, PrimitiveType.Cube, "Visor",
                new Vector3(0f, 0.01f, 0.42f),
                Quaternion.identity,
                new Vector3(0.72f, 0.22f, 0.08f),
                VisualTheme.Glow(VisualTheme.Sensor, 0.55f));
            Part(head.transform, PrimitiveType.Cylinder, "Band",
                new Vector3(0f, 0.12f, 0f),
                Quaternion.identity,
                new Vector3(1.05f, 0.08f, 1.05f),
                VisualTheme.Trim());
        }

        public static void HideHurtbox(GameObject hurtbox)
        {
            var renderer = hurtbox.GetComponent<MeshRenderer>();
            if (renderer != null) renderer.enabled = false;
        }

        static GameObject Part(Transform parent, PrimitiveType type, string name, Vector3 local, Quaternion rotation, Vector3 scale, Material material)
        {
            var go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = local;
            go.transform.localRotation = rotation;
            go.transform.localScale = scale;
            Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<MeshRenderer>().sharedMaterial = material;
            return go;
        }
    }
}
