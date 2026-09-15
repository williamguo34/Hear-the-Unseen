using UnityEngine;

namespace ForceSense
{
    public static class VisualTheme
    {
        public static readonly Color Void = new Color(0.06f, 0.07f, 0.09f);
        public static readonly Color Ambient = new Color(0.22f, 0.24f, 0.28f);
        public static readonly Color Fog = new Color(0.08f, 0.09f, 0.11f);
        public static readonly Color Metal = new Color(0.42f, 0.44f, 0.48f);
        public static readonly Color MetalDark = new Color(0.22f, 0.23f, 0.26f);
        public static readonly Color Panel = new Color(0.38f, 0.40f, 0.44f);
        public static readonly Color Concrete = new Color(0.42f, 0.40f, 0.38f);
        public static readonly Color Warm = new Color(1f, 0.52f, 0.18f);
        public static readonly Color Sensor = new Color(0.35f, 0.92f, 1f);
        public static readonly Color Blade = new Color(0.45f, 0.95f, 0.88f);
        public static readonly Color Bolt = new Color(1f, 0.42f, 0.12f);
        public static readonly Color Helmet = new Color(0.08f, 0.085f, 0.095f);
        public static readonly Color UiCyan = new Color(0.42f, 0.86f, 0.98f);
        public static readonly Color UiAmber = new Color(0.98f, 0.58f, 0.22f);
        public static readonly Color UiReady = new Color(0.4f, 0.92f, 0.55f);
        public static readonly Color UiWait = new Color(0.95f, 0.38f, 0.32f);
        public static readonly Color UiText = new Color(0.86f, 0.92f, 0.96f);

        static Material _wall;
        static Material _floor;
        static Material _trim;
        static Material _warm;
        static Material _pad;
        static Material _ring;

        public static Texture2D Tex(string resourcesPath)
        {
            return Resources.Load<Texture2D>(resourcesPath);
        }

        public static Material Lit(Color color, float metallic, float smooth, Texture2D albedo = null, Texture2D normal = null, Vector2? tile = null)
        {
            var mat = new Material(Shader.Find("Standard"));
            mat.color = color;
            if (albedo != null) mat.mainTexture = albedo;
            if (tile.HasValue) mat.mainTextureScale = tile.Value;
            mat.SetFloat("_Metallic", metallic);
            mat.SetFloat("_Glossiness", smooth);
            if (normal != null)
            {
                mat.SetTexture("_BumpMap", normal);
                if (tile.HasValue) mat.SetTextureScale("_BumpMap", tile.Value);
                mat.EnableKeyword("_NORMALMAP");
            }
            return mat;
        }

        public static Material Glow(Color color, float intensity)
        {
            var mat = Lit(color, 0.15f, 0.65f);
            mat.EnableKeyword("_EMISSION");
            mat.SetColor("_EmissionColor", color * intensity);
            return mat;
        }

        public static Material Additive(Color color, Texture2D texture = null)
        {
            var shader = Shader.Find("Particles/Additive")
                         ?? Shader.Find("Legacy Shaders/Particles/Additive")
                         ?? Shader.Find("Particles/Standard Unlit");
            var mat = new Material(shader);
            mat.color = color;
            if (texture != null) mat.mainTexture = texture;
            return mat;
        }

        public static Material Wall()
        {
            if (_wall != null) return _wall;
            _wall = Lit(Panel, 0.45f, 0.42f, Tex("Art/Textures/metal_plate_diff"), Tex("Art/Textures/metal_plate_nor"), new Vector2(1.6f, 1.6f));
            return _wall;
        }

        public static Material Floor()
        {
            if (_floor != null) return _floor;
            _floor = Lit(Concrete, 0.08f, 0.28f, Tex("Art/Textures/concrete_diff"), Tex("Art/Textures/concrete_nor"), new Vector2(3.5f, 3.5f));
            return _floor;
        }

        public static Material Trim()
        {
            return _trim ?? (_trim = Lit(MetalDark, 0.55f, 0.45f, Tex("Art/Textures/metal_plate_diff"), Tex("Art/Textures/metal_plate_nor"), new Vector2(0.6f, 2f)));
        }

        public static Material WarmStrip()
        {
            return _warm ?? (_warm = Glow(Warm, 2.4f));
        }

        public static Material TrainingPad()
        {
            return _pad ?? (_pad = Lit(new Color(0.28f, 0.29f, 0.32f), 0.4f, 0.38f, Tex("Art/Textures/metal_plate_diff"), Tex("Art/Textures/metal_plate_nor"), new Vector2(2f, 2f)));
        }

        public static Material TrainingRing()
        {
            return _ring ?? (_ring = Glow(Warm, 1.6f));
        }

        public static Material Handle()
        {
            return Lit(new Color(0.12f, 0.12f, 0.13f), 0.85f, 0.42f, Tex("Art/Textures/metal_plate_diff"), Tex("Art/Textures/metal_plate_nor"), new Vector2(1f, 3f));
        }

        public static Material Grip()
        {
            return Lit(new Color(0.08f, 0.07f, 0.07f), 0.05f, 0.18f);
        }

        public static Material OrbShell()
        {
            return Lit(new Color(0.22f, 0.24f, 0.27f), 0.62f, 0.5f, Tex("Art/Textures/metal_plate_diff"), Tex("Art/Textures/metal_plate_nor"), new Vector2(1.8f, 1.8f));
        }

        public static Sprite Slice(Color fill, Color border, int size = 64, int edge = 8)
        {
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
            tex.wrapMode = TextureWrapMode.Clamp;
            tex.filterMode = FilterMode.Bilinear;
            for (var y = 0; y < size; y++)
            for (var x = 0; x < size; x++)
            {
                var onEdge = x < 2 || y < 2 || x >= size - 2 || y >= size - 2;
                var inBorder = x < edge || y < edge || x >= size - edge || y >= size - edge;
                tex.SetPixel(x, y, onEdge ? border : inBorder ? Color.Lerp(fill, border, 0.35f) : fill);
            }
            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, new Vector4(edge, edge, edge, edge));
        }

        public static void ApplyEnvironment()
        {
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = Ambient;
            RenderSettings.ambientIntensity = 1f;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = Fog;
            RenderSettings.fogStartDistance = 10f;
            RenderSettings.fogEndDistance = 28f;
            RenderSettings.reflectionIntensity = 0.35f;
            QualitySettings.pixelLightCount = Mathf.Max(QualitySettings.pixelLightCount, 8);
        }

        public static Font UiFont()
        {
            return Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }
    }
}
