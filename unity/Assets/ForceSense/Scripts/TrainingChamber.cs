using UnityEngine;

namespace ForceSense
{
    public static class TrainingChamber
    {
        public const float FloorY = -1.12f;
        public const float Height = 3.15f;
        public const float HalfWidth = 3.6f;
        public const float ZNear = -3.0f;
        public const float ZFar = 8.15f;
        public static readonly Vector3 PadCenter = new Vector3(0f, FloorY + 0.02f, 1.55f);

        public static Transform Build(Transform parent)
        {
            VisualTheme.ApplyEnvironment();
            var root = new GameObject("TrainingChamber").transform;
            root.SetParent(parent, false);

            Floor(root);
            Walls(root);
            Columns(root);
            Ceiling(root);
            TrainingCircle(root);
            SparseProps(root);
            Lighting(root);
            return root;
        }

        static void Floor(Transform root)
        {
            var depth = ZFar - ZNear;
            Primitive(root, PrimitiveType.Cube, "Floor",
                new Vector3(0f, FloorY - 0.04f, (ZNear + ZFar) * 0.5f),
                Quaternion.identity,
                new Vector3(HalfWidth * 2f + 0.4f, 0.08f, depth + 0.4f),
                VisualTheme.Floor());
        }

        static void Walls(Transform root)
        {
            var depth = ZFar - ZNear;
            var midZ = (ZNear + ZFar) * 0.5f;
            var midY = FloorY + Height * 0.5f;
            var wall = VisualTheme.Wall();
            var trim = VisualTheme.Trim();

            Primitive(root, PrimitiveType.Cube, "WallNegX", new Vector3(-HalfWidth, midY, midZ), Quaternion.identity, new Vector3(0.08f, Height, depth), wall);
            Primitive(root, PrimitiveType.Cube, "WallPosX", new Vector3(HalfWidth, midY, midZ), Quaternion.identity, new Vector3(0.08f, Height, depth), wall);
            Primitive(root, PrimitiveType.Cube, "WallNear", new Vector3(0f, midY, ZNear), Quaternion.identity, new Vector3(HalfWidth * 2f, Height, 0.08f), wall);
            Primitive(root, PrimitiveType.Cube, "WallFar", new Vector3(0f, midY, ZFar), Quaternion.identity, new Vector3(HalfWidth * 2f, Height, 0.08f), wall);

            RecessedPanels(root, -HalfWidth + 0.055f, 1, midZ, depth, wall);
            RecessedPanels(root, HalfWidth - 0.055f, -1, midZ, depth, wall);

            for (var x = -2.4f; x <= 2.4f; x += 2.4f)
            {
                VerticalStrip(root, new Vector3(x, midY, ZFar - 0.06f));
                VerticalStrip(root, new Vector3(x, midY, ZNear + 0.06f));
            }
            for (var z = 1.2f; z <= 6.8f; z += 2.8f)
            {
                VerticalStrip(root, new Vector3(-HalfWidth + 0.06f, midY, z));
                VerticalStrip(root, new Vector3(HalfWidth - 0.06f, midY, z));
            }

            Primitive(root, PrimitiveType.Cube, "BaseTrim", new Vector3(0f, FloorY + 0.08f, midZ), Quaternion.identity, new Vector3(HalfWidth * 2f - 0.1f, 0.12f, depth - 0.1f), trim);
        }

        static void RecessedPanels(Transform root, float x, int inward, float midZ, float depth, Material wall)
        {
            const float cell = 1.35f;
            var startZ = midZ - depth * 0.5f + cell * 0.5f + 0.2f;
            for (var z = startZ; z < midZ + depth * 0.5f - 0.3f; z += cell)
            for (var row = 0; row < 2; row++)
            {
                var y = FloorY + 0.55f + row * 1.35f;
                Primitive(root, PrimitiveType.Cube, "Recess",
                    new Vector3(x + inward * 0.03f, y, z),
                    Quaternion.identity,
                    new Vector3(0.04f, 1.15f, 1.15f),
                    wall);
            }
        }

        static void Columns(Transform root)
        {
            var y = FloorY + Height * 0.5f;
            var xs = new[] { -HalfWidth + 0.18f, HalfWidth - 0.18f };
            var zs = new[] { ZNear + 0.18f, ZFar - 0.18f };
            foreach (var x in xs)
            foreach (var z in zs)
            {
                Primitive(root, PrimitiveType.Cube, "Column", new Vector3(x, y, z), Quaternion.identity, new Vector3(0.22f, Height, 0.22f), VisualTheme.Trim());
                VerticalStrip(root, new Vector3(x, y, z + 0.12f));
            }
        }

        static void Ceiling(Transform root)
        {
            var midZ = (ZNear + ZFar) * 0.5f;
            Primitive(root, PrimitiveType.Cube, "Ceiling",
                new Vector3(0f, FloorY + Height, midZ),
                Quaternion.identity,
                new Vector3(HalfWidth * 2f, 0.08f, ZFar - ZNear),
                VisualTheme.Trim());

            for (var x = -1.8f; x <= 1.8f; x += 1.8f)
            for (var z = 1.4f; z <= 6.8f; z += 2.7f)
            {
                Primitive(root, PrimitiveType.Cube, "CeilingLight",
                    new Vector3(x, FloorY + Height - 0.05f, z),
                    Quaternion.identity,
                    new Vector3(0.9f, 0.03f, 0.16f),
                    VisualTheme.WarmStrip());
            }
        }

