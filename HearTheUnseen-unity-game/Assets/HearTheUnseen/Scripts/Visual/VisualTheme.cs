using UnityEngine;

namespace HearTheUnseen
{
    public static class VisualTheme
    {
        public static readonly Color Ambient = new Color(0.22f, 0.24f, 0.28f);
        public static readonly Color Fog = new Color(0.08f, 0.09f, 0.11f);
        public static readonly Color Sensor = new Color(0.35f, 0.92f, 1f);
        public static readonly Color Blade = new Color(0.45f, 0.95f, 0.88f);
        public static readonly Color Bolt = new Color(1f, 0.42f, 0.12f);
        public static readonly Color UiReady = new Color(0.4f, 0.92f, 0.55f);
        public static readonly Color UiText = new Color(0.86f, 0.92f, 0.96f);

        public static Texture2D Tex(string resourcesPath)
        {
            return Resources.Load<Texture2D>(resourcesPath);
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
