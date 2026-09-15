using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace ForceSense
{
    public sealed class SciFiHud : MonoBehaviour
    {
        Text _tracking;
        Text _calibration;
        Text _score;
        Text _phase;
        Text _startLabel;
        System.Action _onForward;
        System.Action _onSaber;
        System.Action _onToggle;

        public static SciFiHud Create(Transform parent, System.Action onForward, System.Action onSaber, System.Action onToggle)
        {
            EnsureEventSystem();
            var go = new GameObject("SciFiHud");
            go.transform.SetParent(parent, false);
            var hud = go.AddComponent<SciFiHud>();
            hud._onForward = onForward;
            hud._onSaber = onSaber;
            hud._onToggle = onToggle;
            hud.Build();
            return hud;
        }

        public void Refresh(string status, bool headLive, bool saberReady, bool forwardSet, bool saberSet, RoundPhase phase, RoundResult last, int blocks, int hits, int dodges, bool running)
        {
            if (_tracking != null)
                _tracking.text = $"HEAD     {(headLive ? "LIVE" : "---")}\nSABER    {(saberReady ? "READY" : "WAIT")}\nLINK     {ShortStatus(status)}";
            if (_calibration != null)
                _calibration.text = $"FORWARD  {(forwardSet ? "SET" : "NEED")}\nSABER    {(saberSet ? "SET" : "NEED")}";
            if (_score != null)
                _score.text = $"BLOCKS   {blocks:00}\nHITS     {hits:00}\nDODGES   {dodges:00}";
            if (_phase != null)
                _phase.text = running ? $"{phase.ToString().ToUpper()}   LAST {last.ToString().ToUpper()}" : "STANDBY";
            if (_startLabel != null)
                _startLabel.text = running ? "STOP  [SPACE]" : "START TRAINING  [SPACE]";
            ColorStatus(_tracking, headLive && saberReady);
        }

        static string ShortStatus(string status)
        {
            if (string.IsNullOrEmpty(status)) return "OFF";
            return status.Length > 28 ? status.Substring(0, 28) : status;
        }

        static void ColorStatus(Text text, bool ready)
        {
            if (text == null) return;
            text.color = ready ? VisualTheme.UiReady : VisualTheme.UiText;
        }

        void Build()
        {
            var canvasGo = new GameObject("Canvas");
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.pixelPerfect = true;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600, 900);
            scaler.matchWidthOrHeight = 0.5f;
            canvasGo.AddComponent<GraphicRaycaster>();

            var panel = VisualTheme.Slice(new Color(0.04f, 0.05f, 0.07f, 0.86f), VisualTheme.UiCyan);
            var amber = VisualTheme.Slice(new Color(0.12f, 0.07f, 0.03f, 0.92f), VisualTheme.UiAmber);
            var dim = VisualTheme.Slice(new Color(0.05f, 0.06f, 0.08f, 0.8f), new Color(0.25f, 0.4f, 0.48f));

            var left = Panel(canvasGo.transform, "Left", new Vector2(16, -16), new Vector2(420, 430), new Vector2(0, 1), panel);
            Label(left, "FORCESENSE\n<size=16>HEAR THE FORCE</size>", 18, 20, 380, 58, 22, FontStyle.Bold);
            Label(left, "TRACKING", 18, 84, 380, 22, 13, FontStyle.Bold, VisualTheme.UiCyan);
            _tracking = Label(left, "", 18, 108, 380, 72, 16);
            Label(left, "CALIBRATION", 18, 186, 380, 22, 13, FontStyle.Bold, VisualTheme.UiCyan);
            _calibration = Label(left, "", 18, 210, 380, 44, 16);

            Button(left, "SET FORWARD  [C]", 18, 268, 384, 36, dim, _onForward);
            Button(left, "SET SABER REFERENCE  [S]", 18, 312, 384, 36, dim, _onSaber);
            _startLabel = Button(left, "START TRAINING  [SPACE]", 18, 362, 384, 42, amber, _onToggle);

            var right = Panel(canvasGo.transform, "Right", new Vector2(-16, -16), new Vector2(280, 210), new Vector2(1, 1), panel);
            Label(right, "ROUND", 16, 16, 248, 22, 13, FontStyle.Bold, VisualTheme.UiCyan);
            _score = Label(right, "", 16, 42, 248, 90, 20, FontStyle.Bold);
            _phase = Label(right, "STANDBY", 16, 140, 248, 50, 15);
        }

        static RectTransform Panel(Transform parent, string name, Vector2 anchored, Vector2 size, Vector2 pivot, Sprite sprite)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = pivot;
            rect.anchorMax = pivot;
            rect.pivot = pivot;
            rect.anchoredPosition = anchored;
            rect.sizeDelta = size;
            var image = go.GetComponent<Image>();
            image.sprite = sprite;
            image.type = Image.Type.Sliced;
            image.color = Color.white;
            return rect;
        }

        static Text Label(Transform parent, string text, float x, float y, float w, float h, int size, FontStyle style = FontStyle.Normal, Color? color = null)
        {
            var go = new GameObject("Label", typeof(RectTransform), typeof(Text));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = new Vector2(0, 1);
            rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = new Vector2(x, -y);
            rect.sizeDelta = new Vector2(w, h);
            var ui = go.GetComponent<Text>();
            ui.font = VisualTheme.UiFont();
            ui.text = text;
            ui.fontSize = size;
            ui.fontStyle = style;
            ui.color = color ?? VisualTheme.UiText;
            ui.alignment = TextAnchor.UpperLeft;
            ui.horizontalOverflow = HorizontalWrapMode.Overflow;
            ui.verticalOverflow = VerticalWrapMode.Overflow;
            return ui;
        }

        static Text Button(Transform parent, string text, float x, float y, float w, float h, Sprite sprite, System.Action action)
        {
            var go = new GameObject("Button", typeof(RectTransform), typeof(Image), typeof(Button));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = new Vector2(0, 1);
            rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = new Vector2(x, -y);
            rect.sizeDelta = new Vector2(w, h);
            go.GetComponent<Image>().sprite = sprite;
            go.GetComponent<Image>().type = Image.Type.Sliced;
            var button = go.GetComponent<Button>();
            button.onClick.AddListener(() => action?.Invoke());

            var label = Label(go.transform, text, 10, 8, w - 20, h - 10, 14, FontStyle.Bold, VisualTheme.UiText);
            var labelRect = label.GetComponent<RectTransform>();
            labelRect.anchorMin = Vector2.zero;
            labelRect.anchorMax = Vector2.one;
            labelRect.pivot = new Vector2(0.5f, 0.5f);
            labelRect.offsetMin = new Vector2(8, 4);
            labelRect.offsetMax = new Vector2(-8, -4);
            label.alignment = TextAnchor.MiddleCenter;
            return label;
        }

        static void EnsureEventSystem()
        {
            if (Object.FindObjectOfType<EventSystem>() != null) return;
            var es = new GameObject("EventSystem");
            es.AddComponent<EventSystem>();
            es.AddComponent<StandaloneInputModule>();
        }
    }
}