        static void TrainingCircle(Transform root)
        {
            Primitive(root, PrimitiveType.Cylinder, "Pad",
                PadCenter, Quaternion.identity, new Vector3(3.1f, 0.015f, 3.1f), VisualTheme.TrainingPad());

            const int segments = 40;
            const float radius = 1.58f;
            for (var i = 0; i < segments; i++)
            {
                var a = i / (float)segments * Mathf.PI * 2f;
                var p = PadCenter + new Vector3(Mathf.Cos(a) * radius, 0.02f, Mathf.Sin(a) * radius);
                Primitive(root, PrimitiveType.Cube, "RingSeg",
                    p, Quaternion.Euler(0f, -a * Mathf.Rad2Deg, 0f),
                    new Vector3(0.22f, 0.025f, 0.055f),
                    VisualTheme.TrainingRing());
            }

            Primitive(root, PrimitiveType.Cylinder, "InnerRing",
                PadCenter + Vector3.up * 0.018f, Quaternion.identity,
                new Vector3(0.55f, 0.012f, 0.55f), VisualTheme.WarmStrip());
        }

        static void SparseProps(Transform root)
        {
            Primitive(root, PrimitiveType.Cube, "CrateA",
                new Vector3(-2.7f, FloorY + 0.28f, 6.6f), Quaternion.Euler(0f, 18f, 0f),
                new Vector3(0.55f, 0.55f, 0.55f), VisualTheme.Wall());
            Primitive(root, PrimitiveType.Cube, "CrateB",
                new Vector3(2.85f, FloorY + 0.2f, 7.1f), Quaternion.Euler(0f, -12f, 0f),
                new Vector3(0.4f, 0.4f, 0.4f), VisualTheme.Trim());
            Primitive(root, PrimitiveType.Cube, "Console",
                new Vector3(0f, FloorY + 0.42f, ZNear + 0.28f), Quaternion.identity,
                new Vector3(1.1f, 0.72f, 0.22f), VisualTheme.Trim());
            Primitive(root, PrimitiveType.Cube, "ConsoleScreen",
                new Vector3(0f, FloorY + 0.58f, ZNear + 0.4f), Quaternion.identity,
                new Vector3(0.72f, 0.32f, 0.02f), VisualTheme.Glow(VisualTheme.Sensor, 0.7f));
            Primitive(root, PrimitiveType.Cube, "OriginBeacon",
                Vector3.zero, Quaternion.identity, new Vector3(0.06f, 0.06f, 0.03f),
                VisualTheme.Glow(VisualTheme.Sensor, 1.1f));
        }

        static void Lighting(Transform root)
        {
            var sun = new GameObject("KeyLight");
            sun.transform.SetParent(root, false);
            sun.transform.rotation = Quaternion.Euler(42f, -28f, 0f);
            var directional = sun.AddComponent<Light>();
            directional.type = LightType.Directional;
            directional.color = new Color(0.82f, 0.88f, 1f);
            directional.intensity = 1.05f;
            directional.shadows = LightShadows.Soft;

            Point(root, "PadLight", PadCenter + Vector3.up * 2.1f, new Color(1f, 0.78f, 0.52f), 2.4f, 9f);
            Point(root, "FillL", new Vector3(-2.2f, FloorY + 2.2f, 3.2f), VisualTheme.Warm, 1.4f, 8f);
            Point(root, "FillR", new Vector3(2.2f, FloorY + 2.2f, 3.2f), VisualTheme.Warm, 1.4f, 8f);
            Point(root, "CoolBack", new Vector3(0f, FloorY + 2.4f, 6.4f), VisualTheme.Sensor, 1.1f, 8f);
            Point(root, "SpectatorFill", new Vector3(2.1f, 1.4f, 4.2f), new Color(0.75f, 0.82f, 1f), 1.2f, 7f);
        }

        static void VerticalStrip(Transform root, Vector3 position)
        {
            Primitive(root, PrimitiveType.Cube, "WarmStrip",
                position, Quaternion.identity, new Vector3(0.035f, Height - 0.3f, 0.035f), VisualTheme.WarmStrip());
        }

        static void Point(Transform root, string name, Vector3 position, Color color, float intensity, float range)
        {
            var go = new GameObject(name);
            go.transform.SetParent(root, false);
            go.transform.position = position;
            var light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.intensity = intensity;
            light.range = range;
            light.shadows = LightShadows.None;
        }

        static GameObject Primitive(Transform parent, PrimitiveType type, string name, Vector3 position, Quaternion rotation, Vector3 scale, Material material)
        {
            var go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(position, rotation);
            go.transform.localScale = scale;
            Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<MeshRenderer>().sharedMaterial = material;
            return go;
        }
    }
}
